"""蓝图锁覆盖整个关联会话，防止改名另存和后台回写绕过锁。"""

from sqlalchemy import select
from sqlalchemy.engine import Connection

from app.infrastructure.persistence.repositories.errors import BlueprintLocked
from app.infrastructure.persistence.schema import blueprints, sessions


def assert_session_unlocked(connection: Connection, session_id: str | None) -> None:
    if not session_id:
        return
    connection.execute(
        select(sessions.c.session_id)
        .where(sessions.c.session_id == session_id)
        .with_for_update()
    ).first()
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
