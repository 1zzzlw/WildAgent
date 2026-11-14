"""LangGraph 持久化任务、checkpoint 生命周期和断线事件补发。"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.checkpoint.mysql.asyncmy import AsyncMySaver
import asyncmy
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from redis.exceptions import LockError

from config import config
from app.infrastructure.database import Database, database
from app.infrastructure.schema import metadata
from app.infrastructure.checkpoints import check_schema
from app.infrastructure.cache import cache
from app.infrastructure.realtime import realtime_bus, session_lock
from app.repositories.jobs import JobRepository
from loguru import logger

from app.contracts.agent_events import versioned_event


JobRunner = Callable[[Any, dict, bool], Awaitable[None]]

GENERATION_PIPELINE_VERSION = "design-document-auto-v1"
_PIPELINE_UPGRADE_ERROR = "生成流程已升级，旧任务无法继续恢复，请重新发起生成请求"
_PERSISTED_EVENT_TYPES = {
    "agent_step",
    "thinking_status",
    "plan_ready",
    "plan_item_updated",
    "design_ready",
    "patch_proposal",
    "blueprint_generated",
    "agent_reply",
    "error",
    "generation_stopped",
}
_TERMINAL_EVENT_STATUS = {
    "patch_proposal": "completed",
    "agent_reply": "completed",
    "error": "failed",
    "generation_stopped": "stopped",
}


@dataclass(slots=True)
class GenerationJob:
    request_id: str
    session_id: str
    payload: dict
    status: str
    last_event_seq: int = 0
    error: str | None = None


class DurableEventSink:
    """实现 WebSocket 的 send_json 接口，同时持久化并广播事件。"""

    def __init__(self, service: "GenerationJobService", request_id: str):
        self.service = service
        self.request_id = request_id
        self.failed = False
        self.error: str | None = None

    async def send_json(self, payload: dict) -> None:
        if payload.get("type") == "error" or payload.get("validation_passed") is False:
            self.failed = True
            self.error = str(payload.get("error") or payload.get("content") or "校验未通过")
        try:
            await self.service.publish_event(self.request_id, payload)
        except (sqlite3.Error, SQLAlchemyError) as exc:
            self.failed = True
            self.error = str(exc)
            logger.error(f"[{self.request_id}] 事件记录失败，继续向客户端发送已有结果: {exc}")
            await self.service._broadcast(self.request_id, versioned_event(payload))


class GenerationJobService:
    """让图任务独立于任意一条 WebSocket 连接。"""

    def __init__(self, database_path: Path | None = None, *, bus=realtime_bus):
        # 显式路径仅用于隔离回归；应用默认始终连接 MySQL。
        self.database_path = Path(database_path) if database_path is not None else None
        db = Database(create_engine(f"sqlite:///{self.database_path}", connect_args={"check_same_thread": False})) if self.database_path else database
        self.repository = JobRepository(db)
        self.bus = bus
        self._recovery_task = None
        self._checkpoint_pool = None
        self._checkpoint_context = None
        self._checkpointer: AsyncSqliteSaver | AsyncMySaver | None = None
        self._runner: JobRunner | None = None
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._subscribers: dict[str, dict[int, Any]] = {}
        self._event_locks: dict[str, asyncio.Lock] = {}
        self._payload_locks: dict[str, asyncio.Lock] = {}
        self._stopped_requests: set[str] = set()
        self._init_lock = asyncio.Lock()
        self._initialized = False

    @property
    def checkpointer(self):
        if self._checkpointer is None:
            raise RuntimeError("GenerationJobService 尚未初始化")
        return self._checkpointer

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            try:
                if self.database_path is not None:
                    self.database_path.parent.mkdir(parents=True, exist_ok=True)
                    await asyncio.to_thread(metadata.create_all, self.repository.database.engine)
                    self._checkpoint_context = AsyncSqliteSaver.from_conn_string(str(self.database_path))
                    self._checkpointer = await self._checkpoint_context.__aenter__()
                    await self._checkpointer.setup()
                else:
                    await asyncio.to_thread(check_schema)
                    cfg = config.mysql
                    self._checkpoint_pool = await asyncmy.create_pool(host=cfg.host, port=cfg.port,
                        user=cfg.username, password=cfg.password.get_secret_value(), db=cfg.database,
                        charset="utf8mb4", autocommit=True, minsize=1, maxsize=4,
                        connect_timeout=cfg.connect_timeout, pool_recycle=1800)
                    self._checkpointer = AsyncMySaver(self._checkpoint_pool)
                    await self.bus.start()
                    self.bus.subscribe("generation", self._receive_remote)
                self._initialized = True
                logger.info("LangGraph 持久化已启用")
            except BaseException:
                await self.shutdown()
                raise

    async def startup(self, runner: JobRunner) -> None:
        await self.initialize()
        self._runner = runner
        active_jobs = await self.list_active_jobs()
        incompatible = [
            job for job in active_jobs if not self._uses_current_pipeline(job)
        ]
        for job in incompatible:
            await self._retire_incompatible_job(job)
        incomplete = [
            job
            for job in active_jobs
            if job.status == "running" and self._uses_current_pipeline(job)
        ]
        for job in incomplete:
            self._spawn(job, resume=True)
        if self.database_path is None and self._recovery_task is None:
            self._recovery_task = asyncio.create_task(self._recover_loop(), name="generation-recovery")
        if incomplete:
            logger.warning(f"正在恢复 {len(incomplete)} 个未完成 LangGraph 任务")

    async def shutdown(self) -> None:
        if self._recovery_task:
            self._recovery_task.cancel()
            await asyncio.gather(self._recovery_task, return_exceptions=True)
            self._recovery_task = None
        tasks = list(self._active_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._active_tasks.clear()
        self._stopped_requests.clear()
        if self._checkpoint_context is not None:
            await self._checkpoint_context.__aexit__(None, None, None)
        if self._checkpoint_pool is not None:
            self._checkpoint_pool.close()
            await self._checkpoint_pool.wait_closed()
            self._checkpoint_pool = None
        self.bus.unsubscribe("generation", self._receive_remote)
        self._checkpoint_context = None
        self._checkpointer = None
        self._runner = None
        self._initialized = False

    async def start_job(self, payload: dict, subscriber: Any) -> tuple[GenerationJob, bool]:
        await self.initialize()
        if self.database_path is not None:
            return await self._start_job(payload, subscriber)
        async with session_lock(str(payload.get("session_id") or payload.get("request_id") or "")):
            return await self._start_job(payload, subscriber)

    async def _start_job(self, payload: dict, subscriber: Any) -> tuple[GenerationJob, bool]:
        """创建任务；同一会话已有运行任务时附着旧任务而不重复生成。"""
        await self.initialize()
        request_id = str(payload.get("request_id") or "")
        session_id = str(payload.get("session_id") or request_id)
        if not request_id:
            raise ValueError("request_id 不能为空")

        active = await self.get_active_job_for_session(session_id)
        if active is not None and not self._uses_current_pipeline(active):
            await self._retire_incompatible_job(active)
            active = None
        if active is not None and active.request_id != request_id:
            return active, False

        existing = await self.get_job(request_id)
        if existing is not None:
            if existing.session_id != session_id:
                raise ValueError("任务不属于当前会话")
            return existing, False

        job_payload = dict(payload)
        job_payload["_pipeline_version"] = GENERATION_PIPELINE_VERSION
        await self._insert_job(request_id, session_id, job_payload)
        job = GenerationJob(request_id, session_id, job_payload, "running")
        await self.attach(job.request_id, subscriber)
        self._spawn(job, resume=False)
        return job, True

    async def stop_job(
        self, subscriber: Any, *, request_id: str, session_id: str,
    ) -> GenerationJob:
        """先落盘停止状态，再取消执行；日志写完后才发送停止确认。"""
        await self.initialize()
        lock = self._payload_locks.setdefault(request_id, asyncio.Lock())
        async with lock:
            async with self._event_locks.setdefault(request_id, asyncio.Lock()):
                job = await self.get_job(request_id)
                if job is None or job.session_id != session_id:
                    raise ValueError("找不到当前会话的任务")
                await self.attach(request_id, subscriber)
                event = versioned_event({
                    "type": "generation_stopped",
                    "request_id": request_id,
                    "session_id": session_id,
                    "status": "stopped",
                    "content": "已停止，已有执行记录已保存。",
                })
                if job.status not in {"running", "waiting_review"}:
                    await subscriber.send_json({
                        **event,
                        "status": job.status,
                        "content": "已有执行记录已保存。" if job.status == "stopped"
                        else "任务已结束，已有记录已保留。",
                    })
                    return job
                self._stopped_requests.add(request_id)
                await self._mark_status(request_id, "stopped", None)
            if self.database_path is None:
                await self.bus.publish("generation", {"command": "stop", "request_id": request_id})
            task = self._active_tasks.get(request_id)
            if task is not None and not task.done():
                task.cancel("user_stop")
                await asyncio.gather(task, return_exceptions=True)
            await self.publish_event(request_id, event)
            return await self.get_job(request_id)

    async def resume_or_replay(
        self,
        subscriber: Any,
        *,
        request_id: str | None,
        session_id: str,
        after_seq: int = 0,
    ) -> GenerationJob | None:
        """重新附着连接，必要时恢复任务，并补发断线期间的关键事件。"""
        await self.initialize()
        job = await self.get_job(request_id) if request_id else None
        if job is not None and job.session_id != session_id:
            raise ValueError("任务不属于当前会话")
        if job is None:
            job = await self.get_active_job_for_session(session_id)
        if job is None:
            return None
        if job.status in {"running", "waiting_review"} and not self._uses_current_pipeline(job):
            await self._retire_incompatible_job(job)
            job = await self.get_job(job.request_id)
            assert job is not None

        # 与持久化事件发布共用一把锁，保证“历史补发完成”先于新的实时关键事件。
        lock = self._event_locks.setdefault(job.request_id, asyncio.Lock())
        async with lock:
            await self.attach(job.request_id, subscriber)
            await subscriber.send_json(versioned_event({
                "type": "generation_resumed",
                "request_id": job.request_id,
                "session_id": job.session_id,
                "status": job.status,
                "last_event_seq": job.last_event_seq,
            }))
            for event in await self.events_after(job.request_id, after_seq):
                await subscriber.send_json(event)
        if job.status == "running" and job.request_id not in self._active_tasks:
            self._spawn(job, resume=True)
        return job

    async def attach(self, request_id: str, subscriber: Any) -> None:
        self._subscribers.setdefault(request_id, {})[id(subscriber)] = subscriber

    async def detach(self, subscriber: Any) -> None:
        subscriber_id = id(subscriber)
        empty = []
        for request_id, subscribers in self._subscribers.items():
            subscribers.pop(subscriber_id, None)
            if not subscribers:
                empty.append(request_id)
        for request_id in empty:
            self._subscribers.pop(request_id, None)

    def has_running_job_for(self, subscriber: Any) -> bool:
        """当前物理连接是否仍附着至少一个正在执行的后台任务。"""
        subscriber_id = id(subscriber)
        for request_id, subscribers in self._subscribers.items():
            if subscriber_id not in subscribers:
                continue
            task = self._active_tasks.get(request_id)
            if task is not None and not task.done():
                return True
        return False

    async def publish_event(self, request_id: str, payload: dict) -> None:
        if request_id in self._stopped_requests and payload.get("type") != "generation_stopped":
            return
        event = dict(payload)
        should_persist = (
            event.get("type") in _PERSISTED_EVENT_TYPES
            or (
                event.get("type") == "thinking_delta"
                and event.get("channel") == "progress"
            )
        )
        if should_persist:
            lock = self._event_locks.setdefault(request_id, asyncio.Lock())
            async with lock:
                if request_id in self._stopped_requests and event.get("type") != "generation_stopped":
                    return
                sequence = await self._append_event(request_id, event)
                if not sequence:
                    return
                event["event_seq"] = sequence
                await self._broadcast(request_id, event)
            return
        await self._broadcast(request_id, event)

    async def events_after(self, request_id: str, after_seq: int) -> list[dict]:
        return await asyncio.to_thread(self.repository.events_after, request_id, after_seq)

    async def get_job(self, request_id: str | None) -> GenerationJob | None:
        return self._row_to_job(await asyncio.to_thread(self.repository.get, request_id)) if request_id else None

    async def get_running_job_for_session(self, session_id: str) -> GenerationJob | None:
        return self._row_to_job(await asyncio.to_thread(self.repository.active, session_id, ("running",)))

    async def get_active_job_for_session(self, session_id: str) -> GenerationJob | None:
        return self._row_to_job(await asyncio.to_thread(self.repository.active, session_id))

    async def delete_session_jobs(self, session_id: str) -> None:
        await self.initialize()
        request_ids = await asyncio.to_thread(self.repository.delete_session, session_id)
        for request_id in request_ids:
            await self.checkpointer.adelete_thread("generation:" + request_id)

    async def list_running_jobs(self) -> list[GenerationJob]:
        return [self._row_to_job(row) for row in await asyncio.to_thread(self.repository.list, ("running",))]

    async def list_active_jobs(self) -> list[GenerationJob]:
        return [self._row_to_job(row) for row in await asyncio.to_thread(self.repository.list)]

    @staticmethod
    def _uses_current_pipeline(job: GenerationJob) -> bool:
        return job.payload.get("_pipeline_version") == GENERATION_PIPELINE_VERSION

    async def _require_current_pipeline(self, job: GenerationJob) -> None:
        if self._uses_current_pipeline(job):
            return
        await self._retire_incompatible_job(job)
        raise ValueError(_PIPELINE_UPGRADE_ERROR)

    async def _retire_incompatible_job(self, job: GenerationJob) -> None:
        """终止旧图拓扑任务，避免恢复到已经删除的节点。"""

        if job.status not in {"running", "waiting_review"}:
            return
        logger.warning(
            f"[{job.request_id}] 检测到旧生成流程任务，已停止自动恢复"
        )
        await self.publish_event(job.request_id, versioned_event({
            "type": "error",
            "code": "generation_pipeline_upgraded",
            "request_id": job.request_id,
            "session_id": job.session_id,
            "error": _PIPELINE_UPGRADE_ERROR,
        }))

    def _spawn(self, job: GenerationJob, *, resume: bool) -> asyncio.Task:
        if self._runner is None:
            raise RuntimeError("GenerationJobService runner 尚未配置")
        existing = self._active_tasks.get(job.request_id)
        if existing is not None and not existing.done():
            return existing
        task = asyncio.create_task(
            self._run_claimed_job(job, resume=resume),
            name=f"langgraph:{job.request_id}",
        )
        self._active_tasks[job.request_id] = task
        return task

    async def _recover_loop(self):
        while True:
            await asyncio.sleep(30)
            try:
                for job in await self.list_running_jobs():
                    if self._uses_current_pipeline(job) and job.request_id not in self._active_tasks:
                        self._spawn(job, resume=True)
            except Exception:
                logger.warning("任务恢复扫描暂不可用，将在下一轮重新检查")

    async def _run_claimed_job(self, job: GenerationJob, *, resume: bool):
        if self.database_path is not None:
            return await self._run_job(job, resume=resume)
        lock = cache.async_client.lock(cache.key("generation:lease:" + job.request_id), timeout=60, blocking=False)
        work = renewal = None
        try:
            if not await lock.acquire(blocking=False):
                return
            latest = await self.get_job(job.request_id)
            if latest is None or latest.status != "running":
                return
            work = asyncio.create_task(self._run_job(job, resume=resume))
            async def renew():
                while True:
                    await asyncio.sleep(15)
                    await lock.extend(60, replace_ttl=True)
                    latest = await self.get_job(job.request_id)
                    if latest is None or latest.status == "stopped":
                        raise asyncio.CancelledError()
            renewal = asyncio.create_task(renew())
            done, _ = await asyncio.wait((work, renewal), return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                await task
        finally:
            for task in (work, renewal):
                if task and not task.done():
                    task.cancel()
            await asyncio.gather(*(task for task in (work, renewal) if task), return_exceptions=True)
            try:
                if await lock.owned():
                    await lock.release()
            except LockError:
                pass
            if self._active_tasks.get(job.request_id) is asyncio.current_task():
                self._active_tasks.pop(job.request_id, None)

    async def _receive_remote(self, data: dict):
        request_id = data["request_id"]
        if data.get("command") == "stop":
            self._stopped_requests.add(request_id)
            task = self._active_tasks.get(request_id)
            if task:
                task.cancel("remote_user_stop")
            return
        async with self._event_locks.setdefault(request_id, asyncio.Lock()):
            await self._broadcast_local(request_id, data["event"])

    async def _run_job(self, job: GenerationJob, *, resume: bool) -> None:
        sink = DurableEventSink(self, job.request_id)
        try:
            assert self._runner is not None
            await self._runner(sink, job.payload, resume)
        except asyncio.CancelledError:
            current = await self.get_job(job.request_id)
            current_status = current.status if current is not None else "running"
            logger.info(
                f"[{job.request_id}] 用户停止任务" if current_status == "stopped"
                else f"[{job.request_id}] 任务随服务关闭暂停，保留 {current_status} 状态"
            )
            raise
        except Exception as exc:
            logger.exception(f"[{job.request_id}] 持久化生成任务失败: {exc}")
            await self.publish_event(job.request_id, versioned_event({
                "type": "error",
                "request_id": job.request_id,
                "session_id": job.session_id,
                "error": f"生成任务失败: {exc}",
            }))
            await self._mark_status(job.request_id, "failed", str(exc))
        else:
            await self._mark_status(
                job.request_id,
                "failed" if sink.failed else "completed",
                sink.error if sink.failed else None,
            )
        finally:
            current = asyncio.current_task()
            if self._active_tasks.get(job.request_id) is current:
                self._active_tasks.pop(job.request_id, None)

    async def _broadcast(self, request_id: str, event: dict) -> None:
        await self._broadcast_local(request_id, event)
        if self.database_path is None:
            from redis.exceptions import RedisError
            try:
                await self.bus.publish("generation", {"request_id": request_id, "event": event})
            except RedisError:
                logger.warning("实时通知暂不可用，已保留事件供断线重放")

    async def _broadcast_local(self, request_id: str, event: dict) -> None:
        subscribers = list(self._subscribers.get(request_id, {}).values())
        failed = []
        for subscriber in subscribers:
            try:
                await asyncio.wait_for(subscriber.send_json(event), timeout=5)
            except Exception:
                failed.append(subscriber)
        for subscriber in failed:
            await self.detach(subscriber)

    async def _insert_job(self, request_id: str, session_id: str, payload: dict) -> None:
        await asyncio.to_thread(self.repository.insert, request_id, session_id, payload)

    async def _append_event(self, request_id: str, payload: dict) -> int:
        terminal = _TERMINAL_EVENT_STATUS.get(payload.get("type"))
        if terminal and payload.get("validation_passed") is False:
            terminal = "failed"
        return await asyncio.to_thread(self.repository.append, request_id, payload, terminal)

    async def _mark_status(self, request_id: str, status: str, error: str | None) -> None:
        await asyncio.to_thread(self.repository.mark, request_id, status, error)

    @staticmethod
    def _row_to_job(row) -> GenerationJob | None:
        if row is None:
            return None
        return GenerationJob(
            request_id=row[0],
            session_id=row[1],
            payload=json.loads(row[2]),
            status=row[3],
            last_event_seq=int(row[4]),
            error=row[5],
        )


generation_job_service = GenerationJobService()
