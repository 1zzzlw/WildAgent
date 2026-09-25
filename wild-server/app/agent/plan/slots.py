"""兼容入口；槽位契约位于不依赖 plan 包初始化的公共模块。"""

from app.agent.generation.slot_utils import (
    component_slots,
    slot_batch_summary,
    slot_counts,
    slot_ids_for,
)

__all__ = ["component_slots", "slot_batch_summary", "slot_counts", "slot_ids_for"]
