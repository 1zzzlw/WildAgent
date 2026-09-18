"""结构化要求与 architecture 配额的一致性回归测试。

背景：`normalize_architecture_plan` 会把 door/window 的配额**派生**成立面 pattern 的
实际槽位数量（min == max == count）。曾经的结构化要求注入会在这之后抬高这两个开口的
min，使配额与实际槽位互相矛盾，`DesignDocument` 随即抛出未捕获的 Pydantic 异常，
整轮生成直接终止（用户看到 "door 立面槽位数量 1 不在配额 2~2 内"）。

注入机制与候选评分选择已整体删除（见
`docs/面试难点解决过程/Agent工作流与中间状态设计问题/候选机制清理与proposal节点处置方案.md`），
本文件保留的核心断言改为：**归一化产物自身必须始终满足 DesignDocument 契约**，
以及契约失败必须转成受控业务错误。
"""

import pytest
from pydantic import ValidationError

from app.agent.generation.architecture.planning import (
    _facade_opening_counts,
    normalize_architecture_plan,
)
from app.agent.generation.architecture.workflow import (
    DesignContractError,
    build_design_document_or_error,
)
from app.design.resolver import build_design_document


_MESSAGE = "生成一个两层别墅，带阳台"

# 覆盖开口派生最容易出错的几种需求：阳台、凸窗、多层。
_OPENING_MESSAGES = [
    _MESSAGE,
    "生成一个三层欧式别墅",
    "生成带凸窗的两层现代别墅",
]


def _normalized(message: str = _MESSAGE) -> dict:
    return normalize_architecture_plan({}, message)


def _opening_slots(plan: dict) -> dict[str, int]:
    facades = plan.get("facades") or {}
    massing = plan.get("massing") or {}
    floors = int(massing.get("modeled_floors") or massing.get("floors") or 1)
    return _facade_opening_counts(facades, floors)


@pytest.mark.parametrize("message", _OPENING_MESSAGES)
def test_pattern_governed_quota_matches_actual_facade_slots(message: str) -> None:
    """door/window 的配额必须等于立面实际槽位数，不能是模型可写的自由度。"""

    plan = _normalized(message)
    slots = _opening_slots(plan)

    for opening in ("door", "window"):
        quota = plan["component_quota"].get(opening)
        if quota is None:
            continue
        assert quota["min"] == quota["max"] == slots.get(opening, 0)


@pytest.mark.parametrize("message", _OPENING_MESSAGES)
def test_normalized_plan_always_satisfies_design_contract(message: str) -> None:
    """归一化产物必须能直接构造成 DesignDocument——这是错误率不上升的关键。"""

    document = build_design_document(
        _normalized(message),
        session_id="regression_session",
        source_request=message,
    )

    assert document.decisions.component_quota


_CURTAIN_WALL_MESSAGES = [
    "生成一个玻璃幕墙",
    "生成一个玻璃幕墙办公楼",
]


@pytest.mark.parametrize("message", _CURTAIN_WALL_MESSAGES)
def test_curtain_wall_door_quota_matches_facade_slots(message: str) -> None:
    """幕墙建筑的 door 配额必须与立面槽位数一一对应（窗保持密铺自由）。

    背景：`normalize_architecture_plan` 曾在 curtain_wall 模式下整体跳过
    door/window 的槽位重派生，导致模型输出的 door 配额（如 2~2）与立面
    实际只有 1 个门槽位脱钩，`DesignDocument` 抛出 "door 立面槽位数量 1
    不在配额 2~2 内"。修复后：door 仍按逐层 pattern 一一对应，window 保持
    幕墙密铺配额（宽区间），两者不再互相矛盾。
    """

    plan = _normalized(message)
    assert plan.get("curtain_wall") is True

    slots = _opening_slots(plan)
    door_quota = plan["component_quota"]["door"]
    window_quota = plan["component_quota"]["window"]

    assert door_quota["min"] == door_quota["max"] == slots["door"]
    # 幕墙窗是密集网格，配额保持宽区间（1~480），不等于槽位数。
    assert window_quota["min"] == 1
    assert window_quota["max"] > slots["window"]

    document = build_design_document(
        plan,
        session_id="regression_session",
        source_request=message,
    )
    assert document.decisions.component_quota


# 同一句话里的平面尺寸，验收侧与架构侧必须认出同一个值。
# 曾经的矛盾：验收侧认"宽约17米，深约23米"，架构侧的 `_requested_dimension`
# 不认"约"字，整条落回默认 12×9 → 验收要求 17×23、实际生成 12×9，
# 必然阻断交付。两侧解析器各写各的，就必须有测试钉住它们的一致性。
_DIMENSION_CONSISTENCY_CASES = [
    "生成两层住宅，宽约17米，深约23米",
    "生成两层住宅，宽度为17米，进深为23米",
    "生成两层住宅，宽17米深23米",
    "生成两层住宅，建筑平面17×23",
]


@pytest.mark.parametrize("message", _DIMENSION_CONSISTENCY_CASES)
def test_acceptance_and_architecture_agree_on_plan_dimensions(message: str) -> None:
    """说了尺寸就必须两侧都认；不然就会出现无法满足的验收要求。"""

    from app.agent.planning.requirements import _extract_plan_dimensions

    expected = _extract_plan_dimensions(message)
    massing = _normalized(message)["massing"]

    assert expected == (17.0, 23.0), f"验收侧没解析出尺寸：{message}"
    assert (massing["width"], massing["depth"]) == expected, (
        f"架构侧解析结果与验收侧不一致：{message}"
    )


def test_no_dimension_request_keeps_architecture_defaults() -> None:
    """没提尺寸时两侧都不该凭空造要求——验收侧返回 None，架构侧走默认。"""

    from app.agent.planning.requirements import _extract_plan_dimensions

    message = "生成两层住宅"
    assert _extract_plan_dimensions(message) is None
    assert _normalized(message)["massing"]["width"] > 0


@pytest.mark.xfail(
    strict=True,
    reason=(
        "已知遗留缺口（与本次候选机制清理无关）：高层的确定性兜底方案自身不自洽。"
        "`_fallback_plan` 按 floors=21 给出 window 配额 84，而立面 pattern 只在 "
        "modeled_floors=10 上展开，实际槽位为 69，DesignDocument 契约直接拒绝。"
        "修复 `_fallback_plan` 后本用例会转为 XPASS，届时删除该标记。"
    ),
)
def test_schematic_high_rise_fallback_satisfies_design_contract() -> None:
    """示意型高层：兜底方案也必须满足契约（当前不满足，见 xfail 原因）。"""

    message = "建造二十一层办公楼"
    document = build_design_document(
        _normalized(message),
        session_id="regression_session",
        source_request=message,
    )

    assert document.decisions.component_quota


def test_ascii_slash_marks_alternative_components() -> None:
    """door/window 是"任一"，不能因为斜杠两侧是字母就被判成"全部"。"""

    from app.agent.planning.requirements import compile_structured_requirements
    from app.agent.planning.execution import build_execution_plan

    plan = build_execution_plan(
        request_id="req_slash",
        intent="generate",
        user_message="生成一个两层别墅",
        planned_tasks=[
            {
                "title": "确定体量",
                "objective": "确定两层主体",
                "phase": "architecture",
                "acceptance": ["建筑必须为两层"],
                "basis": "用户需求",
            },
            {
                "title": "主体",
                "objective": "生成主体",
                "phase": "skeleton",
                "acceptance": ["至少添加一个 door/window 组件"],
                "basis": "用户需求",
            },
            {
                "title": "最终校验",
                "objective": "校验",
                "phase": "final_validate",
                "acceptance": ["完整校验零错误"],
                "basis": "WILD 协议",
            },
        ],
        planner_source="llm",
    )
    assert plan["planner_source"] == "llm", plan["dynamic_tasks"]
    requirement = compile_structured_requirements(plan)[1]

    assert requirement["kind"] == "component_any"
    assert requirement["operator"] == "contains_any"


def test_design_contract_error_is_a_controlled_business_error() -> None:
    """契约失败必须转成可读业务错误，而不是把 Pydantic 异常抛给调用方。"""

    plan = _normalized()
    plan["component_quota"]["door"] = {"min": 9, "max": 9, "note": "人为制造不一致"}

    with pytest.raises(DesignContractError) as excinfo:
        build_design_document_or_error(
            plan,
            session_id="regression_session",
            source_request=_MESSAGE,
            building_type="building",
            style_intent=[],
            previous=None,
        )

    message = str(excinfo.value)
    assert "不在配额" in message
    assert "Value error" not in message
    assert "input_value" not in message


def test_validation_error_is_wrapped_not_leaked() -> None:
    """DesignDocument 本身仍然拒绝不一致的配额（证明上面确实在检查真实约束）。"""

    plan = _normalized()
    plan["component_quota"]["door"] = {"min": 9, "max": 9, "note": "人为制造不一致"}

    with pytest.raises(ValidationError):
        build_design_document(
            plan,
            session_id="regression_session",
            source_request=_MESSAGE,
        )
