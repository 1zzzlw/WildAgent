import app.agent.nodes.style_review_node as style_review_node


def _state() -> dict:
    return {
        "user_message": "生成一栋普通住宅",
        "style_revision": 0,
    }


def test_style_can_be_confirmed_directly(monkeypatch) -> None:
    monkeypatch.setattr(
        style_review_node,
        "interrupt",
        lambda _payload: {"action": "confirm", "style_package_id": "chinese"},
    )

    result = style_review_node.style_review(_state())

    assert result["style_review_status"] == "approved"
    assert result["style_package_id"] == "chinese"
    assert style_review_node.route_style_review(result) == "decor_assembly"


def test_style_feedback_selects_next_package_and_reopens_review(monkeypatch) -> None:
    monkeypatch.setattr(
        style_review_node,
        "interrupt",
        lambda _payload: {"action": "revise", "feedback": "改成克制的欧式古典风格"},
    )

    result = style_review_node.style_review(_state())

    assert result["style_review_status"] == "revise"
    assert result["style_package_id"] == "european"
    assert result["style_revision"] == 1
    assert style_review_node.route_style_review(result) == "style_review"
