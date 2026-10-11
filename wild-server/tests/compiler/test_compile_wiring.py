"""建筑按标记落实后装配；物件仍使用既有骨架与类型策略。"""
from copy import deepcopy
import pytest
from app.agent.design_flow.compile import compile_node
from app.agent.design_flow.review import route_design_review
from app.agent.generation.architecture import normalize_architecture_plan
from app.agent.plan.contracts import PlanKindStrategy, PlanStrategy
from app.agent.plan.expand import _produced_kinds, expand_plan
from app.design.compilation import compile_document
from app.design.resolver import build_design_document

_MESSAGE = "生成一个三层别墅"












def test_produced_kinds_reads_both_buckets() -> None:
    blueprint = {
        "geometry": {
            "elements": [{"type": "wall", "id": "w1"}, {"type": "roof", "id": "r1"}],
            "components": [{"type": "door", "id": "d1"}, {"type": "door", "id": "d2"}],
        }
    }
    assert _produced_kinds(blueprint) == {"wall", "roof", "door"}
    # 骨架缺失 / 物件骨架（空容器）都不该凭空过滤掉任何类型。
    assert _produced_kinds(None) == set()
    assert _produced_kinds({"geometry": {"elements": [], "components": []}}) == set()

def test_model_strategy_cannot_redispatch_compiled_kinds() -> None:
    """模型策略里含已产出类型时也不派 ``generate`` —— 这是**模型策略路径**上的过滤。

     实测（2026-09-28 真模型探针）：编译已产出 door/window/roof，plan 仍派
    ``generate_door`` / ``generate_window`` / ``generate_roof``，白烧约 200s 模型时间，
    且窗被生成两遍（27 → 54）。根因是过滤只挂在确定性降级路径（``_requested_kinds``），
    模型给了策略时走 ``ordered_kinds(strategy)`` 把它整个绕过了。

    判据只看"产物里有没有"，不写 per-type 分支（与具体构件类型无关）。
    """

    strategy = PlanStrategy(
        kinds=[
            PlanKindStrategy(kind="door", reason="模型点名"),
            PlanKindStrategy(kind="ramp", reason="模型点名"),
        ],
        source="llm",
    )
    state = {
        "architecture_plan": {},
        "design_brief": {
            "component_quota": {"door": {"min": 1, "max": 4}, "ramp": {"min": 1, "max": 2}}
        },
        "user_message": _MESSAGE,
        "skeleton_blueprint": {"geometry": {"components": [{"type": "door", "id": "d1"}]}},
    }

    plan = expand_plan(state, strategy=strategy)
    dispatched = {item.kind for item in plan.items if item.op == "generate"}

    assert "door" not in dispatched, "编译产出的门又被派了一次"
    assert "ramp" in dispatched, "没产出的类型必须继续派给模型"
    # 抑制要留痕：交付清单得能回答"模型点名了门为什么没有条目"。
    assert [entry.action for entry in plan.history] == ["strategy:llm", "suppress:produced"]
    assert "door" in plan.history[-1].reason

def test_deterministic_path_skips_produced_types_through_the_same_gate() -> None:
    """降级路径同样不重复派发 —— 两条路径共用 ``expand_plan`` 里这一个闸口。

    这条测的**不是** ``_requested_kinds`` 自己过滤（它已不含该职责），
    而是"不管策略从哪来，条目都不会重复"。原先只在降级路径上过滤，
    正是"过滤挂在半条路上"的写法才让模型策略路径漏了出去。
    """

    state = {
        "architecture_plan": {},
        "design_brief": {
            "component_quota": {"door": {"min": 1, "max": 4}, "ramp": {"min": 1, "max": 2}}
        },
        "user_message": _MESSAGE,
        "suggested_components": ["door", "ramp"],
        "skeleton_blueprint": {"geometry": {"components": [{"type": "door", "id": "d1"}]}},
    }

    plan = expand_plan(state)  # 不给策略 → 走确定性降级
    dispatched = {item.kind for item in plan.items if item.op == "generate"}

    assert "door" not in dispatched, "降级路径漏了过滤"
    assert "ramp" in dispatched, "没产出的类型必须继续派发"
