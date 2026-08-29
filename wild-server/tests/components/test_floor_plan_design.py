from app.agent.spatial_plan import (
    fallback_spatial_plan,
    is_confirmable_spatial_plan,
    recover_confirmable_spatial_plan,
    validate_spatial_plan,
)


def test_invalid_first_model_plan_becomes_directly_confirmable_baseline() -> None:
    massing = {
        "shape": "rectangle",
        "width": 12.0,
        "depth": 9.0,
        "floor_height": 3.2,
        "modeled_floors": 2,
    }
    fallback = fallback_spatial_plan(massing, "模型平面不连通")

    recovered, used = recover_confirmable_spatial_plan(
        None,
        fallback,
        massing,
        [],
    )
    issues = validate_spatial_plan(recovered)

    assert used is True
    assert recovered["source"] == "deterministic_template"
    assert issues == []
    assert is_confirmable_spatial_plan(recovered, issues) is True
    assert all(len(level["spaces"]) == 2 for level in recovered["levels"])


def test_valid_model_plan_is_not_replaced() -> None:
    model_plan = {"source": "model", "levels": [{"level": 1}]}

    recovered, used = recover_confirmable_spatial_plan(
        None,
        model_plan,
        {},
        [],
    )

    assert used is False
    assert recovered is model_plan
