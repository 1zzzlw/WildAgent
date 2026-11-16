"""统一会话和蓝图归属检查，HTTP 与 WebSocket 共用。"""
from app.application.errors import ApplicationError
from app.infrastructure.persistence.repositories.blueprints import blueprint_repository
from app.infrastructure.persistence.repositories.blueprints import session_for_filename
from app.infrastructure.persistence.repositories.conversations import conversations


def check_owner(owner_id: str | None, user: dict | None) -> None:
    if (user or {}).get("identity") == 2:
        return
    if owner_id is not None and (user or {}).get("id") != owner_id:
        raise ApplicationError('not_found', "资料不存在")


def check_session(session_id: str, user: dict | None) -> None:
    exists, owner = conversations.owner(session_id)
    if exists:
        check_owner(owner, user)


def check_blueprint(filename: str, user: dict | None) -> None:
    row = blueprint_repository.get_metadata(filename)
    if row:
        check_owner(row["owner_id"], user)
    sid = session_for_filename(filename)
    if sid:
        check_session(sid, user)


def require_admin(user: dict | None) -> dict:
    if not user or user.get("role") != "editor" or user.get("identity") != 2:
        raise ApplicationError("forbidden", "此操作需要管理员权限")
    return user


def check_session_writable(session_id: str, user: dict | None) -> None:
    from app.infrastructure.persistence.database import database
    from app.infrastructure.persistence.repositories.locks import assert_session_unlocked

    check_session(session_id, user)
    with database.engine.begin() as connection:
        assert_session_unlocked(connection, session_id)
