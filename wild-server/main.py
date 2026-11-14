"""WildAgent 后端的 FastAPI 应用入口。

本模块只负责装配应用：
1. 注册启动/关闭生命周期；
2. 配置浏览器跨域访问；
3. 挂载 WebSocket Agent 与场景文件 REST 路由。

具体业务逻辑分别下沉到 ``app.api`` 和 ``app.services``，避免入口文件持有状态。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from loguru import logger
import asyncio
from sqlalchemy.exc import SQLAlchemyError
from redis.exceptions import RedisError

from app.api.ws_agent import (
    router as ws_router,
    shutdown_generation_jobs,
    startup_generation_jobs,
)
from app.api.scenes import router as scenes_router
from app.api.sessions import router as sessions_router
from app.api.assets import router as assets_router
from app.api.config_api import router as config_router
from app.api.rag_observability import router as rag_observability_router
from app.api.designs import router as designs_router
from app.api.item_catalog import router as item_catalog_router
from app.api.auth import router as auth_router, enforce_write_access
from app.services.agent_service import agent_service
from config import config
from app.infrastructure.database import database
from app.infrastructure.cache import cache
from app.infrastructure.realtime import realtime_bus
from app.extensions.presence import presence_service
from app.repositories.errors import AccessDenied


@asynccontextmanager
async def lifespan(app: FastAPI):
    """管理整个 FastAPI 应用的启动与关闭阶段。

    ``yield`` 之前在服务开始接收请求前执行，``yield`` 之后在服务退出时执行。
    参数 ``app`` 由 FastAPI 注入，保留它是为了符合 lifespan 回调协议。
    """
    print_log()
    try:
        await init_connect()
        await realtime_bus.start()
        await presence_service.startup()
        await startup_generation_jobs()
        yield
    finally:
        await shutdown_generation_jobs()
        await presence_service.shutdown()
        await realtime_bus.close()
        await cache.aclose()
        await asyncio.to_thread(close_connect)


def print_log():
    """记录应用开始启动。"""
    logger.info("服务启动")


async def init_connect():
    await asyncio.to_thread(database.initialize)
    await asyncio.to_thread(cache.check)
    logger.info("MySQL 与 Redis 连接已就绪")


def close_connect():
    database.close()
    cache.close()
    logger.info("断开服务")


# ``app`` 是 Uvicorn 通过 ``main:app`` 导入的 ASGI 应用对象。
app = FastAPI(
    version="1.0",
    # 由上面的上下文管理器接管应用启动、关闭前后的逻辑。
    lifespan=lifespan
)


@app.exception_handler(SQLAlchemyError)
@app.exception_handler(RedisError)
async def storage_error_handler(request, exc):
    return JSONResponse(status_code=503, content={"detail": "数据服务暂不可用，请稍后重试"})


@app.exception_handler(AccessDenied)
async def ownership_error_handler(request, exc):
    return JSONResponse(status_code=404, content={"detail": "资料不存在"})

# 开发阶段允许 Vite 前端从不同端口访问 API 和 WebSocket。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 上线时应替换为明确的前端域名。
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由实现留在各自模块；入口只负责把它们挂到同一个应用上。
app.middleware("http")(enforce_write_access)
app.include_router(auth_router)
app.include_router(ws_router, tags=["ws连接初始化"])
app.include_router(scenes_router, tags=["场景API"])
app.include_router(sessions_router, tags=["会话API"])
app.include_router(assets_router, tags=["资产API"])
app.include_router(config_router, tags=["配置管理"])
app.include_router(rag_observability_router)
app.include_router(designs_router)
app.include_router(item_catalog_router)


@app.get("/")
async def root():
    """最小健康检查接口，用于快速确认 HTTP 服务可访问。"""
    return {"Hello": "World"}


@app.get("/health/ready")
async def readiness():
    """报告当前进程真实的 RAG 初始化状态，供 Docker/Jenkins 就绪探测。"""
    loader = agent_service.spec_loader
    loader_name = type(loader).__name__
    source_count = len(loader.list_sources())
    sync_stats = getattr(loader, "last_sync_stats", None)
    if callable(sync_stats):
        sync_stats = sync_stats()
    if not isinstance(sync_stats, dict):
        sync_stats = {"total": 0, "updated": 0, "deleted": 0}

    rag_ready = (
        not config.rag.enabled
        or (
            loader_name == "RAGSpecLoader"
            # list_sources 同时包含固定注入的最小规范和 RAG 文档。
            and source_count > 1
            and sync_stats.get("total", 0) > 0
        )
    )
    storage_ready = True
    try:
        await asyncio.to_thread(database.check)
        await asyncio.to_thread(cache.check)
    except (SQLAlchemyError, RedisError):
        storage_ready = False
    ready = rag_ready and storage_ready
    payload = {
        "status": "ready" if ready else "not_ready",
        "storage": {"ready": storage_ready, "database": "mysql", "cache": "redis"},
        "rag": {
            "enabled": config.rag.enabled,
            "ready": rag_ready,
            "loader": loader_name,
            "source_count": source_count,
            "collection": config.rag.collection_name,
            "sync": sync_stats,
        },
    }
    return JSONResponse(status_code=200 if ready else 503, content=payload)


if __name__ == "__main__":
    # 支持直接执行 ``python main.py``；生产部署通常使用外部 uvicorn 命令。
    import uvicorn

    uvicorn.run(
        "main:app",
        log_level="info",
        reload=True
    )
