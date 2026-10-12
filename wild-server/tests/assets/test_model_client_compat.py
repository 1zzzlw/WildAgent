import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.llm.client import (
    ReasoningChatOpenAI,
    _response_mapping,
    content_as_text,
    message_texts,
    create_llm,
)
from config import ModelConfig


class _PydanticLikeResponse:
    def __init__(self, data):
        self.data = data

    def model_dump(self):
        return self.data


class ModelClientCompatibilityTest(unittest.TestCase):
    def test_mimo_token_plan_can_disable_thinking(self):
        model = create_llm(ModelConfig(name="mimo-v2.6-flash", api_key="test-key",
            base_url="https://token-plan-cn.xiaomimimo.com/v1"), enable_thinking=False)
        self.assertEqual(model.extra_body, {"thinking": {"type": "disabled"}})

    def test_explicit_mimo_provider_uses_its_protocol_at_a_custom_endpoint(self):
        model = create_llm(ModelConfig(provider="mimo", name="mimo-v2.6-flash", api_key="test-key",
            base_url="https://proxy.example/v1"), enable_thinking=False)
        self.assertEqual(model.extra_body, {"thinking": {"type": "disabled"}})

    def test_mimo_thinking_switch_does_not_send_unsupported_budget(self):
        cfg = ModelConfig(base_url="https://api.xiaomimimo.com/v1", name="mimo-v2.6-flash", api_key="test-key", thinking_budget=4096)
        self.assertEqual(create_llm(cfg, enable_thinking=True).extra_body, {"thinking": {"type": "enabled"}})
        self.assertEqual(create_llm(cfg, enable_thinking=False).extra_body, {"thinking": {"type": "disabled"}})
        cfg.base_url = "https://other-compatible.example/v1"
        self.assertIsNone(create_llm(cfg, enable_thinking=False).extra_body)

    def test_content_as_text_accepts_openai_content_blocks(self):
        self.assertEqual(
            content_as_text([
                {"type": "text", "text": "WILD"},
                {"type": "output_text", "output_text": "_OK"},
            ]),
            "WILD\n_OK",
        )

    def test_message_texts_keeps_reasoning_when_content_is_empty(self):
        message = SimpleNamespace(
            content="",
            additional_kwargs={"reasoning_content": "WILD_OK"},
            response_metadata={},
        )

        self.assertEqual(message_texts(message), ("", "WILD_OK"))

    def test_response_mapping_accepts_chat_completion_object(self):
        response = _PydanticLikeResponse({
            "choices": [{
                "message": {
                    "content": "answer",
                    "reasoning_content": "reasoning",
                },
            }],
        })

        mapped = _response_mapping(response)

        self.assertEqual(mapped["choices"][0]["message"]["content"], "answer")

    def test_non_stream_result_keeps_reasoning_for_object_response(self):
        response = _PydanticLikeResponse({
            "choices": [{
                "message": {
                    "content": "answer",
                    "reasoning_content": "reasoning",
                },
            }],
        })
        generation = SimpleNamespace(
            message=SimpleNamespace(additional_kwargs={}),
        )
        parent_result = SimpleNamespace(generations=[generation])

        with patch.object(
            ReasoningChatOpenAI.__mro__[1],
            "_create_chat_result",
            return_value=parent_result,
        ):
            model = object.__new__(ReasoningChatOpenAI)
            result = ReasoningChatOpenAI._create_chat_result(model, response)

        self.assertIs(result, parent_result)
        self.assertEqual(
            generation.message.additional_kwargs["reasoning_content"],
            "reasoning",
        )


if __name__ == "__main__":
    unittest.main()
