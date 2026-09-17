"""回归：验收编译的量词盲区不得把已合并的蓝图判死。

真实事故 2026-09-17（任务 req_1789634516108_eu82yreb4，用户只输入"生成一个别墅"）：

    [1] ~ [10.2] 全部 20 个结构校验器【全部通过】，合并也成功（23 个元素）
    错误: 业务验收未通过：实际数量：{'door': 1, 'window': 13, 'roof': 1}

死因是执行计划里 task_4 的一条验收被编译错了：

    原文   "材质方案包含墙体、屋顶、门窗至少3种材质"   ← 语义是"材质至少 3 种"
    编译   {"types": ["door", "window", "roof"], "minimum": 3}
           ← 变成"门、窗、屋顶每种至少 3 个"
    实际   door=1 / roof=1 < 3 → failed（severity=error）
    后果   plan.status=failed，且 final_blueprint 被置 None —— 蓝图被丢弃

本文件钉住三件事：
  1. 「N种/类/款」是种类数，不得变成实例下限；
  2. 材质类要求必须由 material_plan 消费，且**不能**被构件分支抢先编译；
  3. 真·实例要求（"至少N个"）仍要照旧强制执行，不能被这次修复放水。
"""

from __future__ import annotations

import pytest

from app.agent.planning.requirements import (
    _minimum_count,
    _minimum_kind_count,
    blocking_acceptance_failures,
    compile_structured_requirements,
    evaluate_acceptance_results,
)

INCIDENT_TEXT = "材质方案包含墙体、屋顶、门窗至少3种材质"


def _plan_with_acceptance(*acceptance: str, phase: str = "final_validate") -> dict:
    return {
        "dynamic_tasks": [
            {"id": "task_1", "phase": phase, "acceptance": list(acceptance)},
        ]
    }


def _blueprint(*, door: int = 0, window: int = 0, roof: int = 0) -> dict:
    return {
        "geometry": {
            "elements": [
                {"id": f"roof_{index}", "type": "roof"} for index in range(roof)
            ],
            "components": [
                {"id": f"door_{index}", "type": "door"} for index in range(door)
            ]
            + [
                {"id": f"window_{index}", "type": "window"}
                for index in range(window)
            ],
        }
    }


def _material_plan(role_count: int) -> dict:
    return {"roles": [{"role": f"role_{index}"} for index in range(role_count)]}


@pytest.mark.parametrize(
    ("text", "instance", "kind"),
    [
        # 种类量词：数的是"有多少种类"，不构成实例下限
        ("至少3种材质", 1, 3),
        ("至少3类构件", 1, 3),
        ("至少2款阳台栏杆", 1, 2),
        ("至少4种材料方案", 1, 4),
        # 实例量词：照旧构成实例下限
        ("至少3个窗户", 3, None),
        ("至少6扇窗", 6, None),
        ("至少4面墙", 4, None),
        # 没有数量短语
        ("生成完整的屋顶和门窗", 1, None),
    ],
)
def test_quantifier_distinguishes_kind_from_instance(
    text: str, instance: int, kind: int | None
) -> None:
    assert _minimum_count(text) == instance
    assert _minimum_kind_count(text) == kind


def test_material_kind_requirement_is_dispatched_to_material_plan() -> None:
    """事故原文必须编译成材质角色数量要求，而不是构件存在性要求。"""

    requirement = compile_structured_requirements(
        _plan_with_acceptance(INCIDENT_TEXT)
    )[0]

    assert requirement["kind"] == "material_role_count"
    assert requirement["validator"] == "material_plan_exists"
    assert requirement["target"] == "material_plan.roles"
    assert requirement["expected"] == {"minimum": 3}
    assert "material_plan" in requirement["consumers"]
    # 关键反向断言：不能被构件分支编译成"门窗屋顶每种≥3个"
    assert requirement["validator"] != "component_presence"
    assert "types" not in requirement["expected"]


def test_kind_quantifier_without_material_term_is_not_material_requirement() -> None:
    """只有种类量词、没有材质词时，不能误判成材质要求。"""

    requirement = compile_structured_requirements(
        _plan_with_acceptance("至少生成2种构件", phase="skeleton")
    )[0]

    assert requirement["validator"] != "material_plan_exists"


@pytest.mark.parametrize(
    ("role_count", "expected_status"),
    [(9, "passed"), (3, "passed"), (2, "failed"), (0, "failed")],
)
def test_material_plan_validator_honours_minimum(
    role_count: int, expected_status: str
) -> None:
    requirements = compile_structured_requirements(
        _plan_with_acceptance(INCIDENT_TEXT)
    )
    state = {
        "structured_requirements": requirements,
        "material_plan": _material_plan(role_count),
    }

    results = evaluate_acceptance_results(
        state=state, result={}, phase="final_validate"
    )

    assert results[requirements[0]["source_acceptance_id"]]["status"] == expected_status


def test_incident_requirement_no_longer_blocks_merged_blueprint() -> None:
    """事故场景端到端：9 个材质角色 + door=1/window=13/roof=1 必须放行。"""

    requirements = compile_structured_requirements(
        _plan_with_acceptance(INCIDENT_TEXT)
    )
    state = {
        "structured_requirements": requirements,
        # 线上那次 material_plan 的真实角色数
        "material_plan": _material_plan(9),
        # 线上那次 merged_blueprint 的真实数量
        "merged_blueprint": _blueprint(door=1, window=13, roof=1),
    }

    results = evaluate_acceptance_results(
        state=state, result={}, phase="final_validate"
    )

    requirement = requirements[0]
    assert results[requirement["source_acceptance_id"]]["status"] == "passed"
    assert results[requirement["source_acceptance_id"]]["observed"] == 9
    assert blocking_acceptance_failures(requirements, results) == []


def test_instance_quantifier_is_still_enforced() -> None:
    """修复不能放水：真·实例要求（"至少N个"）仍要照旧判失败并阻断。"""

    requirements = compile_structured_requirements(
        _plan_with_acceptance("至少生成3个窗户", phase="skeleton")
    )
    requirement = requirements[0]
    assert requirement["expected"] == {"types": ["window"], "minimum": 3}

    state = {
        "structured_requirements": requirements,
        "merged_blueprint": _blueprint(window=1),
    }

    results = evaluate_acceptance_results(
        state=state, result={}, phase="final_validate"
    )

    result = results[requirement["source_acceptance_id"]]
    assert result["status"] == "failed"
    assert result["observed"] == {"window": 1}
    assert blocking_acceptance_failures(requirements, results)
