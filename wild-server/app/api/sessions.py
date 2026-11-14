"""会话、聊天消息与执行轮次 API；存储与并发合并由仓储负责。"""
import asyncio
import re
import time
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse

from app.repositories.blueprints import blueprint_repository
from app.repositories.conversations import conversations
from app.repositories.jobs import JobRepository
from app.utils.blueprint_parser import compact_blueprint_title

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
MAX_TURNS_PER_SESSION = 100


def _safe_session_id(session_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
        raise HTTPException(status_code=400, detail="无效的 session_id")
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
    }


@router.get("")
def list_sessions(request: Request):
    user = getattr(request.state, "user", None) or {}
    metadata = conversations.list(user.get("id"))
    blueprints = blueprint_repository.for_sessions([meta["session_id"] for meta in metadata])
    values = [_build_session_info(meta["session_id"], meta, blueprints.get(meta["session_id"])) for meta in metadata]
    return JSONResponse(values, headers={"Cache-Control": "no-store, max-age=0"})


@router.post("")
def create_session(request: Request):
    sid = f"session_{uuid4().hex}"
    user = getattr(request.state, "user", None) or {}
    conversations.ensure(sid, user.get("id"))
    return {"session_id": sid}


@router.get("/{session_id}")
def get_session(session_id: str):
    meta = _read_session_meta(session_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return _build_session_info(session_id, meta, blueprint_repository.for_session(session_id))


@router.put("/{session_id}")
def update_session(session_id: str, request: Request, updates: dict = Body(...)):
    if _read_session_meta(session_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    user = getattr(request.state, "user", None) or {}
    conversations.write(session_id, {key: updates[key] for key in ("name", "building_type") if key in updates}, user.get("id"))
    return {"status": "ok"}


@router.delete("/{session_id}")
async def delete_session(session_id: str, request: Request):
    from app.services.generation_job_service import generation_job_service
    from app.infrastructure.realtime import session_lock
    from app.services.access_service import check_session
    _safe_session_id(session_id)
    try:
        async with session_lock(session_id):
            await asyncio.to_thread(check_session, session_id, getattr(request.state, "user", None))
            await generation_job_service.delete_session_jobs(session_id)
            bp = await asyncio.to_thread(blueprint_repository.for_session, session_id)
            await asyncio.to_thread(conversations.delete, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "deleted", "session_id": session_id,
            "blueprint_files": [bp["filename"]] if bp else []}


@router.get("/{session_id}/messages")
def get_messages(session_id: str):
    return (_read_session_meta(session_id) or {}).get("messages", [])


@router.post("/{session_id}/messages")
def add_messages(session_id: str, request: Request, body: list[dict] | dict = Body(...)):
    _safe_session_id(session_id)
    user = getattr(request.state, "user", None) or {}
    values = body if isinstance(body, list) else [body]
    return {"status": "ok", "message_count": conversations.append_messages(session_id, values, user.get("id"))}


def _normalize_turns(turns: object) -> list[dict]:
    if not isinstance(turns, list):
        return []
    return [dict(value) for value in turns[-MAX_TURNS_PER_SESSION:]
            if isinstance(value, dict) and isinstance(value.get("request_id"), str) and value["request_id"]]


@router.get("/{session_id}/turns")
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


@router.put("/{session_id}/turns")
def replace_turns(session_id: str, request: Request, body: list[dict] | dict = Body(...)):
    _safe_session_id(session_id)
    raw = body.get("turns", []) if isinstance(body, dict) else body
    turns = _normalize_turns(raw)
    deduplicated = {turn["request_id"]: turn for turn in turns}
    values = list(deduplicated.values())[-MAX_TURNS_PER_SESSION:]
    user = getattr(request.state, "user", None) or {}
    conversations.write(session_id, {"turns": values}, user.get("id"))
    return {"status": "ok", "turn_count": len(values)}
