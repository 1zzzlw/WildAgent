"""蓝图锁覆盖整个关联会话，防止改名另存和后台回写绕过锁。"""

from sqlalchemy import select
from sqlalchemy.engine import Connection

from app.infrastructure.persistence.repositories.errors import (
    AccountUnavailable,
    BlueprintLocked,
)
from app.infrastructure.persistence.schema import blueprints, sessions, users


def assert_session_unlocked(connection: Connection, session_id: str | None) -> None:
    if not session_id:
        return
    session = connection.execute(
        select(sessions.c.owner_id)
        .where(sessions.c.session_id == session_id)
        .with_for_update()
    ).first()
    if session and session.owner_id:
        status = connection.scalar(
            select(users.c.status).where(users.c.id == session.owner_id)
        )
        if status != "active":
            raise AccountUnavailable("蓝图所属账号已被停用，不能继续修改")
    locked = connection.execute(
        select(blueprints.c.filename)
        .where(blueprints.c.session_id == session_id, blueprints.c.locked.is_(True))
        .with_for_update()
    ).first()
    if locked:
        raise BlueprintLocked("蓝图已锁定，请管理员解锁后再修改")


def assert_row_unlocked(row: dict | None) -> None:
    if row and row.get("locked"):
        raise BlueprintLocked("蓝图已锁定，请管理员解锁后再修改或删除")
