import app.agent.nodes.floor_plan_review_node as floor_plan_review_node


def _state(source: str = "model") -> dict:
    return {
        "floor_plan": {"source": source, "fallback_reason": "平面不完整"},
        "floor_plan_validation": [],
        "floor_plan_revision": 0,
        "floor_plan_review_history": [],
    }


def test_confirm_marks_valid_plan_as_approved(monkeypatch) -> None:
    monkeypatch.setattr(
        floor_plan_review_node,
        "interrupt",
        lambda _: {"action": "confirm"},
    )

    result = floor_plan_review_node.floor_plan_review(_state())

    assert result["floor_plan_review_status"] == "approved"
    assert floor_plan_review_node.route_floor_plan_review(result) == "material_plan"


def test_revision_feedback_routes_back_to_floor_plan_design(monkeypatch) -> None:
    monkeypatch.setattr(
        floor_plan_review_node,
        "interrupt",
        lambda _: {"action": "revise", "feedback": "二层主卧增加一扇南向窗"},
    )

    result = floor_plan_review_node.floor_plan_review(_state())

    assert result["floor_plan_review_status"] == "revise"
    assert result["floor_plan_revision"] == 1
    assert result["floor_plan_feedback"] == "二层主卧增加一扇南向窗"
    assert floor_plan_review_node.route_floor_plan_review(result) == "floor_plan_design"


def test_fallback_plan_cannot_be_confirmed(monkeypatch) -> None:
    monkeypatch.setattr(
        floor_plan_review_node,
        "interrupt",
        lambda _: {"action": "confirm"},
    )

    result = floor_plan_review_node.floor_plan_review(_state("deterministic_fallback"))

    assert result["floor_plan_review_status"] == "revise"
    assert "降级轮廓" in result["floor_plan_feedback"]


def test_deterministic_template_can_be_confirmed(monkeypatch) -> None:
    monkeypatch.setattr(
        floor_plan_review_node,
        "interrupt",
        lambda _: {"action": "confirm"},
    )

    result = floor_plan_review_node.floor_plan_review(_state("deterministic_template"))

    assert result["floor_plan_review_status"] == "approved"


def test_rule_failure_retry_explains_measurement_instead_of_calling_it_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        floor_plan_review_node,
        "interrupt",
        lambda _: {"action": "confirm"},
    )
    state = _state("model")
    state["floor_plan_validation"] = [{
        "code": "rule_daylight",
        "message": "空间 living 的窗地面积比为 0.05",
    }]

    result = floor_plan_review_node.floor_plan_review(state)

    assert result["floor_plan_review_status"] == "revise"
    assert result["floor_plan_auto_repairing"] is True
    assert result["floor_plan_auto_repair_count"] == 1
    assert "工程预审未通过" in result["floor_plan_feedback"]
    assert "安全降级轮廓" not in result["floor_plan_feedback"]


def test_rule_failure_pauses_after_bounded_automatic_revisions(monkeypatch) -> None:
    interrupted = {"called": False}

    def decide(_):
        interrupted["called"] = True
        return {"action": "revise", "feedback": "请重新权衡采光和空间布局"}

    monkeypatch.setattr(floor_plan_review_node, "interrupt", decide)
    state = _state("model")
    state["floor_plan_auto_repair_count"] = 2
    state["floor_plan_validation"] = [{
        "code": "rule_daylight",
        "message": "空间 living 的窗地面积比为 0.05",
    }]

    result = floor_plan_review_node.floor_plan_review(state)

    assert interrupted["called"] is True
    assert result["floor_plan_auto_repairing"] is False
    assert result["floor_plan_auto_repair_count"] == 0
