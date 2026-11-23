"""总体建筑方案、确定性骨架与立面约束的公开 API。"""

from app.domain.design.architecture.facade import conform_balconies_to_slots
from app.domain.design.architecture.facade import conform_entrance_accessories
from app.domain.design.architecture.facade import conform_openings_to_slots
from app.domain.design.architecture.facade import conform_railings_to_slots
from app.domain.design.architecture.facade import conform_roofs_to_slots
from app.domain.design.architecture.facade import resolve_facade_layout
from app.domain.design.architecture.planning import normalize_architecture_plan
from app.domain.design.architecture.profile import is_architecture_request
from app.domain.design.architecture.skeleton import build_deterministic_skeleton
from app.domain.design.architecture.skeleton import evaluate_skeleton_complexity
from app.domain.design.architecture.target_kind import TargetKind
from app.domain.design.architecture.target_kind import detect_target_kind

__all__ = [
    "build_deterministic_skeleton",
    "conform_balconies_to_slots",
    "conform_entrance_accessories",
    "conform_openings_to_slots",
    "conform_railings_to_slots",
    "conform_roofs_to_slots",
    "detect_target_kind",
    "evaluate_skeleton_complexity",
    "is_architecture_request",
    "normalize_architecture_plan",
    "resolve_facade_layout",
    "TargetKind",
]
