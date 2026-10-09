"""确定性编译通路的接线测试：节点、路由、"不重复派发已产出类型"、以及整路闭环。

编译本身的行为契约在 ``test_compile_design.py``；这里只钉**接线**——
建筑批准后必走编译、物件链不受影响、不会让模型重做一遍已经算出来的东西，
且"编译 → 计划 → 交付校验"这条整路真的能闭合。
"""

from __future__ import annotations

import pytest

from app.agent.nodes.compile_node import compile_node
from app.agent.nodes.design_review_node import route_design_review
from app.agent.plan.contracts import PlanKindStrategy, PlanStrategy
from app.agent.plan.expand import _produced_kinds, expand_plan

_MESSAGE = "生成一个三层别墅"

_ARCHITECTURE_PLAN: dict = {
    "massing": {
        "shape": "rect",
        "width": 12,
        "depth": 9,
        "floors": 3,
        "modeled_floors": 3,
        "floor_height": 3.2,
    },
    "facades": {
        "front": {
            "bays": 4,
            "entrance_bay": 2,
            "ground_pattern": ["window", "door", "window", "empty"],
            "upper_pattern": ["window", "window", "window", "empty"],
        },
        "back": {"bays": 4, "ground_pattern": ["window"] * 4, "upper_pattern": ["window"] * 4},
        "left": {"bays": 3, "ground_pattern": ["window"] * 3, "upper_pattern": ["window"] * 3},
        "right": {"bays": 3, "ground_pattern": ["window"] * 3, "upper_pattern": ["window"] * 3},
    },
    "roof": {"type": "gable", "ridge_axis": "x", "overhang": 0.6},
    "circulation": {"vertical_strategy": "stair"},
    "complexity": {
        "level": "standard",
        "min_volumes": 1,
        "grid_bays": [3, 2],
        "min_detail_packages": 2,
        "target_structural_elements": 30,
    },
}


# ── 一、路由（没有开关：建筑一律走编译）──


def _state(*, approved: bool = True, plan: dict | None = None) -> dict:
    return {
        "design_review_status": "approved" if approved else "pending",
        "architecture_plan": plan if plan is not None else dict(_ARCHITECTURE_PLAN),
    }


def test_route_compiles_every_approved_architecture() -> None:
    """批准后的建筑一律走确定性编译——**没有开关**。

    这里刻意不读任何环境变量：图纸一旦批准，结构/门窗/屋顶/附属构件就是图纸的
    确定性函数，再让模型重算一遍既是重复劳动、又会与图纸分叉。
    """

    assert route_design_review(_state()) == "compile"


def test_route_keeps_object_scenes_on_skeleton() -> None:
    """物件（"生成一张桌子"）没有体量/立面/屋顶协议，编译只会把它变成一栋房子。

    这是 ``skeleton`` 仍然存活的**唯一**理由 ⇒ 这条断言实质是在钉
    "物件链没有被并进建筑链"。
    """

    object_plan = {"target_kind": "object", "objects": [{"id": "o1", "primitive": "table"}]}
    assert route_design_review(_state(plan=object_plan)) == "skeleton"


def test_route_sends_unapproved_design_back_to_revision() -> None:
    assert route_design_review(_state(approved=False)) == "architecture"


# ── 三、编译节点 ──


@pytest.mark.asyncio
async def test_compile_node_fills_blueprint_without_model() -> None:
    """节点是纯函数式的：同输入同输出，且不产生 error / status=failed。

    红线：图纸有问题只记进 ``compile_report``，绝不掐掉整轮生成。
    """

    state = {"architecture_plan": dict(_ARCHITECTURE_PLAN), "user_message": _MESSAGE}
    delta = await compile_node(state)

    blueprint = delta["skeleton_blueprint"]
    geometry = blueprint["geometry"]
    kinds = {item["type"] for item in geometry["elements"]}
    component_kinds = {item["type"] for item in geometry["components"]}

    assert {"wall", "floor", "roof"} <= kinds
    assert {"door", "window"} <= component_kinds
    # 门/窗/屋顶一次算完 → 不该再建议模型做一遍。
    assert delta["suggested_components"] == []
    assert delta["design_brief"]["opening_slots"]
    assert delta["skeleton_summary"]

    report = delta["compile_report"]
    assert report["elements"] > 0 and report["components"] > 0
    assert report["ok"] is True, report["defects"]
    assert "error" not in delta and "status" not in delta


@pytest.mark.asyncio
async def test_compile_node_output_is_deterministic() -> None:
    state = {"architecture_plan": dict(_ARCHITECTURE_PLAN), "user_message": _MESSAGE}
    first = await compile_node(state)
    second = await compile_node(state)
    assert first["skeleton_blueprint"] == second["skeleton_blueprint"]


# ── 四、不重复派发 ──


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


@pytest.mark.asyncio
async def test_plan_after_compile_does_not_redispatch_openings() -> None:
    """端到端接线：编译节点 → ``expand_plan``，门窗屋顶都不再进计划。

    这一条是"少花钱"的可观测判据——编译通路的意义就是把这几次模型调用省掉。
    """

    state = {"architecture_plan": dict(_ARCHITECTURE_PLAN), "user_message": _MESSAGE}
    delta = await compile_node(state)

    plan = expand_plan({**state, **delta})
    dispatched = {item.kind for item in plan.items if item.op == "generate"}
    assert not ({"door", "window", "roof"} & dispatched), dispatched


# ── 五、整路：compile → plan → 交付校验 ──


@pytest.mark.asyncio
async def test_plan_dispatches_exactly_the_uncompiled_kinds() -> None:
    """编译后计划里**只剩**编译器没有派生规则的那几类，一个不多一个不少。

    "一个不多" = 不重复派发已产出的（省模型调用）；
    "一个不少" = 缺规则的必须仍派给模型（否则那类构件直接缺席，而红线只允许标记、不允许阻断）。

    用 ``ramp`` / ``elevator`` 而不是先前的 ``cornice`` / ``chimney``：
    这两类已补上确定性派生规则（檐口沿檐边、烟囱立屋脊），
    再拿它们举例就测不到"派给模型"这条分支了。

    ⚠️ 必须照实把编译节点的**整份**回写喂给 ``expand_plan``。只喂蓝图会让
    ``design_brief`` 缺失 → 配额查不到 → 计划空掉：这条测试本身就在钉"节点回写了什么"。
    """

    state = await _compiled_state({"ramp": 1, "elevator": 1})
    plan = expand_plan(state)
    dispatched = {item.kind for item in plan.items if item.op == "generate"}
    assert dispatched == {"ramp", "elevator"}, dispatched


@pytest.mark.asyncio
async def test_compiled_blueprint_passes_delivery_pipeline() -> None:
    """编译产物直接过**交付**校验（22 步），零 error。

    编译器自带那三层（尺寸 / 引用 / 设计清单）只是交付门禁的子集。这一步不过，
    开关打开后交付的就是 partial/failed —— 那等于"确定性编译"只省了模型钱、却交不出东西。

     **但这条测试不能只信流水线**：实测把门窗合成整段去掉（图纸点了 1 门 39 窗、
    产物一个没有），22 步**照样全绿** —— 交付门禁只问"这份蓝图合不合法"，
    **不问"图纸点名的构件是否都到位"**（后者是 `validate_design_brief_constraints` 的职责，
    它不在 `run_validation_pipeline` 里）。所以下面必须自己钉住"产物非退化"，
    否则这份断言会被一份合法的空房子骗过去。
    """

    from app.services.agent_service import run_validation_pipeline

    state = await _compiled_state()
    blueprint = state["skeleton_blueprint"]

    component_kinds = {
        item["type"] for item in blueprint["geometry"]["components"]
    }
    assert {"door", "window"} <= component_kinds, "产物退化了，这条测试就没意义了"

    results = run_validation_pipeline(blueprint)
    errors = [result.name for result in results if result.has_error]
    assert results, "校验流水线一步都没跑，说明入口被改坏了"
    assert errors == [], errors


async def _compiled_state(quota: dict | None = None) -> dict:
    """跑一次编译节点，返回**完整的**状态回写（含 blueprint / design_brief / suggested_components）。"""

    plan = dict(_ARCHITECTURE_PLAN)
    if quota is not None:
        plan["component_quota"] = {kind: {"min": n, "max": n} for kind, n in quota.items()}
    delta = await compile_node({"architecture_plan": plan, "user_message": _MESSAGE})
    return {"architecture_plan": plan, "user_message": _MESSAGE, **delta}


@pytest.mark.asyncio
async def test_derived_attachments_pass_delivery_pipeline() -> None:
    """点了檐口/烟囱/灯具的编译产物也过 22 步**交付**校验，零 error。

    ``gable`` 只有两条檐边，所以檐口写 2（写 4 会被"产不够就不产"的门挡回 ``uncompiled``，
    那测的就不是派生物了）。这条是"派生的字段名/坐标语义跟引擎契约不差分毫"的整路证明。
    """

    from app.services.agent_service import run_validation_pipeline

    state = await _compiled_state({"cornice": 2, "chimney": 1, "light": 8})
    blueprint = state["skeleton_blueprint"]

    component_kinds = {item["type"] for item in blueprint["geometry"]["components"]}
    assert {"cornice", "chimney", "light"} <= component_kinds, (
        "派生物没落地，这条测试就没意义了"
    )

    results = run_validation_pipeline(blueprint)
    errors = [result.name for result in results if result.has_error]
    assert results, "校验流水线一步都没跑，说明入口被改坏了"
    assert errors == [], errors
