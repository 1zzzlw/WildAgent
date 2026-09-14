"""总体建筑方案、确定性骨架与立面约束的公开 API。"""

from .facade import (
    conform_balconies_to_slots,
    conform_entrance_accessories,
    conform_openings_to_slots,
    conform_railings_to_slots,
    conform_roofs_to_slots,
    resolve_facade_layout,
)
from .planning import (
    normalize_architecture_plan,
    score_architecture_plan,
    select_architecture_plan,
)
from .profile import detect_architecture_profile, resolve_complexity_profile
from .skeleton import build_deterministic_skeleton, evaluate_skeleton_complexity

__all__ = [
    "build_deterministic_skeleton",
    "conform_balconies_to_slots",
    "conform_entrance_accessories",
    "conform_openings_to_slots",
    "conform_railings_to_slots",
    "conform_roofs_to_slots",
    "detect_architecture_profile",
    "evaluate_skeleton_complexity",
    "normalize_architecture_plan",
    "resolve_complexity_profile",
    "resolve_facade_layout",
    "score_architecture_plan",
    "select_architecture_plan",
]
