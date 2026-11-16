"""后台管理用例，账号删除保留数据归属与审计记录。"""

from math import isfinite

from sqlalchemy import select, update

from app.application.access import require_admin
from app.application.blueprints import get_scene
from app.application.errors import ApplicationError
from app.infrastructure.persistence.database import database
from app.infrastructure.persistence.repositories import administration as repository
from app.infrastructure.persistence.repositories.activity import (
    append_audit,
    lock_account,
    public_usage,
)
from app.infrastructure.persistence.repositories.blueprints import validate_filename
from app.infrastructure.persistence.repositories.conversations import now_ms
from app.infrastructure.persistence.schema import blueprints, sessions


def account_summary(account: dict) -> dict:
    return {
        **account,
        "is_admin": account["identity"] == 2,
        "usage": public_usage(account),
    }


def list_users(user: dict, **filters) -> dict:
    require_admin(user)
    result = repository.list_accounts(**filters)
    result["items"] = [account_summary(account) for account in result["items"]]
    return result


def update_user(actor: dict, user_id: str, changes: dict) -> dict:
    require_admin(actor)
    if not changes:
        raise ApplicationError("invalid_input", "请提供需要修改的字段")
    try:
        return account_summary(repository.change_account(actor["id"], user_id, changes))
    except LookupError as exc:
        raise ApplicationError("not_found", str(exc)) from exc


def delete_user(actor: dict, user_id: str) -> dict:
    # 逻辑删除使已有登录立即失效，保留蓝图归属，避免资料意外变成公开内容。
    update_user(actor, user_id, {"status": "deleted"})
    return {"status": "deleted", "user_id": user_id}


def list_blueprints(user: dict, **filters) -> dict:
    require_admin(user)
    return repository.list_blueprints(**filters)


def get_blueprint_metrics(user: dict, filename: str) -> dict:
    require_admin(user)
    return blueprint_metrics(get_scene(filename))


def blueprint_metrics(blueprint: dict) -> dict:
    rectangles = []
    points = []
    for element in (blueprint.get("geometry") or {}).get("elements", []):
        if not isinstance(element, dict):
            continue
        start, end = element.get("from"), element.get("to")
        if not _point(start) or not _point(end):
            continue
        points.extend([start, end])
        if element.get("type") == "floor":
            rectangles.append(
                (
                    min(start[1], end[1]),
                    min(start[0], end[0]),
                    min(start[2], end[2]),
                    max(start[0], end[0]),
                    max(start[2], end[2]),
                )
            )
    if rectangles:
        ground = min(rectangle[0] for rectangle in rectangles)
        footprints = [
            rectangle[1:]
            for rectangle in rectangles
            if abs(rectangle[0] - ground) < 0.01
        ]
        area = _rectangle_union_area(footprints)
        width = max(rectangle[2] for rectangle in footprints) - min(
            rectangle[0] for rectangle in footprints
        )
        depth = max(rectangle[3] for rectangle in footprints) - min(
            rectangle[1] for rectangle in footprints
        )
        area_kind = "floor_union"
    elif points:
        width = max(p[0] for p in points) - min(p[0] for p in points)
        depth = max(p[2] for p in points) - min(p[2] for p in points)
        area, area_kind = width * depth, "bounds"
    else:
        width = depth = area = None
        area_kind = "unavailable"
    return {
        "footprint_area": area,
        "footprint_width": width,
        "footprint_depth": depth,
        "footprint_kind": area_kind,
    }


def _point(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 3
        and all(
            isinstance(number, (int, float))
            and not isinstance(number, bool)
            and isfinite(number)
            for number in value
        )
    )


def _rectangle_union_area(rectangles: list[tuple]) -> float:
    xs = set()
    for left, _, right, _ in rectangles:
        xs.update([left, right])
    xs = sorted(xs)
    area = 0.0
    for left, right in zip(xs, xs[1:]):
        intervals = sorted(
            (bottom, top)
            for x1, bottom, x2, top in rectangles
            if x1 < right and x2 > left
        )
        covered = 0.0
        end = None
        for bottom, top in intervals:
            start = bottom if end is None else max(bottom, end)
            covered += max(0, top - start)
            end = top if end is None else max(end, top)
        area += (right - left) * covered
    return area


def set_blueprint_lock(user: dict, filename: str, locked: bool) -> dict:
    require_admin(user)
    validate_filename(filename)
    with database.engine.begin() as connection:
        actor = lock_account(connection, user["id"])
        require_admin({**actor, "role": "editor"})
        row = connection.execute(
            select(blueprints.c.session_id).where(blueprints.c.filename == filename)
        ).first()
        if not row:
            raise ApplicationError("not_found", "蓝图不存在")
        if row.session_id:
            connection.execute(
                select(sessions.c.session_id)
                .where(sessions.c.session_id == row.session_id)
                .with_for_update()
            ).first()
        current = connection.execute(
            select(blueprints.c.locked)
            .where(blueprints.c.filename == filename)
            .with_for_update()
        ).first()
        if current is None:
            raise ApplicationError("not_found", "蓝图不存在")
        connection.execute(
            update(blueprints)
            .where(blueprints.c.filename == filename)
            .values(
                locked=locked,
                locked_by=actor["id"] if locked else None,
                locked_at=now_ms() if locked else None,
            )
        )
        append_audit(
            connection,
            actor,
            "blueprint.lock" if locked else "blueprint.unlock",
            resource=filename,
            session_id=row.session_id,
            details={"before": bool(current.locked), "locked": locked},
        )
    return {"filename": filename, "locked": locked}
