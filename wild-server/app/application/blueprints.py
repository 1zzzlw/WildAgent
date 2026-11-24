"""blueprints 业务用例，传输协议由 API 层适配。"""

from collections.abc import Callable

from app.application.errors import ApplicationError
from app.application.access import require_admin
from app.infrastructure.persistence.repositories.activity import public_usage, record_activity
from app.infrastructure.persistence.repositories.accounts import accounts
from app.infrastructure.persistence.repositories.errors import OperationConflict


from app.infrastructure.persistence.repositories.blueprints import blueprint_repository
from app.infrastructure.persistence.repositories.blueprints import validate_filename
from app.infrastructure.persistence.repositories.blueprints import session_for_filename
from app.infrastructure.persistence.repositories.conversations import conversations


def list_scenes(user: dict | None):
    user = user or {}
    return blueprint_repository.list(user.get("id"))


def get_scene(filename: str):
    try:
        row = blueprint_repository.get(filename)
    except ValueError as exc:
        raise ApplicationError('invalid_input', str(exc)) from exc
    if row is None:
        raise ApplicationError('not_found', "蓝图不存在")
    return row["blueprint_json"]


def update_scene(filename: str, user: dict | None, blueprint: dict=None, *,
                 operation_id: str | None = None, label: str = "保存蓝图", base_revision: int | None = None,
                 verify_ai_edit: Callable[..., bool] | None = None):
    if not isinstance(blueprint.get("meta"), dict) or not isinstance(blueprint.get("geometry"), dict):
        raise ApplicationError('invalid_input', "JSON 必须包含 meta 和 geometry 对象")
    try:
        validate_filename(filename)
        user = user or {}
        current = blueprint_repository.get(filename)
        session_id = current["session_id"] if current else session_for_filename(filename)
        owner_id = current["owner_id"] if current else user.get("id")
        if not current and session_id and user.get("identity") == 2:
            exists, session_owner = conversations.owner(session_id)
            if exists:
                owner_id = session_owner
        path = blueprint_repository.save(filename, blueprint, owner_id=owner_id, session_id=session_id,
                                         actor_id=user.get("id"), operation_id=operation_id,
                                         label=label, base_revision=base_revision, verify_ai_edit=verify_ai_edit)
    except OperationConflict:
        raise
    except ValueError as exc:
        raise ApplicationError('invalid_input', str(exc)) from exc
    account = accounts.get(user["id"]) if user.get("id") else None
    return {"status": "ok", "path": path, "usage": public_usage(account) if account else None}


def delete_scene(filename: str, user: dict | None = None):
    actor = require_admin(user)
    try:
        deleted = blueprint_repository.delete(filename)
    except ValueError as exc:
        raise ApplicationError('invalid_input', str(exc)) from exc
    if not deleted:
        raise ApplicationError('not_found', "蓝图不存在")
    record_activity(actor["id"], "blueprint.delete", resource=filename)
    return {"status": "deleted", "filename": filename}
