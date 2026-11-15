"""设计清单槽位的通用读取与批次摘要。"""

from __future__ import annotations

from typing import Any


def component_slots(design_brief: Any, kind: str | None = None) -> list[dict[str, Any]]:
    """读取所有 ``*_slots`` 集合，不绑定门窗或其它具体构件名。"""

    if not isinstance(design_brief, dict):
        return []
    found: list[dict[str, Any]] = []
    for collection_name, raw_slots in design_brief.items():
        if not collection_name.endswith("_slots") or not isinstance(raw_slots, list):
            continue
        inferred_kind = collection_name.removesuffix("_slots")
        for raw_slot in raw_slots:
            if not isinstance(raw_slot, dict):
                continue
            # opening_slots 是多类型容器，必须读取条目里的 type；其它命名槽位集合
            # 由集合名确定构件类型，避免条目内部的样式 type 被误当成构件 kind。
            slot_kind = str(
                raw_slot.get("type") if inferred_kind == "opening" else inferred_kind
            ).strip()
            if not slot_kind or slot_kind == "opening":
                continue
            if kind is None or slot_kind == kind:
                found.append({**raw_slot, "type": slot_kind})
    return found


def slot_ids_for(design_brief: Any, kind: str) -> list[str]:
    return sorted(
        str(slot["id"])
        for slot in component_slots(design_brief, kind)
        if isinstance(slot.get("id"), str) and slot["id"]
    )


def slot_counts(design_brief: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for slot in component_slots(design_brief):
        kind = str(slot["type"])
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def slot_batch_summary(design_brief: Any) -> dict[str, Any]:
    """按构件类型与关键尺寸聚合，供模型判断批量与并发策略。"""

    grouped: dict[str, dict[tuple[str, ...], int]] = {}
    for slot in component_slots(design_brief):
        kind = str(slot["type"])
        signature = tuple(
            str(slot.get(field) if slot.get(field) is not None else "?")
            for field in ("width", "height", "depth", "span")
        )
        variants = grouped.setdefault(kind, {})
        variants[signature] = variants.get(signature, 0) + 1
    return {
        kind: {
            "total": sum(variants.values()),
            "variants": [
                {
                    "width": signature[0],
                    "height": signature[1],
                    "depth": signature[2],
                    "span": signature[3],
                    "count": count,
                }
                for signature, count in sorted(variants.items())
            ],
        }
        for kind, variants in sorted(grouped.items())
    }


__all__ = ["component_slots", "slot_batch_summary", "slot_counts", "slot_ids_for"]
