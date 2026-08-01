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
                name="test-model",
                api_key="test-key",
                base_url="https://example.com/compatible-mode/v1",
            ),
            enable_thinking=True,
            streaming=True,
        )

        self.assertEqual(model.extra_body, {"enable_thinking": True})
        self.assertTrue(model.streaming)

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

