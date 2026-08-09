import unittest
from unittest.mock import patch

from app.agent.nodes import skeleton_node


class _FakeResponse:
    content = """
    {
      "blueprint": {
        "meta": {"version": "1.1", "type": "building", "name": "恢复骨架"},
        "geometry": {"elements": [{"id": "floor_1", "type": "floor"}], "components": []},
        "materials": {}
      }
    }
    """
    response_metadata = {
        "finish_reason": "stop",
        "token_usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        },
    }


class _FakeLLM:
    async def ainvoke(self, messages):
        self.messages = messages
        return _FakeResponse()


class SkeletonBlueprintRecoveryTest(unittest.IsolatedAsyncioTestCase):
    async def test_recovery_uses_non_thinking_model_and_extracts_wrapped_blueprint(self):
        fake_llm = _FakeLLM()
        with patch.object(skeleton_node, "create_llm", return_value=fake_llm) as create:
            blueprint, diag = await skeleton_node._recover_blueprint_json(
                system_prompt="骨架规则",
                user_message="生成两层别墅",
                failed_reply='DESIGN_BRIEF: {"component_quota": {"door": {"min": 1}}}',
                design_brief={"component_quota": {"door": {"min": 1}}},
            )

        create.assert_called_once_with(enable_thinking=False, streaming=False)
        self.assertEqual(blueprint["meta"]["name"], "恢复骨架")
        self.assertTrue(diag["success"])
        self.assertEqual(diag["token_usage"]["total"], 30)
        self.assertIn("只能输出一个严格合法的 JSON 对象", fake_llm.messages[0]["content"])

    def test_token_usage_is_merged(self):
        merged = skeleton_node._merge_token_usage(
            {"input": 10, "output": 20, "total": 30},
            {"input": 5, "output": 7, "total": 12},
        )
        self.assertEqual(merged, {"input": 15, "output": 27, "total": 42})


if __name__ == "__main__":
    unittest.main()
