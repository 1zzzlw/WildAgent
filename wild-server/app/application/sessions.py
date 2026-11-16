"""sessions 业务用例，传输协议由 API 层适配。"""

import asyncio
import re
import time
from uuid import uuid4
from app.application.errors import ApplicationError


from app.infrastructure.persistence.repositories.blueprints import blueprint_repository
from app.infrastructure.persistence.repositories.conversations import conversations
from app.infrastructure.persistence.repositories.jobs import JobRepository
from app.domain.blueprint.parser import compact_blueprint_title


MAX_TURNS_PER_SESSION = 100


def _safe_session_id(session_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
        raise ApplicationError('invalid_input', "无效的 session_id")
    return session_id


def _read_session_meta(session_id: str) -> dict | None:
    return conversations.read(_safe_session_id(session_id))


def _build_session_info(session_id: str, meta: dict, bp: dict | None) -> dict:
    name = str(meta.get("name") or "").strip()
    custom = name if name not in {"", "新建筑", "未命名建筑"} else ""
    return {
        "session_id": session_id, "filename": bp["filename"] if bp else meta.get("filename"),
        "name": custom or compact_blueprint_title(bp["name"] if bp else name),
        "building_type": meta.get("building_type"),
        "created_at": meta.get("created_at", 0), "updated_at": meta.get("updated_at", 0),
        "elements_count": bp["elements_count"] if bp else 0,
        "components_count": bp["components_count"] if bp else 0,
        "message_count": meta.get("message_count", len(meta.get("messages", []))),
        "turn_count": meta.get("turn_count", len(meta.get("turns", []))),
        "status": "saved" if bp else "draft",
        "locked": bool(bp and bp.get("locked")),
    }


def list_sessions(user: dict | None):
    user = user or {}
    metadata = conversations.list(user.get("id"))
    blueprints = blueprint_repository.for_sessions([meta["session_id"] for meta in metadata])
    values = [_build_session_info(meta["session_id"], meta, blueprints.get(meta["session_id"])) for meta in metadata]
    return values


def create_session(user: dict | None):
    sid = f"session_{uuid4().hex}"
    user = user or {}
    conversations.ensure(sid, user.get("id"))
    return {"session_id": sid}


def get_session(session_id: str):
    meta = _read_session_meta(session_id)
    if meta is None:
        raise ApplicationError('not_found', "会话不存在")
    return _build_session_info(session_id, meta, blueprint_repository.for_session(session_id))


def update_session(session_id: str, user: dict | None, updates: dict=None):
    if _read_session_meta(session_id) is None:
        raise ApplicationError('not_found', "会话不存在")
    user = user or {}
    conversations.write(session_id, {key: updates[key] for key in ("name", "building_type") if key in updates}, user.get("id"))
    return {"status": "ok"}


async def delete_session(session_id: str, user: dict | None):
    from app.application.generation.jobs import generation_job_service
    from app.infrastructure.redis.events import session_lock
    from app.application.access import check_session
    _safe_session_id(session_id)
    try:
        async with session_lock(session_id):
            await asyncio.to_thread(check_session, session_id, user)
            bp = await asyncio.to_thread(blueprint_repository.for_session, session_id)
            if bp:
                from app.application.access import require_admin, check_session_writable

                require_admin(user)
                await asyncio.to_thread(check_session_writable, session_id, user)
            await generation_job_service.delete_session_jobs(session_id)
            await asyncio.to_thread(conversations.delete, session_id)
    except ValueError as exc:
        raise ApplicationError('conflict', str(exc)) from exc
    return {"status": "deleted", "session_id": session_id,
            "blueprint_files": [bp["filename"]] if bp else []}


def get_messages(session_id: str):
    return (_read_session_meta(session_id) or {}).get("messages", [])


def add_messages(session_id: str, user: dict | None, body: list[dict] | dict=None):
    _safe_session_id(session_id)
    user = user or {}
    values = body if isinstance(body, list) else [body]
    return {"status": "ok", "message_count": conversations.append_messages(session_id, values, user.get("id"))}


def _normalize_turns(turns: object) -> list[dict]:
    if not isinstance(turns, list):
        return []
    return [dict(value) for value in turns[-MAX_TURNS_PER_SESSION:]
            if isinstance(value, dict) and isinstance(value.get("request_id"), str) and value["request_id"]]


def get_turns(session_id: str):
    values = _normalize_turns((_read_session_meta(session_id) or {}).get("turns", []))
    statuses = JobRepository().statuses(session_id)
    for turn in values:
        if turn.get("status") == "running":
            status = statuses.get(turn["request_id"])
            if status not in {"running", "waiting_review"}:
                turn["status"] = {"completed": "done", "stopped": "stopped"}.get(status, "error")
                turn["completed_at"] = turn.get("completed_at") or int(time.time() * 1000)
                turn["thinking_status"] = "completed" if status == "completed" else "error"
                if status is None:
                    turn["interruption_reason"] = "未找到可恢复的生成任务"
    return values


def replace_turns(session_id: str, user: dict | None, body: list[dict] | dict=None):
    _safe_session_id(session_id)
    raw = body.get("turns", []) if isinstance(body, dict) else body
    turns = _normalize_turns(raw)
    deduplicated = {turn["request_id"]: turn for turn in turns}
    values = list(deduplicated.values())[-MAX_TURNS_PER_SESSION:]
    user = user or {}
    conversations.write(session_id, {"turns": values}, user.get("id"))
    return {"status": "ok", "turn_count": len(values)}
