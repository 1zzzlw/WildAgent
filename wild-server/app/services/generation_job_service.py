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
    "floor_plan_ready",
    "floor_plan_review_required",
    "execution_plan_ready",
    "execution_plan_review_required",
    "execution_feedback_queued",
    "style_review_required",
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


class GenerationPaused(Exception):
    """LangGraph 已持久化暂停点，等待用户输入；不是失败。"""


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
    """让快速与精密模式的图任务独立于任意一条 WebSocket 连接。"""

    def __init__(self, database_path: Path = DEFAULT_CHECKPOINT_PATH):
        self.database_path = Path(database_path)
        self._checkpoint_context = None
        self._checkpointer: AsyncSqliteSaver | None = None
        self._runner: JobRunner | None = None
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._subscribers: dict[str, dict[int, Any]] = {}
        self._event_locks: dict[str, asyncio.Lock] = {}
        self._payload_locks: dict[str, asyncio.Lock] = {}
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

        active = await self.get_active_job_for_session(session_id)
        if active is not None and active.request_id != request_id:
            return active, False

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
            job = await self.get_active_job_for_session(session_id)
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

    async def submit_floor_plan_review(
        self,
        subscriber: Any,
        *,
        request_id: str,
        session_id: str,
        action: str,
        feedback: str = "",
    ) -> GenerationJob:
        """提交平面确认或修改意见，并从持久化 interrupt 继续。"""

        await self.initialize()
        job = await self.get_job(request_id)
        if job is None or job.session_id != session_id:
            raise ValueError("找不到对应的平面审核任务")
        if job.status != "waiting_review":
            raise ValueError("当前任务不在平面审核阶段")
        waiting_type = str(job.payload.get("_waiting_review_type") or "floor_plan")
        if waiting_type != "floor_plan":
            raise ValueError("当前等待的是风格审核，不是平面审核")
        action = str(action).lower()
        feedback = str(feedback).strip()
        if action not in {"confirm", "revise"}:
            raise ValueError("平面审核 action 只能是 confirm 或 revise")
        if action == "revise" and not feedback:
            raise ValueError("提交修改时必须填写具体修改意见")
        payload = dict(job.payload)
        payload["_floor_plan_review"] = {"action": action, "feedback": feedback}
        await self._update_payload_and_status(request_id, payload, "running")
        resumed = GenerationJob(
            request_id=request_id,
            session_id=session_id,
            payload=payload,
            status="running",
            last_event_seq=job.last_event_seq,
        )
        await self.attach(request_id, subscriber)
        active = self._active_tasks.get(request_id)
        if active is not None and not active.done():
            async def resume_after_pause() -> None:
                await asyncio.gather(active, return_exceptions=True)
                latest = await self.get_job(request_id)
                if latest is not None and latest.status == "running":
                    self._spawn(latest, resume=True)

            asyncio.create_task(
                resume_after_pause(),
                name=f"langgraph-review-resume:{request_id}",
            )
        else:
            self._spawn(resumed, resume=True)
        return resumed

    async def submit_style_review(
        self,
        subscriber: Any,
        *,
        request_id: str,
        session_id: str,
        action: str,
        style_package_id: str = "",
        feedback: str = "",
    ) -> GenerationJob:
        """提交第二次风格确认，并从 style_review interrupt 继续。"""

        await self.initialize()
        job = await self.get_job(request_id)
        if job is None or job.session_id != session_id:
            raise ValueError("找不到对应的风格审核任务")
        if job.status != "waiting_review":
            raise ValueError("当前任务不在风格审核阶段")
        if str(job.payload.get("_waiting_review_type") or "") != "style":
            raise ValueError("当前等待的是平面审核，不是风格审核")
        action = str(action).lower()
        feedback = str(feedback).strip()
        style_package_id = str(style_package_id).strip().lower()
        if action not in {"confirm", "revise"}:
            raise ValueError("风格审核 action 只能是 confirm 或 revise")
        if action == "confirm" and not style_package_id:
            raise ValueError("确认风格时必须选择一个风格包")
        if action == "confirm":
            from app.agent.plan2build.style_registry import style_registry

            style_registry.get(style_package_id)
        if action == "revise" and not feedback:
            raise ValueError("修改风格时必须填写具体意见")
        payload = dict(job.payload)
        payload["_style_review"] = {
            "action": action,
            "style_package_id": style_package_id,
            "feedback": feedback,
        }
        await self._update_payload_and_status(request_id, payload, "running")
        resumed = GenerationJob(
            request_id=request_id,
            session_id=session_id,
            payload=payload,
            status="running",
            last_event_seq=job.last_event_seq,
        )
        await self.attach(request_id, subscriber)
        active = self._active_tasks.get(request_id)
        if active is not None and not active.done():
            async def resume_after_pause() -> None:
                await asyncio.gather(active, return_exceptions=True)
                latest = await self.get_job(request_id)
                if latest is not None and latest.status == "running":
                    self._spawn(latest, resume=True)

            asyncio.create_task(
                resume_after_pause(),
                name=f"langgraph-style-review-resume:{request_id}",
            )
        else:
            self._spawn(resumed, resume=True)
        return resumed

    async def submit_execution_plan_review(
        self,
        subscriber: Any,
        *,
        request_id: str,
        session_id: str,
        action: str,
        feedback: str = "",
    ) -> GenerationJob:
        """批准或要求修改执行计划，并从持久化 interrupt 继续。"""

        await self.initialize()
        job = await self.get_job(request_id)
        if job is None or job.session_id != session_id:
            raise ValueError("找不到对应的执行计划审核任务")
        if job.status != "waiting_review":
            raise ValueError("当前任务不在执行计划审核阶段")
        if str(job.payload.get("_waiting_review_type") or "") != "execution_plan":
            raise ValueError("当前等待的不是执行计划审核")
        action = str(action).lower()
        feedback = str(feedback).strip()
        if action not in {"confirm", "revise"}:
            raise ValueError("执行计划审核 action 只能是 confirm 或 revise")
        if action == "revise" and not feedback:
            raise ValueError("要求修改计划时必须填写具体意见")
        payload = dict(job.payload)
        payload["_execution_plan_review"] = {
            "action": action,
            "feedback": feedback,
        }
        await self._update_payload_and_status(request_id, payload, "running")
        resumed = GenerationJob(
            request_id=request_id,
            session_id=session_id,
            payload=payload,
            status="running",
            last_event_seq=job.last_event_seq,
        )
        await self.attach(request_id, subscriber)
        active = self._active_tasks.get(request_id)
        if active is not None and not active.done():
            async def resume_after_pause() -> None:
                await asyncio.gather(active, return_exceptions=True)
                latest = await self.get_job(request_id)
                if latest is not None and latest.status == "running":
                    self._spawn(latest, resume=True)

            asyncio.create_task(
                resume_after_pause(),
                name=f"langgraph-plan-review-resume:{request_id}",
            )
        else:
            self._spawn(resumed, resume=True)
        return resumed

    async def queue_execution_feedback(
        self,
        *,
        request_id: str,
        session_id: str,
        feedback: str,
    ) -> int:
        """在计划步骤运行期间持久化用户意见，由下一节点边界吸收。"""

        await self.initialize()
        feedback = str(feedback).strip()
        if not feedback:
            raise ValueError("运行中修改意见不能为空")
        lock = self._payload_locks.setdefault(request_id, asyncio.Lock())
        async with lock:
            job = await self.get_job(request_id)
            if job is None or job.session_id != session_id:
                raise ValueError("找不到对应的计划任务")
            if job.status != "running" or job.payload.get("plan_mode") is not True:
                raise ValueError("当前没有可接收意见的运行中计划")
            payload = dict(job.payload)
            pending = [
                str(item) for item in payload.get("_pending_execution_feedback", [])
                if str(item).strip()
            ]
            pending.append(feedback[:2000])
            payload["_pending_execution_feedback"] = pending
            await self._update_payload_and_status(request_id, payload, "running")
            queued_count = len(pending)
        await self.publish_event(request_id, versioned_event({
            "type": "execution_feedback_queued",
            "request_id": request_id,
            "session_id": session_id,
            "queued_count": queued_count,
        }))
        return queued_count

    async def drain_execution_feedback(self, request_id: str) -> list[str]:
        """原子取出并清空当前已排队意见。"""

        lock = self._payload_locks.setdefault(request_id, asyncio.Lock())
        async with lock:
            job = await self.get_job(request_id)
            if job is None:
                return []
            payload = dict(job.payload)
            pending = [
                str(item).strip()
                for item in payload.get("_pending_execution_feedback", [])
                if str(item).strip()
            ]
            if not pending:
                return []
            payload["_pending_execution_feedback"] = []
            await self._update_payload_and_status(request_id, payload, job.status)
            return pending

    async def mark_waiting_for_review(
        self,
        request_id: str,
        review_type: str = "floor_plan",
    ) -> None:
        """在向客户端暴露审核按钮前落库，消除快速点击产生的竞态。"""

        job = await self.get_job(request_id)
        if job is None:
            raise ValueError("找不到待审核任务")
        payload = dict(job.payload)
        payload["_waiting_review_type"] = review_type
        await self._update_payload_and_status(request_id, payload, "waiting_review")

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

    async def get_active_job_for_session(self, session_id: str) -> GenerationJob | None:
        """同一会话的运行或待审核任务都视为活动任务。"""

        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                """SELECT request_id, session_id, payload_json, status,
                          last_event_seq, error
                   FROM generation_jobs
                   WHERE session_id = ? AND status IN ('running', 'waiting_review')
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
        except GenerationPaused:
            current = await self.get_job(job.request_id)
            review_already_submitted = (
                current is not None
                and current.status == "running"
                and (
                    isinstance(current.payload.get("_floor_plan_review"), dict)
                    or isinstance(current.payload.get("_style_review"), dict)
                    or isinstance(current.payload.get("_execution_plan_review"), dict)
                )
            )
            if not review_already_submitted:
                await self._mark_status(job.request_id, "waiting_review", None)
            logger.info(f"[{job.request_id}] 生成流程已暂停，等待用户审核")
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

    async def _update_payload_and_status(
        self,
        request_id: str,
        payload: dict,
        status: str,
    ) -> None:
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """UPDATE generation_jobs
                   SET payload_json = ?, status = ?, error = NULL, updated_at = ?
                   WHERE request_id = ?""",
                (json.dumps(payload, ensure_ascii=False), status, time.time(), request_id),
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
