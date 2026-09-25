"""拆分后的 Prompt 构建器保持结构化输入和明确输出边界。"""

from types import SimpleNamespace

from app.agent.prompts import (
    build_blueprint_recovery_messages,
    build_chat_system_prompt,
    build_component_recovery_messages,
    build_component_user_message,
    build_plan_strategy_prompt,
    build_plan_strategy_user_message,
)


def test_chat_prompt_injects_only_supplied_knowledge() -> None:
    prompt = build_chat_system_prompt("[chunk-1] Blueprint 坐标协议")

    assert "[chunk-1] Blueprint 坐标协议" in prompt
    assert "不补建筑百科" in prompt


def test_plan_strategy_prompt_offers_capabilities_but_forbids_geometry() -> None:
    prompt = build_plan_strategy_prompt(
        capability_catalog=[
            {"kind": "door", "label": "门", "skip_keywords": ["不要门"]},
            {"kind": "roof", "label": "屋顶", "is_element": True},
        ],
        design_brief={"component_quota": {"door": {"min": 1, "max": 2}}},
        skeleton_summary="一层主体",
        detail_level="standard",
        slot_counts={"door": 2},
    )
    user_message = build_plan_strategy_user_message(
        "生成一栋住宅", {"component_quota": {"door": {"min": 1}}}
    )

    # 能力清单是模型的唯一选项来源；工作量与否定词对它可见，坐标对它不可见
    assert "door（门）" in prompt
    assert "不要门" in prompt
    assert "配额下限：1" in prompt
    assert "精确槽位：2 个" in prompt
    assert "不得输出坐标" in prompt
    assert "生成一栋住宅" in user_message and "min" in user_message


def test_recovery_messages_keep_failed_output_bounded() -> None:
    messages = build_blueprint_recovery_messages(
        system_prompt="system",
        user_message="生成别墅",
        failed_reply="x" * 13000,
        design_brief={"component_quota": {"door": {"min": 1}}},
    )

    assert [message["role"] for message in messages] == ["system", "user"]
    assert "geometry.components 必须是空数组" in messages[0]["content"]
    assert len(messages[1]["content"]) < 13000


def test_component_messages_follow_component_shape_and_quota() -> None:
    config = SimpleNamespace(component_type="door", label="门", is_list=True)
    recovery = build_component_recovery_messages(
        config=config,
        system_prompt="system",
        user_message="生成入口",
        failed_reply="not-json",
    )
    user_message = build_component_user_message(
        config,
        {"component_quota": {"door": {"min": 1, "max": 2, "note": "主入口"}}},
    )

    assert "一个 JSON 数组" in recovery[0]["content"]
    assert "1~2 个" in user_message
    assert "只输出 JSON 数组" in user_message
