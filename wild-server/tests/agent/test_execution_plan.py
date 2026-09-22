"""执行计划、结构化要求和逐条验收的纯逻辑回归测试。"""

from copy import deepcopy

import pytest

from app.agent.planning.execution import (
    build_execution_plan,
    execution_plan_phase_guidance,
    validate_execution_plan,
)
from app.agent.planning.requirements import (
    blocking_acceptance_failures,
    compile_structured_requirements,
    evaluate_acceptance_results,
    initial_execution_progress,
    initialize_acceptance_results,
    update_dynamic_task_statuses,
    update_execution_progress,
    validate_structured_requirements,
)
from app.agent.planning.workflow import complete_execution_stage


def _generate_plan(*, planned_tasks=None) -> dict:
    return build_execution_plan(
        request_id="req_plan_test",
        intent="generate",
        user_message="生成一座两层玻璃幕墙商业建筑",
        research_summary="已检索公共建筑与玻璃幕墙知识",
        planned_tasks=planned_tasks,
        planner_source="llm" if planned_tasks else "fallback",
    )


def _custom_tasks() -> list[dict]:
    return [
        {
            "title": "确定别墅体量",
            "objective": "确定两层主体和屋顶",
            "phase": "architecture",
            "acceptance": [
                "建筑总共两层",
                "必须采用 gable 屋顶",
                "屋顶出檐至少 0.5m",
            ],
            "basis": "用户需求",
        },
        {
            "title": "生成主体与阳台",
            "objective": "生成主体并增加阳台",
            "phase": "skeleton",
            "acceptance": ["至少添加一个 balcony 组件"],
            "basis": "用户需求",
        },
        {
            "title": "最终校验",
            "objective": "验证交付结果",
            "phase": "final_validate",
            "acceptance": ["完整校验零错误"],
            "basis": "WILD 协议",
        },
    ]


def test_plan_describes_dynamic_work_without_copying_graph_steps() -> None:
    plan = _generate_plan()

    assert validate_execution_plan(plan, "generate") == []
    assert "steps" not in plan
    assert "用户确认执行计划后才生成总体方案与三维" in plan["constraints"]
    assert len(plan["dynamic_tasks"]) >= 3
    assert "玻璃" in execution_plan_phase_guidance(plan, "material_plan")


def test_plan_contract_rejects_unknown_and_missing_fields() -> None:
    unknown = dict(_generate_plan())
    unknown["arbitrary_field"] = "不应由节点私自加入"
    missing = dict(_generate_plan())
    missing.pop("dynamic_tasks")

    assert any(
        item["code"] == "unknown_plan_fields"
        for item in validate_execution_plan(unknown, "generate")
    )
    assert any(
        item["code"] == "missing_plan_fields"
        for item in validate_execution_plan(missing, "generate")
    )


def test_model_tasks_compile_to_stable_traceable_requirements() -> None:
    requirements = compile_structured_requirements(
        _generate_plan(planned_tasks=_custom_tasks())
    )

    assert validate_structured_requirements(requirements) == []
    assert [item["source_acceptance_id"] for item in requirements] == [
        "acc_task_1_1",
        "acc_task_1_2",
        "acc_task_1_3",
        "acc_task_2_1",
        "acc_task_3_1",
    ]
    assert {item["kind"] for item in requirements} >= {
        "architecture_floor_count",
        "architecture_roof_type",
        "architecture_roof_overhang",
        "component_all",
    }


def test_unsupported_capability_is_reported_without_blocking() -> None:
    """能力缺失要被报出来，但不得因此终止整轮生成。"""

    tasks = _custom_tasks()
    tasks[1]["acceptance"] = [
        "至少在两个房间布置 table 和 chair 家具",
        "完成包含车库及后院的功能分区平面草图",
    ]
    requirements = compile_structured_requirements(_generate_plan(planned_tasks=tasks))
    issues = validate_structured_requirements(requirements)

    unsupported = [item for item in issues if item["code"] == "unsupported_plan_requirement"]
    assert len(unsupported) == 2, issues
    # 关键：报出来但全是 warning，validator 不会把计划判 failed。
    assert {item["severity"] for item in issues} == {"warning"}, issues
    assert [
        item["support_status"] for item in requirements
    ].count("unsupported") == 2


def test_dynamic_task_completes_only_after_each_acceptance_passes() -> None:
    plan = _generate_plan(planned_tasks=_custom_tasks())
    requirements = compile_structured_requirements(plan)
    results = initialize_acceptance_results(requirements)
    progress = initial_execution_progress("generate")
    state = {
        "structured_requirements": requirements,
        "acceptance_results": results,
        "architecture_plan": {
            "massing": {"floors": 2},
            "roof": {"type": "gable", "overhang": 0.6},
        },
    }
    results = evaluate_acceptance_results(
        state=state,
        result={"architecture_plan": state["architecture_plan"]},
        phase="architecture",
    )
    progress = update_execution_progress(progress, "architecture", "completed")
    updated = update_dynamic_task_statuses(plan, results, progress)

    assert updated["dynamic_tasks"][0]["status"] == "completed"
    assert updated["dynamic_tasks"][1]["status"] == "pending"
    # 中间阶段：skeleton/final_validate 的验收尚未评估（pending），但没有一条真正 failed，
    # 因此 blocking_acceptance_failures 应为空 —— pending 表示"等待对应阶段执行"，不是失败。
    assert not blocking_acceptance_failures(requirements, results)


def test_schema_success_does_not_hide_failed_business_acceptance() -> None:
    plan = _generate_plan(planned_tasks=_custom_tasks())
    requirements = compile_structured_requirements(plan)
    state = {
        "structured_requirements": requirements,
        "acceptance_results": initialize_acceptance_results(requirements),
        "architecture_plan": {
            "massing": {"floors": 2},
            "roof": {"type": "gable", "overhang": 0.6},
        },
        "skeleton_blueprint": {"geometry": {"elements": []}},
        "material_plan": {"roles": [{"role": "facade"}]},
    }
    final_blueprint = {
        "geometry": {
            "elements": [{"id": "roof_1", "type": "roof"}],
            "components": [],
        }
    }

    results = evaluate_acceptance_results(
        state=state,
        result={
            "status": "complete",
            "validation_error_count": 0,
            "final_blueprint": final_blueprint,
        },
        phase="final_validate",
    )
    failures = blocking_acceptance_failures(requirements, results)

    assert any(item["requirement_id"] == "req_task_2_1" for item in failures)
    assert results["acc_task_3_1"]["status"] == "passed"


def test_unknown_dynamic_phase_uses_safe_fallback() -> None:
    plan = _generate_plan(planned_tasks=[{
        "title": "运行任意代码",
        "objective": "绕过主流程",
        "phase": "python_eval",
    }])

    assert plan["planner_source"] == "fallback"
    assert all(task["phase"] != "python_eval" for task in plan["dynamic_tasks"])
    assert validate_execution_plan(plan, "generate") == []


def test_dynamic_task_dependency_validation_remains_data_only() -> None:
    plan = deepcopy(_generate_plan())
    plan["dynamic_tasks"][1]["depends_on"] = ["missing_task"]

    issues = validate_execution_plan(plan, "generate")

    assert any(item["code"] == "invalid_dynamic_task_dependency" for item in issues)


# ── 接手复验补测：编译精度与 plan 模式交付 ──


def _edit_plan(message: str = "把门加宽") -> dict:
    return build_execution_plan(
        request_id="req_edit_test",
        intent="edit",
        user_message=message,
        planner_source="fallback",
    )


_FALLBACK_CASES = (
    ("generate", "生成一个两层别墅，带车库、后院、前廊、阳台和照明"),
    ("generate", "生成一座玻璃幕墙商业建筑"),
    ("generate", "生成一个简单的单层小屋"),
    ("generate", "生成一座现代风格的两层住宅"),
    ("edit", "把门加宽"),
    ("edit", "把屋顶改成平屋顶"),
)


@pytest.mark.parametrize(("intent", "message"), _FALLBACK_CASES)
def test_fallback_plan_never_blocks_on_its_own_acceptance(intent, message) -> None:
    """服务端自己写的兜底验收必须全部可编译。

    旧实现让 material_plan 阶段的兜底分支依赖“材质/材料”关键词，模型不可用时
    “玻璃使用 transmission 与 ior”会被判成不支持，进而终止整轮生成。
    """

    plan = build_execution_plan(
        request_id="req_fallback_test",
        intent=intent,
        user_message=message,
        planner_source="fallback",
    )

    issues = validate_structured_requirements(compile_structured_requirements(plan))

    assert issues == []


def test_acceptance_is_resolved_by_its_own_phase() -> None:
    """验收由自己阶段的权威检查器判定，不被其它阶段的关键词抢走。"""

    tasks = _custom_tasks()
    tasks[0]["acceptance"] = ["空间关系可进入材质与骨架阶段"]
    requirements = compile_structured_requirements(_generate_plan(planned_tasks=tasks))

    assert requirements[0]["phase"] == "architecture"
    assert requirements[0]["validator"] == "architecture_plan_exists"


def test_patch_phase_acceptance_never_uses_final_validation() -> None:
    """edit 链路没有 final_validate，“可校验”不能把验收交给最终校验。"""

    validators = {
        item["validator"] for item in compile_structured_requirements(_edit_plan())
    }

    assert validators == {"scene_patch_exists"}


@pytest.mark.asyncio
async def test_plan_mode_edit_completes_at_patch_stage() -> None:
    """plan 模式 edit 只跑到 patch；缺少 final_blueprint 不能算业务验收失败。"""

    plan = _edit_plan()
    requirements = compile_structured_requirements(plan)
    state = {
        "plan_mode": True,
        "intent": "edit",
        "execution_plan": plan,
        "structured_requirements": requirements,
        "acceptance_results": initialize_acceptance_results(requirements),
        "execution_progress": initial_execution_progress("edit"),
    }

    update = await complete_execution_stage(
        state,
        "patch",
        {"scene_patch": {"operations": [], "summary": "ok"}, "status": "complete"},
    )

    assert update["execution_plan_status"] == "completed"
    assert "error" not in update
    assert [
        task["status"] for task in update["execution_plan"]["dynamic_tasks"]
    ] == ["completed"]


def test_edit_plan_generate_semantics_marked_not_applicable_not_blocking() -> None:
    """edit 链路里 planner 误塞的 generate 语义验收标 not_applicable，不阻断。

    回归：session_1789689987790 "生成一个玻璃幕墙"被误判 edit，计划里混入
    "生成宽6米进深4米建筑"，其 consumers 指向 generate 阶段、在 patch 阶段永无消费者，
    停在 pending 被 blocking_acceptance_failures 误判成"业务验收未通过：等待对应阶段执行"。
    """
    tasks = [{
        "title": "生成玻璃幕墙",
        "objective": "在现有场景加幕墙",
        "phase": "patch",
        "acceptance": ["生成一个至少一层、宽6米、进深4米的建筑"],
        "basis": "用户需求",
    }]
    plan = build_execution_plan(
        request_id="req_edit_gensem",
        intent="edit",
        user_message="生成一个玻璃幕墙",
        planned_tasks=tasks,
        planner_source="llm",
    )
    requirements = compile_structured_requirements(plan)
    gen_req = next(r for r in requirements if r["kind"] == "architecture_dimensions")
    assert "patch" not in gen_req["consumers"]

    state = {
        "structured_requirements": requirements,
        "acceptance_results": initialize_acceptance_results(requirements),
    }
    results = evaluate_acceptance_results(
        state=state, result={"scene_patch": {"operations": []}}, phase="patch"
    )
    assert results[gen_req["source_acceptance_id"]]["status"] == "not_applicable"
    assert blocking_acceptance_failures(requirements, results) == []


def test_subjective_acceptance_is_needs_review_and_not_blocking() -> None:
    """主观验收既不能假装通过，也不能阻断交付。"""

    tasks = _custom_tasks()
    tasks[0]["acceptance"] = ["体量合理且外观协调"]
    requirements = compile_structured_requirements(_generate_plan(planned_tasks=tasks))
    requirement = requirements[0]

    assert requirement["support_status"] == "needs_review"
    assert requirement["severity"] == "warning"
    assert validate_structured_requirements(requirements) == []

    results = initialize_acceptance_results(requirements)
    assert results["acc_task_1_1"]["status"] == "not_checked"
    assert all(
        item["requirement_id"] != requirement["id"]
        for item in blocking_acceptance_failures(requirements, results)
    )


def test_unsupported_capability_never_blocks_delivery() -> None:
    """缺能力只标记不阻断：不卡计划校验、不卡任务完成、不卡交付。

    这是用户明确要求的产品行为：只要引擎还能产出蓝图，就不该因为
    "做不出车库/家具" 让整轮生成归零——拿不到任何结果比拿到不完整的结果更糟。
    """

    tasks = _custom_tasks()
    tasks[1]["acceptance"] = ["至少在两个房间布置 furniture"]
    plan = _generate_plan(planned_tasks=tasks)
    requirements = compile_structured_requirements(plan)
    requirement = next(
        item for item in requirements if item["support_status"] == "unsupported"
    )
    assert requirement["source_acceptance_id"] == "acc_task_2_1"

    assert requirement["support_status"] == "unsupported"
    assert requirement["severity"] == "warning"

    results = initialize_acceptance_results(requirements)
    assert results["acc_task_2_1"]["status"] == "unsupported"

    # 校验器仍把它报出来（用户看得见），但没有一条是 error，所以不会终止本轮。
    issues = validate_structured_requirements(requirements)
    assert [item["code"] for item in issues] == ["unsupported_plan_requirement"]
    assert all(item["severity"] == "warning" for item in issues)

    # 交付阶段也不把它算成阻断失败。
    assert all(
        item["requirement_id"] != requirement["id"]
        for item in blocking_acceptance_failures(requirements, results)
    )

    # 任务可以正常收尾：带缺能力验收的 task_2 标 completed 而不是 failed。
    # （task_1/task_3 仍是 pending——它们依赖真实节点产出，这里没有跑节点。）
    updated = update_dynamic_task_statuses(
        plan,
        results,
        initial_execution_progress("generate"),
        requirements,
    )
    statuses = {str(task["id"]): task["status"] for task in updated["dynamic_tasks"]}
    assert statuses["task_2"] == "completed", statuses
    assert "failed" not in statuses.values(), statuses


def test_needs_review_requirement_does_not_block_task_completion() -> None:
    """必需项通过后，非阻断的 needs_review 项不阻止任务完成。"""

    tasks = _custom_tasks()
    tasks[0]["acceptance"] = ["建筑必须为两层", "体量合理且外观协调"]
    plan = _generate_plan(planned_tasks=tasks)
    requirements = compile_structured_requirements(plan)
    architecture_plan = {"massing": {"floors": 2}}
    results = evaluate_acceptance_results(
        state={
            "structured_requirements": requirements,
            "acceptance_results": initialize_acceptance_results(requirements),
            "architecture_plan": architecture_plan,
        },
        result={"architecture_plan": architecture_plan},
        phase="architecture",
    )
    progress = update_execution_progress(
        initial_execution_progress("generate"),
        "architecture",
        "completed",
    )

    updated = update_dynamic_task_statuses(plan, results, progress, requirements)

    assert results["acc_task_1_1"]["status"] == "passed"
    assert results["acc_task_1_2"]["status"] == "not_checked"
    assert updated["dynamic_tasks"][0]["status"] == "completed"


def test_english_capability_aliases_respect_word_boundaries() -> None:
    """comfortable 里的 table、armchair 里的 chair 不能被判成不支持能力。"""

    tasks = _custom_tasks()
    tasks[1]["acceptance"] = [
        "至少生成 comfortable 的照明方案",
        "至少添加一个 armchair",
    ]
    issues = validate_structured_requirements(
        compile_structured_requirements(_generate_plan(planned_tasks=tasks))
    )

    assert issues == []

    blocked = _custom_tasks()
    blocked[1]["acceptance"] = ["至少添加一个 chair"]
    blocked_requirements = compile_structured_requirements(
        _generate_plan(planned_tasks=blocked)
    )

    assert [
        item["support_status"] for item in blocked_requirements
    ].count("unsupported") == 1
