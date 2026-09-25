"""对账（唯一计划态写入口）与工具裁剪（《动态节点设计规划》§4.8、§5.2）。"""

import pytest

from app.agent.plan.contracts import PlanItem
from app.agent.plan.expand import expand_plan
from app.agent.plan.reconcile import ensure_artifact_consistency, reconcile
from app.agent.plan.store import new_plan, record_result, set_status
from app.agent.plan.tool_registry import get_tool_registry, tool_names_for, tool_spec, tools_for


def _blueprint(components=None, elements=None):
    return {
        "meta": {"version": "1.1"},
        "geometry": {
            "elements": list(elements or []),
            "components": list(components or []),
        },
        "materials": {},
    }


def _brief_state(**overrides):
    state = {
        "user_message": "生成两层小别墅",
        "suggested_components": ["door", "window"],
        "design_brief": {
            "component_quota": {},
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
    }
    state.update(overrides)
    return state


def _generate_item(item_id, kind):
    return PlanItem(id=item_id, op="generate", kind=kind, label=f"生成{kind}")


# ── 对账 ──


@pytest.mark.parametrize("attempts", [1, 3])
def test_generate_failure_keeps_cause_across_reconciliation(attempts):
    item_id = "generate_window_01"
    plan = new_plan([_generate_item(item_id, "window")])
    cause = "条目内工具调用失败：search_knowledge() missing query"
    for _ in range(attempts):
        plan = record_result(plan, item_id, state="failed", evidence=cause)
    updated, _ = reconcile(plan, _brief_state())
    evidence = updated.item(item_id).run.evidence
    assert cause in evidence
    assert "槽位落地" not in evidence
    assert updated.item(item_id).status == ("ready" if attempts == 1 else "abandoned")
    repeated, _ = reconcile(updated, _brief_state())
    assert repeated.item(item_id).run.evidence == evidence


def test_generate_item_is_not_done_without_artifacts():
    plan = new_plan([_generate_item("generate_window_01", "window")])
    updated, events = reconcile(plan, _brief_state())
    assert updated.item("generate_window_01").status != "done"
    assert events == []


def test_generate_item_done_when_slots_land_on_the_wall():
    plan = new_plan([_generate_item("generate_window_01", "window")])
    state = _brief_state(
        component_fragments={"window": [{"id": "win_1", "type": "window"}]},
        merged_blueprint=_blueprint(
            components=[
                {
                    "id": "win_1",
                    "type": "window",
                    "parentWall": "wall_s_1",
                    "from": [1.0, 1.1, 0],
                    "width": 1.5,
                    "height": 1.6,
                }
            ]
        ),
    )
    updated, events = reconcile(plan, state)
    assert updated.item("generate_window_01").status == "done"
    assert "1/1" in updated.item("generate_window_01").run.evidence
    assert events and events[0]["status"] == "done"


def test_generate_item_stays_open_when_slot_geometry_mismatches():
    plan = new_plan([_generate_item("generate_window_01", "window")])
    state = _brief_state(
        component_fragments={"window": [{"id": "win_1", "type": "window"}]},
        merged_blueprint=_blueprint(
            components=[
                {
                    "id": "win_1",
                    "type": "window",
                    "parentWall": "wall_s_1",
                    "from": [1.0, 1.1, 0],
                    "width": 1.9,  # 与槽位不一致
                    "height": 1.6,
                }
            ]
        ),
    )
    updated, _ = reconcile(plan, state)
    item = updated.item("generate_window_01")
    assert item.status != "done"
    # 状态没变也要留证据，否则前端与 trace 都看不到"为什么一直没完成"。
    assert "0/1" in item.run.evidence


def test_generate_item_falls_back_to_count_when_no_slots():
    plan = new_plan([_generate_item("generate_roof_01", "roof")])
    state = _brief_state(
        design_brief={"component_quota": {}, "opening_slots": []},
        component_fragments={"roof": {"id": "roof_1", "type": "roof"}},
        merged_blueprint=_blueprint(elements=[{"id": "roof_1", "type": "roof"}]),
    )
    updated, _ = reconcile(plan, state)
    assert updated.item("generate_roof_01").status == "done"


def test_exhausted_failure_becomes_abandoned():
    plan = new_plan([_generate_item("generate_window_01", "window")])
    plan = record_result(plan, "generate_window_01", state="failed", evidence="解析失败")
    plan = record_result(plan, "generate_window_01", state="failed", evidence="解析失败")
    plan = record_result(plan, "generate_window_01", state="failed", evidence="解析失败")

    updated, events = reconcile(plan, _brief_state())
    assert updated.item("generate_window_01").status == "abandoned"
    assert events[0]["status"] == "abandoned"


def test_unexhausted_failure_goes_back_to_ready_for_retry():
    plan = new_plan([_generate_item("generate_window_01", "window")])
    plan = record_result(plan, "generate_window_01", state="failed", evidence="首次失败")

    updated, _ = reconcile(plan, _brief_state())
    assert updated.item("generate_window_01").status == "ready"


def _merge_chain():
    """generate → 批次 merge → 收尾 merge，三条条目的最小分组链。"""

    return new_plan(
        [
            _generate_item("generate_window_01", "window"),
            PlanItem(
                id="merge_window_01",
                op="merge",
                kind="window",
                params={"scope": "batch"},
                depends_on=["generate_window_01"],
            ),
            PlanItem(
                id="merge_all_01",
                op="merge",
                params={"scope": "final"},
                depends_on=["merge_window_01"],
            ),
        ]
    )


def _mismatched_window_state():
    """分片已产出、蓝图里没有它（或对不上槽位）——"产物没落地"的原料。"""

    return _brief_state(
        component_fragments={"window": [{"id": "win_1", "type": "window"}]},
        merged_blueprint=_blueprint(components=[]),
    )


def test_batch_merge_alone_does_not_count_as_a_lost_artifact():
    """批次合并跑过、收尾归一还没跑时，不许判"产物没落地"。

    槽位吸附与配额强制只在收尾合并里做，此刻蓝图对不上槽位是正常的中间态；
    拿它当判据会白烧重试额度，把本来能成的条目判成 abandoned。
    """

    plan = _merge_chain()
    plan = record_result(plan, "generate_window_01", state="succeeded", count_attempt=False)
    plan = record_result(plan, "merge_window_01", state="succeeded", count_attempt=False)

    updated, _ = reconcile(plan, _mismatched_window_state())

    item = updated.item("generate_window_01")
    assert item.status == "ready"
    assert "等待收尾归一" in item.run.evidence
    assert item.run.attempts == 0


def test_final_merge_is_the_judge_of_a_lost_artifact():
    """收尾归一跑过仍未落地，才算真的被删掉，这时才计一次重试。"""

    plan = _merge_chain()
    plan = record_result(plan, "generate_window_01", state="succeeded", count_attempt=False)
    plan = record_result(plan, "merge_window_01", state="succeeded", count_attempt=False)
    plan = record_result(plan, "merge_all_01", state="succeeded", count_attempt=False)

    updated, _ = reconcile(plan, _mismatched_window_state())

    item = updated.item("generate_window_01")
    assert item.status == "ready"
    assert "产物未并入蓝图" in item.run.evidence
    assert item.run.attempts == 1


def test_merge_and_validate_follow_run_state():
    plan = new_plan(
        [
            PlanItem(id="merge_all_01", op="merge", label="合并分片"),
            PlanItem(id="validate_all_01", op="validate", label="全量校验"),
        ]
    )
    merged = record_result(plan, "merge_all_01", state="succeeded", count_attempt=False)
    merged = record_result(merged, "validate_all_01", state="failed", evidence="引用缺失")

    updated, events = reconcile(merged, _brief_state())
    assert updated.item("merge_all_01").status == "done"
    assert updated.item("validate_all_01").status == "ready"
    assert updated.item("validate_all_01").run.attempts == 1


def test_reconcile_is_idempotent():
    plan = new_plan([_generate_item("generate_window_01", "window")])
    state = _brief_state(
        component_fragments={"window": [{"id": "win_1", "type": "window"}]},
        merged_blueprint=_blueprint(
            components=[
                {
                    "id": "win_1",
                    "type": "window",
                    "parentWall": "wall_s_1",
                    "from": [1.0, 1.1, 0],
                    "width": 1.5,
                    "height": 1.6,
                }
            ]
        ),
    )
    once, _ = reconcile(plan, state)
    twice, events = reconcile(once, state)
    assert once.model_dump(mode="json") == twice.model_dump(mode="json")
    assert events == []


def test_artifact_consistency_reopens_items_whose_elements_vanished():
    plan = new_plan([_generate_item("generate_roof_01", "roof")])
    plan = reconcile(
        plan,
        _brief_state(
            design_brief={"component_quota": {}, "opening_slots": []},
            component_fragments={"roof": {"id": "roof_1", "type": "roof"}},
            merged_blueprint=_blueprint(elements=[{"id": "roof_1", "type": "roof"}]),
        ),
    )[0]
    assert plan.item("generate_roof_01").status == "done"

    # 配额强制 / 去重把元素删掉之后：交付前必须重新打开这条条目。
    reopened = ensure_artifact_consistency(
        plan, {"merged_blueprint": _blueprint(elements=[])}
    )
    assert reopened.item("generate_roof_01").status == "ready"


def test_reconcile_events_carry_progress_payload():
    plan = new_plan([_generate_item("generate_window_01", "window")])
    plan = record_result(plan, "generate_window_01", state="succeeded", count_attempt=False)
    plan = set_status(plan, "generate_window_01", "blocked")
    _, events = reconcile(plan, _brief_state())
    assert len(events) == 1
    event = events[0]
    assert set(event) == {
        "item_id", "label", "op", "kind", "status", "evidence", "elapsed_ms"
    }
    assert event["item_id"] in {item.id for item in plan.items}


# ── 工具裁剪 ──


def test_tool_spec_defaults_are_fail_closed():
    spec = tool_spec("demo", "validate")
    assert spec.max_calls == 1
    assert spec.read_only is False
    assert spec.concurrency_safe is False
    with pytest.raises(ValueError):
        tool_spec("demo", "unknown-category")


def test_fix_and_mutate_tools_are_only_for_repair_items():
    generate_item = _generate_item("generate_window_01", "window")
    generate_names = tool_names_for(generate_item)
    assert "validate_opening_coords" in generate_names
    assert not any(name.startswith("fix_") for name in generate_names)
    assert "repair_actions" not in generate_names

    repair_names = tool_names_for(PlanItem(id="repair_01", op="repair"))
    assert "fix_opening_coords" in repair_names
    assert "repair_actions" in repair_names


@pytest.mark.parametrize(
    "op",
    ["merge", "validate", "fix"],
)
def test_deterministic_items_receive_no_tools_at_all(op):
    """merge / validate / fix 必须可复现可对账：工具集恒为空，不经过模型（§4.7）。"""

    assert tool_names_for(PlanItem(id=f"{op}_all_01", op=op, kind="all")) == []


def test_disabled_tools_never_enter_the_pool():
    assert "web_search" not in tool_names_for(PlanItem(id="repair_01", op="repair"))


def test_tools_for_is_deterministic_and_sorted():
    item = _generate_item("generate_window_01", "window")
    first = [spec.name for spec in tools_for(item)]
    second = [spec.name for spec in tools_for(item)]
    assert first == second
    assert first == sorted(first, key=lambda name: _sort_key(name))


def _sort_key(name):
    spec = next(spec for spec in get_tool_registry() if spec.name == name)
    return (spec.category, spec.name)
