"""会话、聊天消息与执行轮次 API；存储与并发合并由仓储负责。"""

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse
import app.application.sessions as use_cases

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("")
def list_sessions(request: Request):
    result = use_cases.list_sessions(getattr(request.state, "user", None))
    return JSONResponse(result, headers={'Cache-Control': 'no-store, max-age=0'})


@router.post("")
def create_session(request: Request):
    result = use_cases.create_session(getattr(request.state, "user", None))
    return result


@router.get("/{session_id}")
def get_session(session_id: str):
    result = use_cases.get_session(session_id)
    return result


@router.put("/{session_id}")
def update_session(session_id: str, request: Request, updates: dict=Body(...)):
    result = use_cases.update_session(session_id, getattr(request.state, "user", None), updates)
    return result


@router.delete("/{session_id}")
async def delete_session(session_id: str, request: Request):
    result = await use_cases.delete_session(session_id, getattr(request.state, "user", None))
    return result


@router.get("/{session_id}/messages")
def get_messages(session_id: str):
    result = use_cases.get_messages(session_id)
    return result


@router.post("/{session_id}/messages")
def add_messages(session_id: str, request: Request, body: list[dict] | dict=Body(...)):
    result = use_cases.add_messages(session_id, getattr(request.state, "user", None), body)
    return result


@router.get("/{session_id}/turns")
def get_turns(session_id: str):
    result = use_cases.get_turns(session_id)
    return result


@router.put("/{session_id}/turns")
def replace_turns(session_id: str, request: Request, body: list[dict] | dict=Body(...)):
    result = use_cases.replace_turns(session_id, getattr(request.state, "user", None), body)
    return result

