"""装配域：蓝图分片合并后的确定性归一化、配额控制与修复。

合并节点入口 ``merge_fragments_node`` 见 :mod:`.workflow`（不在此 re-export）。
"""
from __future__ import annotations

from .merge import apply_fixes, deduplicate_balcony_representations

__all__ = ["apply_fixes", "deduplicate_balcony_representations"]
