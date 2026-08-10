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

from app.api.ws_agent import router as ws_router
from app.api.scenes import router as scenes_router
from app.api.sessions import router as sessions_router
from app.api.assets import router as assets_router
from app.services.agent_service import agent_service
from config import config


@asynccontextmanager
async def lifespan(app: FastAPI):
    """管理整个 FastAPI 应用的启动与关闭阶段。

    ``yield`` 之前在服务开始接收请求前执行，``yield`` 之后在服务退出时执行。
    参数 ``app`` 由 FastAPI 注入，保留它是为了符合 lifespan 回调协议。
    """
    # 启动阶段：先输出启动日志，再初始化未来可能加入的外部连接。
    print_log()
    init_connect()

    # 控制权交还给 FastAPI；应用会在这里持续运行，直到收到关闭信号。
    yield

    # 关闭阶段：统一释放数据库、缓存或其他长连接。目前只有占位日志。
    close_connect()


def print_log():
    """记录应用开始启动。"""
    logger.info("服务启动")


def init_connect():
    """初始化外部服务连接的预留入口。"""
    logger.info("建立连接成功")


def close_connect():
    """释放外部服务连接的预留入口。"""
    logger.info("断开服务")


# ``app`` 是 Uvicorn 通过 ``main:app`` 导入的 ASGI 应用对象。
app = FastAPI(
    # 由上面的上下文管理器接管应用启动、关闭前后的逻辑。
    lifespan=lifespan
)

# 开发阶段允许 Vite 前端从不同端口访问 API 和 WebSocket。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 上线时应替换为明确的前端域名。
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由实现留在各自模块；入口只负责把它们挂到同一个应用上。
app.include_router(ws_router, tags=["ws连接初始化"])
app.include_router(scenes_router, tags=["场景API"])
app.include_router(sessions_router, tags=["会话API"])
app.include_router(assets_router, tags=["资产API"])


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
            and source_count >= 30
            and sync_stats.get("total", 0) > 0
        )
    )
    payload = {
        "status": "ready" if rag_ready else "not_ready",
        "rag": {
            "enabled": config.rag.enabled,
            "ready": rag_ready,
            "loader": loader_name,
            "source_count": source_count,
            "collection": config.rag.collection_name,
            "sync": sync_stats,
        },
    }
    return JSONResponse(status_code=200 if rag_ready else 503, content=payload)


if __name__ == "__main__":
    # 支持直接执行 ``python main.py``；生产部署通常使用外部 uvicorn 命令。
    import uvicorn

    uvicorn.run(
        "main:app",
        log_level="info",
        reload=True
    )
