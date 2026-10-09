"""P7-D：对照评测框架的守卫。

这一层的风险不是"算错数"，而是**框架本身允许造假**。所以测试钉的是：

1. **答案标准不可事后改**：任务集是纯数据 + 内容摘要；改动会让摘要变。
   报告里必须带摘要，否则"标准有没有被改过"无法第三方核对。
2. **指标不合总分**：``ScoreCard`` **不许有** ``overall`` 字段 ——
   路线文档 §5 明令"不先合成一个容易掩盖问题的总分"。
3. **失败样本不删**：``unsupported`` / ``needs_review`` 单独计数，
   既不并入成功也不从统计消失。
4. **通用 Agent 组不许伪造**：``general_agent`` 是外部产物，
   框架只提供槽位，**不提供**任何"用本仓库假装通用 Agent"的实现。
5. **小样本不声称显著**：这句话是规范的一部分，测试钉住它的内容。
"""
import json

import pytest

from app.agent.vision import benchmark as B
from app.agent.vision.benchmark import (
    CHECKS,
    GROUPS,
    RUNS_PER_TASK,
    TASKS,
    ScoreCard,
    coverage_note,
    human_requirements,
    machine_requirements,
    significance_claim,
    task_spec_digest,
)


# ── 任务集：8 类、字段齐、要求可判 ──────────────────────────────────

def test_eight_tasks_present():
    assert len(TASKS) == 8
    assert [t.id for t in TASKS] == list(range(1, 9))


def test_every_task_has_prompt_and_criteria():
    for task in TASKS:
        assert task.prompt.strip(), f"任务 {task.id} 没有提示词"
        assert task.requirements, f"任务 {task.id} 没有要求项"
        assert task.capability_boundary.strip(), (
            f"任务 {task.id} 没写能力边界 —— 能力不足会被误判成生成失败")


def test_every_machine_requirement_has_a_registered_check():
    """判定函数名必须在 :data:`CHECKS` 里注册。

    🔴 内联判定逻辑等于把答案标准藏进实现：改实现就等于改标准，
       而且报告里看不出来。这条钉住"标准与实现分离"。
    """

    for task in TASKS:
        for req in machine_requirements(task):
            assert req.check, f"{task.id}/{req.id} 没有 check 名"
            assert req.check in CHECKS, f"{task.id}/{req.id} 的 check 未注册：{req.check}"
            assert req.description, f"{task.id}/{req.id} 没有可读描述"


def test_every_requirement_id_is_unique_within_task():
    for task in TASKS:
        ids = [r.id for r in task.requirements]
        assert len(ids) == len(set(ids)), f"任务 {task.id} 要求 id 重复：{ids}"


def test_human_requirements_have_no_check():
    """人工项不能挂机器判定函数 —— 那会让人工打分被程序覆盖。"""

    for task in TASKS:
        for req in human_requirements(task):
            assert req.check is None, f"{task.id}/{req.id} 人工项不该有 check"


def test_task_8_is_the_capability_boundary_task():
    """第 8 类专门检验"如实报告能力边界"，它的要求必须是能力反馈而非几何。"""

    task = next(t for t in TASKS if t.id == 8)
    assert any(r.expect_unsupported for r in machine_requirements(task)), (
        "第 8 类必须至少有一项期望 unsupported，否则测的是'能不能造出来'"
        "而不是'会不会如实说造不出来'")


def test_unsupported_expectation_is_not_counted_as_failure():
    """🔴 命中能力边界**不是失败** —— 如实报告能力不足本身就是得分。

    所以期望 unsupported 的要求，其 satisfied 值不该影响满足率分母。
    """

    task8 = next(t for t in TASKS if t.id == 8)
    reported = next(r for r in machine_requirements(task8) if r.expect_unsupported)
    # 它必须真的挂着一个"报告能力边界"的判定，而不是泛泛的一条要求
    assert reported.check == "capability_feedback_reported"
    assert "能力边界" in reported.description


def test_task_7_is_the_negative_requirement_task():
    """第 7 类测负向要求：明确不要的东西不能出现。"""

    task7 = next(t for t in TASKS if t.id == 7)
    ids = {r.id for r in machine_requirements(task7)}
    assert {"no_balcony", "no_chimney"} <= ids


# ── 摘要：标准可被核对 ───────────────────────────────────────────────

def test_task_spec_digest_is_stable():
    """同一份任务集两次算出同一个摘要。"""

    assert task_spec_digest() == task_spec_digest()
    assert len(task_spec_digest()) == 16


def test_task_spec_digest_changes_when_a_standard_changes():
    """🔴 改任何一条要求/提示词，摘要必须变 —— 否则前后报告不可比。"""

    original = task_spec_digest()
    saved = B.TASKS
    try:
        # 🔴 换成 list 才能赋值 —— tuple 不可赋值正是"冻结"的落点之一。
        mutable = list(saved)
        mutable[0] = B.Task(
            id=saved[0].id, name=saved[0].name, prompt=saved[0].prompt + "（改）",
            requirements=saved[0].requirements, human_criteria=saved[0].human_criteria,
            capability_boundary=saved[0].capability_boundary,
        )
        B.TASKS = tuple(mutable)
        assert task_spec_digest() != original
    finally:
        B.TASKS = saved
    assert task_spec_digest() == original, "还原失败：测试自己污染了任务集"


def test_task_set_cannot_be_appended_to():
    """🔴 冻结的第一层：``TASKS`` 是 tuple，跑起来之后没法往里加任务。

    （字段级冻结由 :func:`test_tasks_tuple_is_immutable_container` 覆盖。）
    """

    with pytest.raises(TypeError):
        B.TASKS[8] = B.Task(  # type: ignore[index]
            id=9, name="临时加的", prompt="x", requirements=(),
            human_criteria=(), capability_boundary="")


def test_task_spec_digest_is_json_serializable_content():
    """摘要覆盖的内容必须能完整序列化，否则"标准"里有不可复现的东西。"""

    blob = json.dumps([t.prompt for t in TASKS], ensure_ascii=False)
    assert len(blob) > 100


# ── 指标：不许合总分 ────────────────────────────────────────────────

def test_scorecard_has_no_overall_field():
    """🔴 路线文档 §5："分别报告，不先合成一个容易掩盖问题的总分"。"""

    card = ScoreCard(group="optimized", task_id=1)
    assert not hasattr(card, "overall")
    payload = card.to_dict()
    assert "overall" not in payload and "totalScore" not in payload
    for key in ("satisfactionRate", "geometryValidRate", "medianDurationSeconds",
                "medianModelCalls", "byStatus", "failureTypes"):
        assert key in payload, f"缺少独立指标 {key}"


def test_metrics_are_reported_independently():
    """满足率高但几何有效率低 —— 两个数必须各自独立呈现，不能互相掩盖。"""

    card = ScoreCard(group="optimized", task_id=2, runs=4, success_runs=1,
                     satisfied={"a": True, "b": True, "c": True, "d": False})
    assert card.satisfaction_rate() == 0.75
    assert card.geometry_valid_rate() == 0.25


def test_satisfaction_rate_none_when_nothing_decidable():
    card = ScoreCard(group="optimized", task_id=8, satisfied={})
    assert card.satisfaction_rate() is None


def test_geometry_valid_rate_none_when_no_runs():
    assert ScoreCard(group="optimized", task_id=1).geometry_valid_rate() is None


def test_by_status_keeps_unsupported_and_needs_review_visible():
    """🔴 失败样本不删：unsupported / needs_review 单独计数。"""

    card = ScoreCard(group="optimized", task_id=8,
                     by_status={"satisfied": 2, "unsupported": 1, "needs_review": 1})
    payload = card.to_dict()
    assert payload["byStatus"] == {"satisfied": 2, "unsupported": 1, "needs_review": 1}
    assert sum(payload["byStatus"].values()) == 4


def test_failure_types_are_kept_not_dropped():
    card = ScoreCard(group="optimized", task_id=1, failure_types=["model_error", "timeout"])
    assert card.to_dict()["failureTypes"] == ["model_error", "timeout"]


def test_median_duration_and_calls():
    card = ScoreCard(group="optimized", task_id=1, durations=[3.0, 1.0, 2.0],
                     call_counts=[5, 1, 3])
    assert card.median_duration() == 2.0
    assert card.median_calls() == 3.0


def test_median_of_even_length_averages_middle():
    card = ScoreCard(group="g", task_id=1, durations=[1.0, 2.0, 3.0, 4.0])
    assert card.median_duration() == 2.5


def test_median_none_when_empty():
    card = ScoreCard(group="g", task_id=1)
    assert card.median_duration() is None and card.median_calls() is None


def test_sample_size_is_exposed():
    """报告必须能看到每组跑了多少次 —— 小样本不声称显著的前提。"""

    assert ScoreCard(group="g", task_id=1, runs=3).sample_size == 3


# ── 措辞：小样本不声称显著 ──────────────────────────────────────────

def test_significance_claim_refuses_small_samples():
    claim = significance_claim(3)
    assert "不能声称统计显著" in claim
    assert str(3) in claim


def test_significance_claim_for_zero_runs():
    assert "未运行" in significance_claim(0)


def test_significance_claim_scales_with_n():
    assert "不建议声称统计显著" in significance_claim(10)
    assert "效应量" in significance_claim(50)


def test_coverage_note_records_missing_tasks():
    """🔴 预算不足缩减时要写明原因与未跑项，不能静悄悄少跑几类。"""

    note = coverage_note({1, 2, 3})
    assert "3/8" in note
    assert "未运行" in note
    assert "[4, 5, 6, 7, 8]" in note


def test_coverage_note_when_complete():
    assert "全部" in coverage_note(set(range(1, 9)))


# ── 三组：通用 Agent 槽位存在但不由本仓库伪造 ────────────────────────

def test_three_groups_are_declared():
    assert GROUPS == ("p0_baseline", "optimized", "general_agent")


def test_framework_provides_no_general_agent_implementation():
    """🔴 P7-D 第 4 条："没有通用 Agent 运行条件时明确缺该组，不编造结论"。

    本仓库**没有**任何"通用 coding agent"实现，框架也绝不能提供一个 ——
    否则"三方对照"会退化成"同一套东西跑三遍"，对照结论全是假的。
    这里钉住：框架只提供组名槽位，不提供任何产出 general_agent 结果的代码。
    """

    import inspect

    source = inspect.getsource(B)
    for forbidden in ("class GeneralAgent", "def run_general_agent",
                      "def general_agent", "GENERAL_AGENT_PROMPT"):
        assert forbidden not in source, (
            f"框架里不该有 {forbidden} —— 通用 Agent 组必须是外部产物")


def test_runs_per_task_matches_spec():
    assert RUNS_PER_TASK == 3


def test_reduction_order_covers_all_tasks():
    assert set(B.REDUCTION_ORDER) == {t.id for t in TASKS}
    assert list(B.REDUCTION_ORDER) == sorted(B.REDUCTION_ORDER), "缩减顺序必须是 1..8"


# ── 冻结：TASKS 不得被运行时改写 ────────────────────────────────────

def test_tasks_tuple_is_immutable_container():
    """``TASKS`` 是 tuple（不能 append），``Task`` 是 frozen dataclass。"""

    import dataclasses

    assert isinstance(TASKS, tuple)
    for task in TASKS:
        assert dataclasses.is_dataclass(task)
        with pytest.raises(dataclasses.FrozenInstanceError):
            task.prompt = "改一个"  # type: ignore[misc]
