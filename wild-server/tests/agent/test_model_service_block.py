"""方案 A 测试：模型服务故障应阻断生成，不再静默回退到确定性模板。"""

import asyncio
import unittest
from unittest.mock import patch

from app.agent.model_errors import classify_model_error, model_failure_result
from app.agent.nodes.architecture_node import architecture_planner
from app.agent.nodes.execution_plan_node import execution_planner
from app.agent.nodes.classifier_node import classifier_node


def _quota_error():
    return Exception("AllocationQuota.FreeTierOnly: Free quota exhausted")


class _MissingModelError(Exception):
    status_code = 404


class ModelServiceBlockTest(unittest.TestCase):
    def test_classifier_blocks_missing_model_before_any_generation_route(self):
        async def _run():
            with patch(
                "app.agent.intent_classifier.invoke_llm",
                side_effect=_MissingModelError("configured model does not exist"),
            ):
                return await classifier_node({
                    "user_message": "生成一个玻璃幕墙商业综合体",
                    "plan_mode": True,
                })

        out = asyncio.run(_run())
        self.assertEqual(out.get("status"), "failed")
        self.assertEqual(
            out.get("terminal_model_error", {}).get("category"),
            "model_not_found",
        )
        self.assertIn("模型名称", out.get("error", ""))

    def test_classify_quota_error(self):
        info = classify_model_error(_quota_error())
        self.assertEqual(info["category"], "quota_exhausted")
        self.assertFalse(info["retryable"])
        self.assertIn("额度", info["user_message"])

    def test_model_failure_result_shape(self):
        block = model_failure_result(_quota_error())
        self.assertEqual(block["status"], "failed")
        self.assertEqual(block["terminal_model_error"]["category"], "quota_exhausted")
        self.assertIn("terminal_model_error", block)
        self.assertIn("error", block)

    def test_execution_planner_blocks_on_quota(self):
        async def _run():
            state = {
                "user_message": "生成一个别墅",
                "intent": "generate",
                "request_id": "req_block",
                "plan_mode": True,
                "plan_research_summary": "",
                "execution_plan_history": [],
            }
            with patch("app.agent.nodes.execution_plan_node.invoke_llm",
                       side_effect=_quota_error()):
                out = await execution_planner(state)
            return out
        out = asyncio.run(_run())
        self.assertEqual(out.get("status"), "failed")
        self.assertEqual(out.get("terminal_model_error", {}).get("category"), "quota_exhausted")
        self.assertEqual(out.get("execution_plan_status"), "failed")

    def test_architecture_blocks_on_quota(self):
        async def _run():
            state = {
                "user_message": "生成一个别墅",
                "intent": "generate",
                "thinking_mode": False,
                "plan_mode": False,
                "execution_plan": None,
                "style_preference": None,
            }
            with patch("app.agent.nodes.architecture_node.invoke_llm",
                       side_effect=_quota_error()):
                out = await architecture_planner(state)
            return out
        out = asyncio.run(_run())
        self.assertEqual(out.get("status"), "failed")
        self.assertEqual(out.get("terminal_model_error", {}).get("category"), "quota_exhausted")
        # 不应再静默产出确定性方案
        self.assertNotIn("architecture_plan", out)

if __name__ == "__main__":
    unittest.main()
