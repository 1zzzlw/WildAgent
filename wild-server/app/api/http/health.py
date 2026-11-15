from fastapi.responses import JSONResponse
import asyncio
from sqlalchemy.exc import SQLAlchemyError
from redis.exceptions import RedisError
from app.agent.runtime import agent_runtime
from config import config
from app.infrastructure.persistence.database import database
from app.infrastructure.redis.connection import cache
from fastapi import APIRouter
router = APIRouter()


@router.get("/")
async def root():
    """最小健康检查接口，用于快速确认 HTTP 服务可访问。"""
    return {"Hello": "World"}


@router.get("/health/ready")
async def readiness():
    """报告当前进程真实的 RAG 初始化状态，供 Docker/Jenkins 就绪探测。"""
    loader = agent_runtime.spec_loader
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
