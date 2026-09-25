"""plan 契约、store 与确定性展开（《动态节点设计规划》§2.2/§2.6/§3.3）。"""

import pytest

from app.agent.generation.components import get_implemented_components
from app.agent.plan.contracts import (
    ItemRun,
    PlanDocument,
    PlanItem,
    TERMINAL_STATUSES,
)
from app.agent.plan.expand import DETAIL_BUDGET, expand_plan, plan_budget, resolve_detail_level
from app.agent.plan.store import (
    append_items,
    counts_are_consistent,
    new_plan,
    poll_runnable,
    record_result,
    refresh_statuses,
    reset_for_retry,
    set_status,
    terminal_stats,
)


def _brief_state(**overrides):
    state = {
        "user_message": "生成两层小别墅，前后立面开窗",
        "suggested_components": ["door", "window", "roof"],
        "design_brief": {
            "component_quota": {
                "door": {"min": 1, "max": 2},
                "window": {"min": 6, "max": 8},
            },
            "opening_slots": [
                {
                    "id": "slot_win_1",
                    "type": "window",
                    "wall_id": "wall_s_1",
                    "from": [1.0, 1.1, 0],
                    "width": 1.5,
                    "height": 1.6,
                }
            ],
        },
        "design_document": {"decisions": {"complexity": {"level": "simple"}}},
    }
    state.update(overrides)
    return state


# ── 契约 ──


def test_op_is_a_closed_set():
    with pytest.raises(ValueError):
        PlanItem(id="x_01", op="build_foundation")


def test_failed_run_state_is_not_terminal():
    item = PlanItem(id="generate_window_01", op="generate", kind="window")
    item.run = ItemRun(state="failed", attempts=1)
    assert item.is_terminal is False
    assert item.status == "pending"


def test_terminal_status_requires_reconcile():
    item = PlanItem(id="generate_window_01", op="generate", kind="window")
    assert item.is_terminal is False
    item.status = "done"
    assert item.is_terminal is True
    assert "done" in TERMINAL_STATUSES


def test_progress_signature_changes_with_state():
    plan = new_plan([PlanItem(id="generate_door_01", op="generate", kind="door")])
    before = plan.progress_signature()
    updated = record_result(plan, "generate_door_01", state="succeeded")
    assert updated.progress_signature() != before


def test_progress_signature_stays_within_contract_for_large_plan():
    items = [
        PlanItem(id=f"generate_component_{index:03d}", op="generate", kind="wall")
        for index in range(40)
    ]

    signature = new_plan(items).progress_signature()

    assert len(signature) == 64
    assert len(signature) <= 200


def test_attempt_counter_alone_is_not_business_progress():
    plan = new_plan([PlanItem(id="generate_door_01", op="generate", kind="door")])
    before = plan.progress_signature()

    plan.item("generate_door_01").run.attempts += 1

    assert plan.progress_signature() == before


def test_replacement_parameters_are_business_progress():
    plan = new_plan([PlanItem(id="generate_door_01", op="generate", kind="door")])
    before = plan.progress_signature()

    plan.item("generate_door_01").params["subtype"] = "单开门"

    assert plan.progress_signature() != before


# ── store ──


def test_dependency_gating_and_blocked_propagation():
    generate = PlanItem(id="generate_roof_01", op="generate", kind="roof")
    merge = PlanItem(id="merge_all_01", op="merge", depends_on=["generate_roof_01"])

    plan = new_plan([generate, merge])
    assert plan.item("generate_roof_01").status == "ready"
    assert plan.item("merge_all_01").status == "blocked"

    done = set_status(plan, "generate_roof_01", "done")
    refreshed = refresh_statuses(done)
    assert refreshed.item("merge_all_01").status == "ready"

    # 上游失败不阻断 merge：分片还在 component_fragments 里，合并照跑，
    # 局部失败允许在交付清单里如实呈现，而不是把整条链拖死（§9.2 政策）。
    abandoned = set_status(plan, "generate_roof_01", "abandoned")
    assert refresh_statuses(abandoned).item("merge_all_01").status == "ready"

    # 上游已成功但只是还没合并进蓝图，也算落定——否则 generate↔merge 永久互等。
    succeeded = record_result(
        record_result(plan, "generate_roof_01", state="running"),
        "generate_roof_01",
        state="succeeded",
        count_attempt=False,
    )
    refreshed = refresh_statuses(succeeded)
    assert refreshed.item("merge_all_01").status == "ready"
    # 已成功产出的 generate 不再可执行（产物已出，只等合并），队列交给 merge
    assert poll_runnable(refreshed).id == "merge_all_01"


def test_dangling_dependency_keeps_item_blocked():
    orphan = PlanItem(id="merge_all_01", op="merge", depends_on=["generate_ghost_99"])

    assert new_plan([orphan]).item("merge_all_01").status == "blocked"


def _settled_chain():
    """一组跑完的分组链：generate → 批次 merge → 收尾 merge → validate，全部 done。"""

    items = [
        PlanItem(id="generate_door_01", op="generate", kind="door"),
        PlanItem(
            id="merge_door_01",
            op="merge",
            kind="door",
            params={"scope": "batch"},
            depends_on=["generate_door_01"],
        ),
        PlanItem(
            id="merge_all_01",
            op="merge",
            params={"scope": "final"},
            depends_on=["merge_door_01"],
        ),
        PlanItem(id="validate_all_01", op="validate", depends_on=["merge_all_01"]),
    ]
    plan = new_plan(items)
    for item in list(plan.items):
        plan = record_result(plan, item.id, state="succeeded", count_attempt=False)
        plan = set_status(plan, item.id, "done")
    return plan


def test_downstream_reopens_when_an_upstream_is_sent_back():
    """下游失效：上游被退回重跑，已完成的批次 merge / 收尾 merge / validate 必须跟着重跑。

    没有这条规则，一次重试就会让合并保持 ``done``——重跑出来的新分片永远并不进蓝图，
    条目在生成侧"成功"、在交付侧什么都没有，是静默丢产物。
    """

    plan = _settled_chain()
    assert refresh_statuses(plan).item("merge_all_01").status == "done"

    sent_back = reset_for_retry(plan, "generate_door_01", evidence="产物未落地，重跑")
    refreshed = refresh_statuses(sent_back)

    for item_id in ("merge_door_01", "merge_all_01", "validate_all_01"):
        item = refreshed.item(item_id)
        assert item.status == "ready", item_id
        # 只把计划态改回去是不够的：执行态还是 succeeded 的话 poll_runnable 会跳过它
        assert item.run.state == "idle", item_id
    # 下游失效是重跑，不是失败——不许烧条目的重试额度
    assert refreshed.item("merge_door_01").run.attempts == 0


def test_abandoned_terminals_are_not_dragged_back_by_a_rerun():
    """``abandoned`` 是"决定不做"，不是"做完了"：上游重跑不该把它拉回来。"""

    plan = _settled_chain()
    plan = set_status(plan, "merge_door_01", "abandoned")
    sent_back = reset_for_retry(plan, "generate_door_01", evidence="重跑")

    assert refresh_statuses(sent_back).item("merge_door_01").status == "abandoned"


def test_final_merge_and_validate_watch_every_producer():
    """收尾条目的上游是全部生产条目，不是某几条 depends_on。

    否则 replanner 追加的分组生成完后，收尾步骤会一直保持 ``done``，新产物被丢掉。
    """

    plan = _settled_chain()
    plan, _ = append_items(
        plan,
        [PlanItem(id="generate_window_01", op="generate", kind="window")],
        reason="replanner 追加",
    )
    refreshed = refresh_statuses(plan)

    assert refreshed.item("merge_all_01").status == "ready"
    assert refreshed.item("validate_all_01").status == "ready"


def test_poll_runnable_follows_declaration_order():
    first = PlanItem(id="generate_door_01", op="generate", kind="door")
    second = PlanItem(id="generate_window_01", op="generate", kind="window")
    plan = new_plan([second, first])
    assert poll_runnable(plan).id == "generate_window_01"
    assert poll_runnable(new_plan([])) is None


def test_record_result_counts_attempts_and_keeps_evidence():
    plan = new_plan([PlanItem(id="generate_window_01", op="generate", kind="window")])
    failed = record_result(plan, "generate_window_01", state="failed", evidence="解析失败")
    assert failed.item("generate_window_01").run.attempts == 1
    assert "解析失败" in failed.item("generate_window_01").run.evidence

    success = record_result(
        failed, "generate_window_01", state="succeeded",
        artifacts=["win_1"], count_attempt=False,
    )
    assert success.item("generate_window_01").run.attempts == 1
    assert success.item("generate_window_01").run.artifacts == ["win_1"]


def test_append_items_is_bounded_and_dedupes():
    plan = new_plan([PlanItem(id="generate_door_01", op="generate", kind="door")])
    extra = PlanItem(id="repair_01", op="repair", kind="door")

    once, appended = append_items(plan, [extra], reason="生成失败")
    assert appended is True
    assert once.revision == 2
    assert once.item("repair_01").origin == "emergent"
    assert once.history[-1].item_ids == ["repair_01"]

    again, appended_again = append_items(once, [extra], reason="重复")
    assert appended_again is False

    twice, _ = append_items(once, [PlanItem(id="repair_02", op="repair")], reason="再来一次")
    assert twice.revision == 2  # 上限 2：不再追加
    assert twice.item("repair_02") is None


def test_terminal_stats_is_verifiable():
    plan = new_plan(
        [
            PlanItem(id="generate_door_01", op="generate", kind="door"),
            PlanItem(id="merge_all_01", op="merge"),
        ]
    )
    plan = set_status(plan, "generate_door_01", "done")
    stats = terminal_stats(plan)
    assert stats["total"] == 2
    assert stats["done"] == 1
    assert stats["unfinished"] == 1
    assert counts_are_consistent(plan) is True


# ── 展开 ──


def test_expand_is_deterministic_and_ordered_by_registry():
    state = _brief_state()
    first = expand_plan(state)
    second = expand_plan(state)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")

    order = {cfg.component_type: index for index, cfg in enumerate(get_implemented_components())}
    generated = [item.kind for item in first.items_by_op("generate")]
    assert generated == sorted(generated, key=lambda kind: (order[kind], kind))
    assert set(generated) == {"door", "window", "roof"}


def test_expand_emits_a_batch_merge_per_group_plus_final_merge_and_validate():
    """§3.3：每组一条 generate + 一条批次 merge，末尾收尾 merge + validate。"""

    plan = expand_plan(_brief_state())
    generate_ids = [item.id for item in plan.items_by_op("generate")]
    merges = plan.items_by_op("merge")

    batch = [item for item in merges if item.is_batch_merge]
    final = [item for item in merges if item.is_final_merge]

    assert len(batch) == len(generate_ids)
    assert len(final) == 1

    # 每组紧跟自己的 generate，且只依赖它——批次合并只吃自己那一组的分片
    for generate_id, merge in zip(generate_ids, batch):
        assert merge.id == generate_id.replace("generate_", "merge_", 1)
        assert merge.depends_on == [generate_id]
        assert merge.target["component_types"] == [merge.kind]
        # 声明顺序：generate 在前、它的批次 merge 紧跟其后
        assert plan.items.index(merge) == plan.items.index(plan.item(generate_id)) + 1

    # 收尾合并依赖全部批次合并（顺序即批次顺序），校验依赖收尾合并
    assert final[0].id == "merge_all_01"
    assert final[0].depends_on == [item.id for item in batch]
    validate = plan.items_by_op("validate")[0]
    assert validate.depends_on == [final[0].id]

    # 依赖未落定时一律 blocked
    for item in (final[0], validate):
        assert plan.item(item.id).status == "blocked"
    assert all(plan.item(item.id).status == "blocked" for item in batch)


def test_expand_iteration_budget_covers_every_item():
    """条目数翻倍之后，迭代预算必须够跑完最短路径，否则链会在队列跑空前收尾。"""

    plan = expand_plan(_brief_state())
    assert plan.budget["iterations"] >= len(plan.items)

    detailed = expand_plan(_brief_state(), detail_level="detailed")
    assert detailed.budget["iterations"] >= len(detailed.items)


def test_expanded_plan_drains_in_declaration_order():
    """展开出的计划必须按声明顺序跑空，且不出现互等。

    两件事都要钉：① 拓扑不能有循环依赖（有的话 poll_runnable 会返回 None 而队列非空，
    表现为"计划展开了但循环里一条都没跑"）；② 顺序恒等于声明顺序（§4.1），
    否则同一份输入两次执行走不同的路，回归样例失效。
    """

    plan = expand_plan(_brief_state())
    order: list[str] = []
    while (item := poll_runnable(plan)) is not None:
        order.append(item.id)
        plan = record_result(plan, item.id, state="succeeded", count_attempt=False)
        plan = set_status(plan, item.id, "done")
        plan = refresh_statuses(plan)
        assert len(order) <= len(plan.items), "队列没有推进，疑似死锁"

    assert order == [item.id for item in plan.items]
    assert all(item.is_terminal for item in plan.items)
    assert terminal_stats(plan)["unfinished"] == 0


def test_expand_carries_slot_ids_for_openings():
    plan = expand_plan(_brief_state())
    window = next(item for item in plan.items_by_op("generate") if item.kind == "window")
    door = next(item for item in plan.items_by_op("generate") if item.kind == "door")
    assert window.target["source_slots"] == ["slot_win_1"]
    assert window.target["quota"] == {"min": 6, "max": 8}
    assert door.target["source_slots"] == []


def test_expand_includes_quota_minimum_components():
    state = _brief_state()
    state["design_brief"]["component_quota"]["balcony"] = {"min": 1, "max": 2}
    plan = expand_plan(state)
    assert "balcony" in [item.kind for item in plan.items_by_op("generate")]


def test_detail_level_read_from_document_and_budget_is_monotonic():
    state = _brief_state()
    assert resolve_detail_level(state) == "simple"
    assert resolve_detail_level({}) == "standard"
    assert plan_budget("simple") == DETAIL_BUDGET["simple"]
    assert plan_budget("unknown-level") == DETAIL_BUDGET["standard"]

    levels = ["minimal", "simple", "standard", "detailed"]
    iterations = [plan_budget(level)["iterations"] for level in levels]
    assert iterations == sorted(iterations)
    assert len(set(iterations)) == len(levels)


def test_plan_document_rejects_unknown_fields():
    with pytest.raises(ValueError):
        PlanDocument(unexpected_field=True)
