import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.agent.model_client import (
    ReasoningChatOpenAI,
    _response_mapping,
    content_as_text,
    message_texts,
)


class _PydanticLikeResponse:
    def __init__(self, data):
        self.data = data

    def model_dump(self):
        return self.data


class ModelClientCompatibilityTest(unittest.TestCase):
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
