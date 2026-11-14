"""统一会话和蓝图归属检查，HTTP 与 WebSocket 共用。"""
from fastapi import HTTPException

from app.repositories.blueprints import blueprint_repository, session_for_filename
from app.repositories.conversations import conversations


def check_owner(owner_id: str | None, user: dict | None) -> None:
    if owner_id is not None and (user or {}).get("id") != owner_id:
        raise HTTPException(status_code=404, detail="资料不存在")


def check_session(session_id: str, user: dict | None) -> None:
    exists, owner = conversations.owner(session_id)
    if exists:
        check_owner(owner, user)


def check_blueprint(filename: str, user: dict | None) -> None:
    row = blueprint_repository.get(filename)
    if row:
        check_owner(row["owner_id"], user)
    sid = session_for_filename(filename)
    if sid:
        check_session(sid, user)
