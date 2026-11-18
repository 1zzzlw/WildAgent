from __future__ import annotations

from time import time
from uuid import uuid4

from sqlalchemy import delete, func, insert, select, true, update
from sqlalchemy.exc import IntegrityError

from app.infrastructure.persistence.database import database
from app.infrastructure.persistence.schema import messages
from app.infrastructure.persistence.schema import sessions
from app.infrastructure.persistence.schema import turns


def now_ms() -> int:
    return int(time() * 1000)


def visible_to(column, user_id: str | None):
    """登录账号共享全部资料；访客仍只读取历史公共资料。"""
    return true() if user_id else column.is_(None)


def ensure_session(conn, session_id: str, owner_id: str | None = None) -> dict:
    row = conn.execute(select(sessions).where(sessions.c.session_id == session_id).with_for_update()).mappings().first()
    if row is None:
        now = now_ms()
        try:
            with conn.begin_nested():
                conn.execute(insert(sessions).values(session_id=session_id, owner_id=owner_id,
                    metadata_json={"name": "新建筑"}, created_at=now, updated_at=now))
        except IntegrityError:
            pass  # 另一请求刚创建了相同会话，重新加锁读取，保留已经确定的归属。
        row = conn.execute(select(sessions).where(sessions.c.session_id == session_id).with_for_update()).mappings().one()
    return dict(row)


class ConversationRepository:
    def ensure(self, session_id: str, owner_id: str | None = None) -> None:
        with database.engine.begin() as conn:
            ensure_session(conn, session_id, owner_id)

    def owner(self, session_id: str) -> tuple[bool, str | None]:
        with database.engine.connect() as conn:
            row = conn.execute(select(sessions.c.owner_id).where(sessions.c.session_id == session_id)).first()
            return (row is not None, row[0] if row else None)

    def read(self, session_id: str) -> dict | None:
        with database.engine.connect() as conn:
            row = conn.execute(select(sessions).where(sessions.c.session_id == session_id)).mappings().first()
            if row is None:
                return None
            result = {**row["metadata_json"], "session_id": session_id,
                      "created_at": row["created_at"], "updated_at": row["updated_at"]}
            for key, table in (("messages", messages), ("turns", turns)):
                result[key] = list(conn.execute(select(table.c.payload_json).where(
                    table.c.session_id == session_id).order_by(table.c.position)).scalars())
            return result

    def list(self, user_id: str | None) -> list[dict]:
        message_counts = select(messages.c.session_id, func.count().label("count")).group_by(messages.c.session_id).subquery()
        turn_counts = select(turns.c.session_id, func.count().label("count")).group_by(turns.c.session_id).subquery()
        with database.engine.connect() as conn:
            rows = conn.execute(select(sessions, message_counts.c.count.label("message_count"),
                turn_counts.c.count.label("turn_count")).outerjoin(message_counts,
                sessions.c.session_id == message_counts.c.session_id).outerjoin(turn_counts,
                sessions.c.session_id == turn_counts.c.session_id).where(visible_to(sessions.c.owner_id, user_id))
                .order_by(sessions.c.updated_at.desc())).mappings()
            return [{**row["metadata_json"], "session_id": row["session_id"], "created_at": row["created_at"],
                     "updated_at": row["updated_at"], "message_count": row["message_count"] or 0,
                     "turn_count": row["turn_count"] or 0} for row in rows]

    @staticmethod
    def _replace(conn, table, session_id: str, values: list[dict]) -> None:
        conn.execute(delete(table).where(table.c.session_id == session_id))
        key = "message_id" if table is messages else "request_id"
        records = []
        seen = set()
        for position, value in enumerate(values):
            identity = str(value.get("id" if table is messages else "request_id") or uuid4())
            if identity in seen:
                continue
            if len(identity) > 128:
                raise ValueError("消息或执行轮次标识过长")
            seen.add(identity)
            records.append({"session_id": session_id, key: identity,
                            "position": position, "payload_json": value})
        if records:
            conn.execute(insert(table), records)

    def write(self, session_id: str, data: dict, owner_id: str | None = None) -> None:
        from app.infrastructure.persistence.repositories.locks import assert_session_unlocked

        with database.engine.begin() as conn:
            current = ensure_session(conn, session_id, owner_id)
            if any(key in data for key in ("name", "building_type", "filename")):
                assert_session_unlocked(conn, session_id)
            meta = {key: value for key, value in data.items() if key not in {
                "messages", "turns", "session_id", "owner_id", "created_at", "updated_at"}}
            conn.execute(update(sessions).where(sessions.c.session_id == session_id).values(
                metadata_json={**current["metadata_json"], **meta}, updated_at=data.get("updated_at", now_ms()),
                created_at=data.get("created_at", current["created_at"])))
            for key, table in (("messages", messages), ("turns", turns)):
                if key in data:
                    self._replace(conn, table, session_id, data[key])

    def append_messages(self, session_id: str, values: list[dict], owner_id: str) -> int:
        with database.engine.begin() as conn:
            ensure_session(conn, session_id, owner_id)
            existing = list(conn.execute(select(messages.c.payload_json).where(
                messages.c.session_id == session_id).order_by(messages.c.position)).scalars())
            ids = {item.get("id") for item in existing if item.get("id")}
            for value in values:
                if not value.get("id") or value["id"] not in ids:
                    existing.append(value)
                    if value.get("id"):
                        ids.add(value["id"])
            self._replace(conn, messages, session_id, existing)
            conn.execute(update(sessions).where(sessions.c.session_id == session_id).values(updated_at=now_ms()))
            return len(existing)

    def sync_turns(self, session_id: str, values: list[dict], owner_id: str | None, limit: int) -> int:
        """在同一会话行锁下合并快照，保留其他账号的请求及已完成状态。"""
        with database.engine.begin() as conn:
            ensure_session(conn, session_id, owner_id)
            existing = conn.execute(select(turns.c.payload_json).where(
                turns.c.session_id == session_id).order_by(turns.c.position)).scalars()
            merged = {}
            for value in existing:
                if isinstance(value.get("request_id"), str) and value["request_id"]:
                    merged[value["request_id"]] = value
            for value in values:
                previous = merged.get(value["request_id"], {})
                if (previous.get("status") in {"completed", "done", "error", "stopped"}
                        and value.get("status") in {"running", "waiting_review"}):
                    continue
                merged[value["request_id"]] = {**previous, **value}
            records = list(merged.values())
            records.sort(key=lambda turn: turn.get("started_at") if type(turn.get("started_at")) in (int, float) else 0)
            records = records[-limit:]
            self._replace(conn, turns, session_id, records)
            conn.execute(update(sessions).where(sessions.c.session_id == session_id).values(updated_at=now_ms()))
            return len(records)

    def delete(self, session_id: str) -> None:
        from app.infrastructure.persistence.repositories.locks import assert_session_unlocked

        with database.engine.begin() as conn:
            assert_session_unlocked(conn, session_id)
            conn.execute(delete(sessions).where(sessions.c.session_id == session_id))


conversations = ConversationRepository()
