import unittest

from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

from app.agent.model_client import ReasoningChatOpenAI, create_llm
from app.services.agent_service import _ReasoningStreamCallback
from config import ModelConfig


class ReasoningModelAdapterTest(unittest.TestCase):
    def test_thinking_mode_sets_dashscope_request_options(self):
        model = create_llm(
            ModelConfig(
                name="qwen3.8-max",
                api_key="test-key",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            enable_thinking=True,
            streaming=True,
        )

        self.assertEqual(model.extra_body, {
            "enable_thinking": True,
            "thinking_budget": 4096,
        })
        self.assertTrue(model.streaming)

    def test_dashscope_thinking_mode_uses_configured_budget(self):
        model = create_llm(
            ModelConfig(
                name="qwen3.8-max",
                api_key="test-key",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                thinking_budget=8192,
            ),
            enable_thinking=True,
        )

        self.assertEqual(model.extra_body, {
            "enable_thinking": True,
            "thinking_budget": 8192,
        })

    def test_dashscope_workspace_endpoint_is_detected(self):
        model = create_llm(
            ModelConfig(
                name="qwen3.8-max",
                api_key="test-key",
                base_url=(
                    "https://workspace.cn-beijing.maas.aliyuncs.com/"
                    "compatible-mode/v1"
                ),
            ),
            enable_thinking=True,
        )

        self.assertEqual(model.extra_body, {
            "enable_thinking": True,
            "thinking_budget": 4096,
        })

    def test_dashscope_deepseek_maps_budget_to_reasoning_effort(self):
        model = create_llm(
            ModelConfig(
                name="deepseek-v4-pro",
                api_key="test-key",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                thinking_budget=4096,
            ),
            enable_thinking=True,
        )

        self.assertEqual(model.extra_body, {
            "enable_thinking": True,
            "reasoning_effort": "low",
        })

    def test_dashscope_kimi_hybrid_model_uses_exact_budget(self):
        model = create_llm(
            ModelConfig(
                name="kimi-k2.6",
                api_key="test-key",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                thinking_budget=4096,
            ),
            enable_thinking=True,
        )

        self.assertEqual(model.extra_body, {
            "enable_thinking": True,
            "thinking_budget": 4096,
        })

    def test_dashscope_kimi_k3_omits_unsupported_budget(self):
        model = create_llm(
            ModelConfig(
                name="kimi-k3",
                api_key="test-key",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            enable_thinking=True,
        )

        self.assertIsNone(model.extra_body)

    def test_zero_budget_keeps_thinking_and_uses_provider_default(self):
        model = create_llm(
            ModelConfig(
                name="qwen3.8-max",
                api_key="test-key",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                thinking_budget=0,
            ),
            enable_thinking=True,
        )

        self.assertEqual(model.extra_body, {"enable_thinking": True})

    def test_standard_compatible_endpoint_does_not_receive_dashscope_option(self):
        model = create_llm(
            ModelConfig(
                name="qwen3.8-max",
                api_key="test-key",
                base_url="https://api.example.com/v1",
            ),
            enable_thinking=True,
            streaming=True,
        )

        self.assertIsNone(model.extra_body)

    def test_dashscope_non_thinking_request_explicitly_disables_thinking(self):
        model = create_llm(
            ModelConfig(
                name="qwen3.8-max",
                api_key="test-key",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            enable_thinking=False,
            streaming=False,
        )

        self.assertEqual(model.extra_body, {"enable_thinking": False})

    def test_native_deepseek_maps_budget_to_reasoning_effort(self):
        model = create_llm(
            ModelConfig(
                name="deepseek-v4-pro",
                api_key="test-key",
                base_url="https://api.deepseek.com/v1",
                thinking_budget=4096,
            ),
            enable_thinking=True,
        )

        self.assertEqual(model.extra_body, {
            "thinking": {"type": "enabled"},
            "reasoning_effort": "low",
        })

    def test_native_deepseek_reasoner_does_not_receive_unsupported_budget(self):
        model = create_llm(
            ModelConfig(
                name="deepseek-reasoner",
                api_key="test-key",
                base_url="https://api.deepseek.com/v1",
            ),
            enable_thinking=True,
        )

        self.assertIsNone(model.extra_body)

    def test_native_kimi_k3_maps_budget_to_reasoning_effort(self):
        model = create_llm(
            ModelConfig(
                name="kimi-k3",
                api_key="test-key",
                base_url="https://api.moonshot.ai/v1",
                thinking_budget=4096,
            ),
            enable_thinking=True,
        )

        self.assertEqual(model.extra_body, {"reasoning_effort": "low"})

    def test_native_kimi_k3_uses_lowest_effort_for_non_thinking_nodes(self):
        model = create_llm(
            ModelConfig(
                name="kimi-k3",
                api_key="test-key",
                base_url="https://api.moonshot.ai/v1",
                thinking_budget=32768,
            ),
            enable_thinking=False,
        )

        self.assertEqual(model.extra_body, {"reasoning_effort": "low"})

    def test_native_kimi_k26_uses_supported_thinking_toggle_only(self):
        model = create_llm(
            ModelConfig(
                name="kimi-k2.6",
                api_key="test-key",
                base_url="https://api.moonshot.ai/v1",
                thinking_budget=4096,
            ),
            enable_thinking=True,
        )

        self.assertEqual(model.extra_body, {"thinking": {"type": "enabled"}})

    def test_native_kimi_fixed_thinking_model_omits_unsupported_controls(self):
        model = create_llm(
            ModelConfig(
                name="kimi-k2.7-code",
                api_key="test-key",
                base_url="https://api.moonshot.ai/v1",
            ),
            enable_thinking=True,
        )

        self.assertIsNone(model.extra_body)

    def test_reasoning_content_is_preserved_from_stream_chunk(self):
        model = ReasoningChatOpenAI(
            model="test-model",
            api_key="test-key",
            base_url="https://example.com/compatible-mode/v1",
        )
        raw_chunk = {
            "choices": [{
                "delta": {
                    "role": "assistant",
                    "content": None,
                    "reasoning_content": "模型真实思考",
                },
                "finish_reason": None,
            }],
        }

        converted = model._convert_chunk_to_generation_chunk(
            raw_chunk,
            AIMessageChunk,
            {},
        )

        self.assertIsNotNone(converted)
        self.assertEqual(
            converted.message.additional_kwargs["reasoning_content"],
            "模型真实思考",
        )


class ReasoningStreamCallbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_callback_emits_only_reasoning_content(self):
        emitted = []

        async def emit(delta: str):
            emitted.append(delta)

        callback = _ReasoningStreamCallback(emit)
        reasoning_chunk = ChatGenerationChunk(
            message=AIMessageChunk(
                content="",
                additional_kwargs={"reasoning_content": "分析建筑结构"},
            )
        )
        answer_chunk = ChatGenerationChunk(
            message=AIMessageChunk(content="最终回答")
        )

        await callback.on_llm_new_token("", chunk=reasoning_chunk)
        await callback.on_llm_new_token("最终回答", chunk=answer_chunk)
        await callback.flush()

        self.assertEqual(emitted, ["分析建筑结构"])
