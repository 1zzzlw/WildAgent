"""LangGraph 持久化任务、checkpoint 生命周期和断线事件补发。"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from loguru import logger

from app.agent.protocol import versioned_event


JobRunner = Callable[[Any, dict, bool], Awaitable[None]]

_SERVER_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHECKPOINT_PATH = (
    _SERVER_ROOT / "storage" / "sessions" / "langgraph_checkpoints.sqlite3"
)
_PERSISTED_EVENT_TYPES = {
    "agent_step",
    "thinking_status",
    "patch_proposal",
    "blueprint_generated",
    "agent_reply",
    "error",
}
_TERMINAL_EVENT_STATUS = {
    "patch_proposal": "completed",
    "agent_reply": "completed",
    "error": "failed",
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
        if payload.get("type") == "error":
            self.failed = True
            self.error = str(payload.get("error") or "任务返回错误事件")
        await self.service.publish_event(self.request_id, payload)


class GenerationJobService:
    """让精密模式生成任务独立于任意一条 WebSocket 连接。"""

    def __init__(self, database_path: Path = DEFAULT_CHECKPOINT_PATH):
        self.database_path = Path(database_path)
        self._checkpoint_context = None
        self._checkpointer: AsyncSqliteSaver | None = None
        self._runner: JobRunner | None = None
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._subscribers: dict[str, dict[int, Any]] = {}
        self._event_locks: dict[str, asyncio.Lock] = {}
        self._init_lock = asyncio.Lock()
        self._initialized = False

    @property
    def checkpointer(self) -> AsyncSqliteSaver:
        if self._checkpointer is None:
            raise RuntimeError("GenerationJobService 尚未初始化")
        return self._checkpointer

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            await self._initialize_job_tables()
            self._checkpoint_context = AsyncSqliteSaver.from_conn_string(
                str(self.database_path)
            )
            self._checkpointer = await self._checkpoint_context.__aenter__()
            await self._checkpointer.setup()
            self._initialized = True
            logger.info(f"LangGraph SQLite checkpoint 已启用: {self.database_path}")

    async def startup(self, runner: JobRunner) -> None:
        await self.initialize()
        self._runner = runner
        incomplete = await self.list_running_jobs()
        for job in incomplete:
            self._spawn(job, resume=True)
        if incomplete:
            logger.warning(f"正在恢复 {len(incomplete)} 个未完成 LangGraph 任务")

    async def shutdown(self) -> None:
        tasks = list(self._active_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._active_tasks.clear()
        if self._checkpoint_context is not None:
            await self._checkpoint_context.__aexit__(None, None, None)
        self._checkpoint_context = None
        self._checkpointer = None
        self._runner = None
        self._initialized = False

    async def start_job(self, payload: dict, subscriber: Any) -> tuple[GenerationJob, bool]:
        """创建任务；同一会话已有运行任务时附着旧任务而不重复生成。"""
        await self.initialize()
        request_id = str(payload.get("request_id") or "")
        session_id = str(payload.get("session_id") or request_id)
        if not request_id:
            raise ValueError("request_id 不能为空")

        running = await self.get_running_job_for_session(session_id)
        if running is not None and running.request_id != request_id:
            return running, False

        existing = await self.get_job(request_id)
        if existing is not None:
            return existing, False

        await self._insert_job(request_id, session_id, payload)
        job = GenerationJob(request_id, session_id, dict(payload), "running")
        await self.attach(job.request_id, subscriber)
        self._spawn(job, resume=False)
        return job, True

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
        if job is None:
            job = await self.get_running_job_for_session(session_id)
        if job is None:
            return None

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

    async def publish_event(self, request_id: str, payload: dict) -> None:
        event = dict(payload)
        if event.get("type") in _PERSISTED_EVENT_TYPES:
            lock = self._event_locks.setdefault(request_id, asyncio.Lock())
            async with lock:
                sequence = await self._append_event(request_id, event)
                event["event_seq"] = sequence
                await self._broadcast(request_id, event)
            return
        await self._broadcast(request_id, event)

    async def events_after(self, request_id: str, after_seq: int) -> list[dict]:
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                """SELECT payload_json FROM generation_events
                   WHERE request_id = ? AND seq > ? ORDER BY seq""",
                (request_id, max(0, int(after_seq))),
            )
            rows = await cursor.fetchall()
        return [json.loads(row[0]) for row in rows]

    async def get_job(self, request_id: str | None) -> GenerationJob | None:
        if not request_id:
            return None
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                """SELECT request_id, session_id, payload_json, status,
                          last_event_seq, error
                   FROM generation_jobs WHERE request_id = ?""",
                (request_id,),
            )
            row = await cursor.fetchone()
        return self._row_to_job(row)

    async def get_running_job_for_session(self, session_id: str) -> GenerationJob | None:
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                """SELECT request_id, session_id, payload_json, status,
                          last_event_seq, error
                   FROM generation_jobs
                   WHERE session_id = ? AND status = 'running'
                   ORDER BY updated_at DESC LIMIT 1""",
                (session_id,),
            )
            row = await cursor.fetchone()
        return self._row_to_job(row)

    async def list_running_jobs(self) -> list[GenerationJob]:
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                """SELECT request_id, session_id, payload_json, status,
                          last_event_seq, error
                   FROM generation_jobs WHERE status = 'running'
                   ORDER BY created_at"""
            )
            rows = await cursor.fetchall()
        return [self._row_to_job(row) for row in rows if row is not None]

    def _spawn(self, job: GenerationJob, *, resume: bool) -> asyncio.Task:
        if self._runner is None:
            raise RuntimeError("GenerationJobService runner 尚未配置")
        existing = self._active_tasks.get(job.request_id)
        if existing is not None and not existing.done():
            return existing
        task = asyncio.create_task(
            self._run_job(job, resume=resume),
            name=f"langgraph:{job.request_id}",
        )
        self._active_tasks[job.request_id] = task
        return task

    async def _run_job(self, job: GenerationJob, *, resume: bool) -> None:
        sink = DurableEventSink(self, job.request_id)
        try:
            assert self._runner is not None
            await self._runner(sink, job.payload, resume)
        except asyncio.CancelledError:
            current = await self.get_job(job.request_id)
            current_status = current.status if current is not None else "running"
            logger.info(
                f"[{job.request_id}] 任务随服务关闭暂停，保留 {current_status} 状态"
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
        subscribers = list(self._subscribers.get(request_id, {}).values())
        failed = []
        for subscriber in subscribers:
            try:
                await subscriber.send_json(event)
            except Exception:
                failed.append(subscriber)
        for subscriber in failed:
            await self.detach(subscriber)

    async def _initialize_job_tables(self) -> None:
        async with aiosqlite.connect(self.database_path) as db:
            await db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS generation_jobs (
                    request_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    last_event_seq INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_generation_jobs_session_status
                    ON generation_jobs(session_id, status, updated_at);
                CREATE TABLE IF NOT EXISTS generation_events (
                    request_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (request_id, seq)
                );
            """)
            await db.commit()

    async def _insert_job(
        self,
        request_id: str,
        session_id: str,
        payload: dict,
    ) -> None:
        now = time.time()
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """INSERT INTO generation_jobs
                   (request_id, session_id, payload_json, status,
                    last_event_seq, created_at, updated_at)
                   VALUES (?, ?, ?, 'running', 0, ?, ?)""",
                (
                    request_id,
                    session_id,
                    json.dumps(payload, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            await db.commit()

    async def _append_event(self, request_id: str, payload: dict) -> int:
        now = time.time()
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                "SELECT last_event_seq FROM generation_jobs WHERE request_id = ?",
                (request_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                await db.rollback()
                return 0
            sequence = int(row[0]) + 1
            stored = {**payload, "event_seq": sequence}
            await db.execute(
                """INSERT INTO generation_events
                   (request_id, seq, payload_json, created_at)
                   VALUES (?, ?, ?, ?)""",
                (
                    request_id,
                    sequence,
                    json.dumps(stored, ensure_ascii=False),
                    now,
                ),
            )
            terminal_status = _TERMINAL_EVENT_STATUS.get(payload.get("type"))
            if terminal_status is None:
                await db.execute(
                    """UPDATE generation_jobs
                       SET last_event_seq = ?, updated_at = ?
                       WHERE request_id = ?""",
                    (sequence, now, request_id),
                )
            else:
                await db.execute(
                    """UPDATE generation_jobs
                       SET last_event_seq = ?, status = ?, error = ?, updated_at = ?
                       WHERE request_id = ?""",
                    (
                        sequence,
                        terminal_status,
                        payload.get("error") if terminal_status == "failed" else None,
                        now,
                        request_id,
                    ),
                )
            await db.commit()
        return sequence

    async def _mark_status(
        self,
        request_id: str,
        status: str,
        error: str | None,
    ) -> None:
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """UPDATE generation_jobs
                   SET status = ?, error = ?, updated_at = ? WHERE request_id = ?""",
                (status, error, time.time(), request_id),
            )
            await db.commit()

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
