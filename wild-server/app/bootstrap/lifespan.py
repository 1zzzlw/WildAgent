from fastapi import FastAPI
from contextlib import asynccontextmanager
from loguru import logger
import asyncio
from app.infrastructure.persistence.database import database
from app.infrastructure.redis.connection import cache
from app.infrastructure.redis.events import realtime_bus
from app.api.websocket.connections import presence_service

from app.bootstrap.resources import initialize_agent_resources
from app.application.generation.runner import run_generation
from app.application.generation.jobs import generation_job_service


async def startup_generation_jobs():
    await generation_job_service.startup(run_generation)


async def shutdown_generation_jobs():
    await generation_job_service.shutdown()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """管理整个 FastAPI 应用的启动与关闭阶段。

    ``yield`` 之前在服务开始接收请求前执行，``yield`` 之后在服务退出时执行。
    参数 ``app`` 由 FastAPI 注入，保留它是为了符合 lifespan 回调协议。
    """
    print_log()
    try:
        await init_connect()
        await asyncio.to_thread(initialize_agent_resources)
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
