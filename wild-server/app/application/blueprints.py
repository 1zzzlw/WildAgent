"""blueprints 业务用例，传输协议由 API 层适配。"""

from app.application.errors import ApplicationError


from app.infrastructure.persistence.repositories.blueprints import blueprint_repository
from app.infrastructure.persistence.repositories.blueprints import validate_filename


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


def update_scene(filename: str, user: dict | None, blueprint: dict=None):
    if not isinstance(blueprint.get("meta"), dict) or not isinstance(blueprint.get("geometry"), dict):
        raise ApplicationError('invalid_input', "JSON 必须包含 meta 和 geometry 对象")
    try:
        validate_filename(filename)
        user = user or {}
        path = blueprint_repository.save(filename, blueprint, owner_id=user.get("id"))
    except ValueError as exc:
        raise ApplicationError('invalid_input', str(exc)) from exc
    return {"status": "ok", "path": path}


def delete_scene(filename: str):
    try:
        deleted = blueprint_repository.delete(filename)
    except ValueError as exc:
        raise ApplicationError('invalid_input', str(exc)) from exc
    if not deleted:
        raise ApplicationError('not_found', "蓝图不存在")
    return {"status": "deleted", "filename": filename}
