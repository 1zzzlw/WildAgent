from __future__ import annotations

import json

from sqlalchemy import JSON, delete, insert, select, type_coerce, update

from app.infrastructure.persistence.database import Database
from app.infrastructure.persistence.database import database
from app.infrastructure.persistence.schema import events
from app.infrastructure.persistence.schema import jobs
from app.infrastructure.persistence.repositories.conversations import now_ms

ACTIVE = ("running", "waiting_review")
JOB_COLUMNS = [jobs.c[name] for name in ("request_id", "session_id", "payload_json", "status", "last_event_seq", "error")]


class JobRepository:
    def __init__(self, db: Database = database):
        self.database = db

    def get(self, request_id: str):
        with self.database.engine.connect() as conn:
            return conn.execute(select(*JOB_COLUMNS).where(jobs.c.request_id == request_id)).first()

    def statuses(self, session_id: str) -> dict[str, str]:
        with self.database.engine.connect() as conn:
            return dict(conn.execute(select(jobs.c.request_id, jobs.c.status)
                        .where(jobs.c.session_id == session_id)).all())

    def active(self, session_id: str, statuses=ACTIVE):
        with self.database.engine.connect() as conn:
            return conn.execute(select(*JOB_COLUMNS).where(jobs.c.session_id == session_id,
                jobs.c.status.in_(statuses)).order_by(jobs.c.updated_at.desc()).limit(1)).first()

    def list(self, statuses=ACTIVE):
        with self.database.engine.connect() as conn:
            return conn.execute(select(*JOB_COLUMNS).where(jobs.c.status.in_(statuses))
                                .order_by(jobs.c.created_at)).all()

    def active_for_account(self, user_id: str):
        actor = type_coerce(jobs.c.payload_json, JSON)["_server_user_id"].as_string()
        with self.database.engine.connect() as connection:
            return connection.execute(select(*JOB_COLUMNS).where(
                jobs.c.status.in_(ACTIVE), actor == user_id).order_by(jobs.c.created_at)).all()

    def insert(self, request_id: str, session_id: str, payload: dict):
        with self.database.engine.begin() as conn:
            conn.execute(insert(jobs).values(request_id=request_id, session_id=session_id,
                payload_json=json.dumps(payload, ensure_ascii=False), status="running",
                last_event_seq=0, created_at=now_ms(), updated_at=now_ms()))

    def append(self, request_id: str, payload: dict, terminal_status: str | None) -> int:
        with self.database.engine.begin() as conn:
            row = conn.execute(select(jobs.c.last_event_seq, jobs.c.status, jobs.c.payload_json).where(
                jobs.c.request_id == request_id).with_for_update()).first()
            if row is None or (row.status == "stopped" and payload.get("type") != "generation_stopped"):
                return 0
            seq = row.last_event_seq + 1
            conn.execute(insert(events).values(request_id=request_id, seq=seq,
                payload_json=json.dumps({**payload, "event_seq": seq}, ensure_ascii=False), created_at=now_ms()))
            changes = dict(last_event_seq=seq, updated_at=now_ms())
            if terminal_status:
                changes.update(status=terminal_status, error=(payload.get("error") or payload.get("content"))
                               if terminal_status == "failed" else None)
            conn.execute(update(jobs).where(jobs.c.request_id == request_id).values(**changes))
            self._record_result(conn, request_id, seq, json.loads(row.payload_json), payload)
            return seq

    @staticmethod
    def _record_result(conn, request_id: str, sequence: int, request: dict, payload: dict) -> None:
        from app.infrastructure.persistence.repositories.activity import append_audit
        from app.infrastructure.persistence.schema import users

        action = payload.get("type")
        if action not in {"agent_reply", "error", "generation_stopped", "blueprint_generated", "patch_proposal"}:
            return
        user_id = request.get("_server_user_id")
        if not user_id:
            return
        actor = conn.execute(select(users.c.id, users.c.username).where(users.c.id == user_id)).mappings().first()
        if not actor:
            return
        details = {"content": str(payload.get("content") or payload.get("error") or "")[:12000]}
        if action == "patch_proposal":
            patch = payload.get("patch") or {}
            details.update(summary=patch.get("summary"), operation_count=len(patch.get("operations") or []))
        if payload.get("filename"):
            details["filename"] = payload["filename"]
        append_audit(conn, dict(actor), "ai." + action, session_id=request.get("session_id"),
                     request_id=request_id, details=details, key=f"ai.event:{request_id}:{sequence}")

    def mark(self, request_id: str, status: str, error: str | None):
        with self.database.engine.begin() as conn:
            conn.execute(update(jobs).where(jobs.c.request_id == request_id, jobs.c.status != "stopped")
                         .values(status=status, error=error, updated_at=now_ms()))

    def events_after(self, request_id: str, after_seq: int) -> list[dict]:
        with self.database.engine.connect() as conn:
            values = conn.execute(select(events.c.payload_json).where(events.c.request_id == request_id,
                events.c.seq > max(0, after_seq)).order_by(events.c.seq)).scalars()
            return [json.loads(value) for value in values]

    def delete_session(self, session_id: str) -> list[str]:
        with self.database.engine.begin() as conn:
            values = conn.execute(select(jobs.c.request_id, jobs.c.status).where(
                jobs.c.session_id == session_id).with_for_update()).all()
            if any(row.status in ACTIVE for row in values):
                raise ValueError("该会话仍有生成任务，请先停止任务再删除")
            ids = [row.request_id for row in values]
            if ids:
                conn.execute(delete(events).where(events.c.request_id.in_(ids)))
                conn.execute(delete(jobs).where(jobs.c.request_id.in_(ids)))
            return ids
