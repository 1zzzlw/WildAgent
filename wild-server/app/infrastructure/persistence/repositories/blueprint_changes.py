"""从实际保存内容生成有限大小的修改证据。"""

from copy import deepcopy

from app.infrastructure.persistence.repositories.activity import fingerprint


def content_fingerprint(blueprint: dict) -> str:
    value = deepcopy(blueprint)
    editor = value.get("editor")
    if isinstance(editor, dict):
        editor.pop("revision", None)
        if not editor:
            value.pop("editor")
    geometry = value.get("geometry")
    if isinstance(geometry, dict):
        geometry.setdefault("components", [])
    return fingerprint(value)


def describe_changes(before: dict, after: dict) -> dict:
    changes = []
    total = 0
    for bucket in ("elements", "components"):
        old = {
            item.get("id"): item
            for item in (before.get("geometry") or {}).get(bucket, [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        new = {
            item.get("id"): item
            for item in (after.get("geometry") or {}).get(bucket, [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        for entity_id in sorted(set(old) | set(new)):
            if old.get(entity_id) == new.get(entity_id):
                continue
            total += 1
            if len(changes) >= 100:
                continue
            previous, current = old.get(entity_id, {}), new.get(entity_id, {})
            fields = sorted(
                key
                for key in set(previous) | set(current)
                if previous.get(key) != current.get(key)
            )
            operation = "update"
            if not previous:
                operation = "add"
            elif not current:
                operation = "remove"
            changes.append(
                {
                    "id": entity_id,
                    "bucket": bucket,
                    "operation": operation,
                    "fields": fields,
                    "before": _brief_values(previous, fields),
                    "after": _brief_values(current, fields),
                }
            )
    sections = []
    for name in (
        "meta",
        "geometry",
        "materials",
        "assets",
        "behaviors",
        "templates",
        "instances",
        "placements",
        "editor",
    ):
        if before.get(name) != after.get(name):
            sections.append(name)
    return {
        "changed_entities": total,
        "entities": changes,
        "sections": sections,
        "truncated": total > len(changes),
    }


def _brief_values(entity: dict, fields: list[str]) -> dict:
    values = {}
    for name in fields[:24]:
        value = entity.get(name)
        if isinstance(value, str) and len(value) > 512:
            value = value[:512] + "…"
        if isinstance(value, (list, dict)) and len(str(value)) > 2048:
            value = {"summary": "内容较大，仅记录字段变化"}
        values[name] = value
    return values
