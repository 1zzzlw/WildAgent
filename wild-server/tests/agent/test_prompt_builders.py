"""拆分后的 Prompt 构建器保持结构化输入和明确输出边界。"""

from types import SimpleNamespace

from app.agent.prompts import (
    append_approved_phase_guidance,
    build_blueprint_recovery_messages,
    build_chat_system_prompt,
    build_claim_extraction_prompt,
    build_component_recovery_messages,
    build_component_user_message,
)


def test_chat_prompt_injects_only_supplied_knowledge() -> None:
    prompt = build_chat_system_prompt("[chunk-1] Blueprint 坐标协议")

    assert "[chunk-1] Blueprint 坐标协议" in prompt
    assert "不补建筑百科" in prompt


def test_approved_phase_guidance_is_optional_and_explicit() -> None:
    assert append_approved_phase_guidance("base", "", "must comply") == "base"

    prompt = append_approved_phase_guidance("base", "生成主体", "必须服从白名单")
    assert "已批准执行计划中的本阶段任务" in prompt
    assert "生成主体" in prompt
    assert "必须服从白名单" in prompt


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


def test_research_prompt_contains_source_and_target_topics() -> None:
    result = SimpleNamespace(
        title="幕墙资料",
        url="https://example.com/facade",
        source="example",
        content="幕墙构造正文",
    )
    prompt = build_claim_extraction_prompt([result], ["facade.system"])

    assert "https://example.com/facade" in prompt
    assert "facade.system" in prompt
    assert "只输出 JSON 数组" in prompt
