"""识别已经消费 AI 修改额度的提案，避免应用提案时再扣手工次数。"""

import json

from sqlalchemy import select

from app.domain.blueprint.editing import _apply_patch_to_blueprint
from app.domain.blueprint.parser import normalize_blueprint_input
from app.infrastructure.persistence.repositories.blueprint_changes import (
    content_fingerprint,
)
from app.infrastructure.persistence.repositories.errors import OperationConflict
from app.infrastructure.persistence.schema import events, jobs


def is_verified_ai_edit(
    connection,
    actor: dict,
    session_id: str | None,
    operation_id: str | None,
    before: dict,
    after: dict,
) -> bool:
    if not operation_id or not operation_id.startswith("patch_req_"):
        return False
    request_id = operation_id.removeprefix("patch_")
    row = connection.execute(
        select(jobs.c.session_id, jobs.c.payload_json).where(
            jobs.c.request_id == request_id
        )
    ).first()
    if row is None:
        return False
    request = json.loads(row.payload_json)
    if row.session_id != session_id or request.get("_server_user_id") != actor["id"]:
        raise OperationConflict("AI 提案不属于当前账号或蓝图")
    original = request.get("blueprint")
    if not isinstance(original, dict) or content_fingerprint(
        original
    ) != content_fingerprint(before):
        raise OperationConflict("AI 提案生成后蓝图已变化，请重新发起修改")
    values = connection.execute(
        select(events.c.payload_json)
        .where(events.c.request_id == request_id)
        .order_by(events.c.seq.desc())
    ).scalars()
    for value in values:
        event = json.loads(value)
        if event.get("type") != "patch_proposal":
            continue
        patch = event.get("patch") or {}
        if patch.get("patch_id") != operation_id:
            continue
        expected = _apply_patch_to_blueprint(before, patch)
        _remove_deleted_references(before, expected)
        expected = normalize_blueprint_input(expected)
        if content_fingerprint(expected) != content_fingerprint(after):
            raise OperationConflict("提交内容与服务端记录的 AI 提案不一致")
        return True
    raise OperationConflict("未找到可应用的 AI 修改提案")


def _remove_deleted_references(before: dict, after: dict) -> None:
    removed = set()
    remaining = set()
    for bucket in ("elements", "components"):
        removed.update(
            item["id"]
            for item in before.get("geometry", {}).get(bucket, [])
            if isinstance(item, dict) and item.get("id")
        )
        remaining.update(
            item["id"]
            for item in after.get("geometry", {}).get(bucket, [])
            if isinstance(item, dict) and item.get("id")
        )
    removed -= remaining
    if not removed:
        return
    geometry = after.get("geometry", {})
    if geometry.get("placements"):
        geometry["placements"] = [
            item for item in geometry["placements"] if item.get("id") not in removed
        ]
    physics = (after.get("behaviors") or {}).get("physics") or {}
    if physics.get("constraints"):
        physics["constraints"] = [
            item for item in physics["constraints"] if item.get("target") not in removed
        ]
    groups = (after.get("editor") or {}).get("groups") or {}
    for key, group in list(groups.items()):
        group["elements"] = [
            value for value in group.get("elements", []) if value not in removed
        ]
        if not group["elements"]:
            del groups[key]
