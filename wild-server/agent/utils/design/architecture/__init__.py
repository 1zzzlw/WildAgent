"""总体建筑方案、确定性骨架与立面约束的公开 API。"""

from agent.utils.design.architecture.facade import conform_balconies_to_slots
from agent.utils.design.architecture.facade import conform_entrance_accessories
from agent.utils.design.architecture.facade import conform_openings_to_slots
from agent.utils.design.architecture.facade import conform_railings_to_slots
from agent.utils.design.architecture.facade import conform_roofs_to_slots
from agent.utils.design.architecture.facade import resolve_facade_layout
from agent.utils.design.architecture.planning import normalize_architecture_plan
from agent.utils.design.architecture.profile import is_architecture_request
from agent.utils.design.architecture.skeleton import build_deterministic_skeleton
from agent.utils.design.architecture.skeleton import evaluate_skeleton_complexity
from agent.utils.design.architecture.target_kind import TargetKind
from agent.utils.design.architecture.target_kind import detect_target_kind

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
