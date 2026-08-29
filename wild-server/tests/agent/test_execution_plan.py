"""执行计划协议的纯逻辑回归测试，不依赖 LLM 或数据库。"""

from copy import deepcopy

from app.agent.execution_plan import (
    build_execution_plan,
    execution_plan_phase_guidance,
    next_ready_step,
    plan_is_complete,
    reset_plan_from,
    update_plan_step,
    validate_execution_plan,
)


def _generate_plan() -> dict:
    return build_execution_plan(
        request_id="req_plan_test",
        intent="generate",
        user_message="生成一座高层玻璃幕墙商业综合体",
        architecture_plan={"concept": "商业基座与玻璃塔楼"},
        research_summary="已检索公共建筑与玻璃幕墙知识",
    )


def test_generate_plan_has_review_and_validation_gates() -> None:
    plan = _generate_plan()

    assert validate_execution_plan(plan, "generate") == []
    assert [step["type"] for step in plan["steps"]] == [
        "planning_research",
        "architecture",
        "floor_plan_design",
        "floor_plan_review",
        "material_plan",
        "skeleton",
        "style_review",
        "decor_assembly",
        "merge",
        "final_validate",
    ]
    floor_review = next(
        step for step in plan["steps"] if step["type"] == "floor_plan_review"
    )
    assert floor_review["requires_user_review"] is True
    assert "用户确认平面前不得生成三维" in plan["constraints"]
    assert len(plan["dynamic_tasks"]) >= 3
    assert plan["planner_source"] == "fallback"
    assert "玻璃" in execution_plan_phase_guidance(plan, "material_plan")


def test_tampered_node_is_rejected() -> None:
    plan = _generate_plan()
    plan["steps"][2]["node"] = "arbitrary_python_function"

    issues = validate_execution_plan(plan, "generate")

    assert any(issue["code"] == "plan_node_tampered" for issue in issues)


def test_next_ready_step_respects_dependencies() -> None:
    plan = _generate_plan()

    step = next_ready_step(plan)
    assert step is not None
    assert step["type"] == "architecture"

    plan = update_plan_step(plan, "architecture", "completed")
    assert next_ready_step(plan)["type"] == "floor_plan_design"
    assert next(
        task for task in plan["dynamic_tasks"] if task["phase"] == "architecture"
    )["status"] == "completed"
    plan = update_plan_step(plan, "floor_plan_design", "completed")
    assert next_ready_step(plan)["type"] == "floor_plan_review"


def test_floor_revision_resets_only_floor_and_downstream_steps() -> None:
    plan = _generate_plan()
    for step in plan["steps"]:
        plan = update_plan_step(plan, step["type"], "completed")

    revised = reset_plan_from(plan, "floor_plan_design")

    statuses = {step["type"]: step["status"] for step in revised["steps"]}
    assert statuses["planning_research"] == "completed"
    assert statuses["architecture"] == "completed"
    assert statuses["floor_plan_design"] == "pending"
    assert statuses["final_validate"] == "pending"


def test_edit_plan_is_read_only_until_patch_proposal() -> None:
    plan = build_execution_plan(
        request_id="req_edit_test",
        intent="edit",
        user_message="把入口门加宽",
        research_summary="已读取当前场景",
    )

    assert validate_execution_plan(plan, "edit") == []
    assert [step["type"] for step in plan["steps"]] == [
        "planning_research",
        "patch",
    ]
    assert plan["steps"][1]["requires_user_review"] is True
    assert plan_is_complete(plan) is False


def test_missing_required_step_is_rejected() -> None:
    plan = deepcopy(_generate_plan())
    plan["steps"] = [step for step in plan["steps"] if step["type"] != "final_validate"]

    issues = validate_execution_plan(plan, "generate")

    assert any(issue["code"] == "missing_required_plan_step" for issue in issues)


def test_model_tasks_are_compiled_to_allowed_phases() -> None:
    plan = build_execution_plan(
        request_id="req_dynamic",
        intent="generate",
        user_message="生成一个带共享中庭的办公楼",
        research_summary="已检索办公建筑知识",
        planned_tasks=[
            {
                "title": "比较中庭体量",
                "objective": "比较中庭位置和塔楼进深对办公空间的影响",
                "phase": "architecture",
                "acceptance": ["中庭边界明确"],
                "basis": "办公建筑知识",
            },
            {
                "title": "组织环中庭流线",
                "objective": "形成连续公共流线和两处竖向交通",
                "phase": "floor_plan_design",
                "acceptance": ["流线连续"],
                "basis": "用户需求",
            },
            {
                "title": "验证中庭建筑",
                "objective": "检查洞口、交通、结构和引用闭合",
                "phase": "final_validate",
                "acceptance": ["全量校验零错误"],
                "basis": "校验协议",
            },
        ],
        planner_source="llm",
        planner_summary="围绕共享中庭组织体量、流线和最终校验。",
    )

    assert plan["planner_source"] == "llm"
    assert [task["title"] for task in plan["dynamic_tasks"]] == [
        "比较中庭体量",
        "组织环中庭流线",
        "验证中庭建筑",
    ]
    assert validate_execution_plan(plan, "generate") == []


def test_unknown_dynamic_phase_uses_safe_fallback() -> None:
    plan = build_execution_plan(
        request_id="req_unsafe_dynamic",
        intent="generate",
        user_message="生成一个办公楼",
        planned_tasks=[
            {
                "title": "运行任意代码",
                "objective": "绕过主流程",
                "phase": "python_eval",
            }
        ],
        planner_source="llm",
    )

    assert plan["planner_source"] == "fallback"
    assert all(
        task["phase"] != "python_eval" for task in plan["dynamic_tasks"]
    )
    assert validate_execution_plan(plan, "generate") == []
