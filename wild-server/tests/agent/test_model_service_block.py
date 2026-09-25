"""模型服务故障应阻断生成，不再静默回退到确定性模板。

节点层面的契约：模型不可用 / 额度耗尽 → ``terminal_model_error`` + ``status=failed``，
图随即终止，不进修复循环（``graph._after_*`` 都先看这个字段）。

`plan` 用模型决定批次与并发策略；模型服务故障必须终止，程序只负责合法化和展开。
"""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.agent.nodes.architecture_node import architecture_planner
from app.agent.nodes.classifier_node import classifier_node
from app.agent.nodes.plan_node import plan_node
from app.llm.errors import classify_model_error, model_failure_result


def _quota_error():
    return Exception("AllocationQuota.FreeTierOnly: Free quota exhausted")


class _MissingModelError(Exception):
    status_code = 404


class ModelServiceBlockTest(unittest.TestCase):
    def test_classifier_blocks_missing_model_before_any_generation_route(self):
        async def _run():
            with patch(
                "app.agent.routing.invoke_llm",
                side_effect=_MissingModelError("configured model does not exist"),
            ):
                return await classifier_node({"user_message": "生成一个玻璃幕墙商业综合体"})

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

    def test_architecture_blocks_on_quota(self):
        async def _run():
            state = {
                "user_message": "生成一个别墅",
                "intent": "generate",
                "thinking_mode": False,
                "style_preference": None,
            }
            with patch("app.agent.generation.architecture.workflow.invoke_llm",
                       side_effect=_quota_error()):
                return await architecture_planner(state)

        out = asyncio.run(_run())
        self.assertEqual(out.get("status"), "failed")
        self.assertEqual(out.get("terminal_model_error", {}).get("category"), "quota_exhausted")
        # 不应再静默产出确定性方案
        self.assertNotIn("architecture_plan", out)

    def test_plan_strategy_blocks_on_model_failure(self):
        """plan 模型不可用时终止，不能伪装成已经完成了智能规划。"""

        async def _run():
            state = {
                "user_message": "生成一个带入户门的单层住宅",
                "design_brief": {"component_quota": {"door": {"min": 1, "max": 2}}},
                "suggested_components": ["door"],
            }
            with patch("app.agent.plan.strategy.invoke_llm", side_effect=_quota_error()):
                return await plan_node(state)

        out = asyncio.run(_run())
        self.assertEqual(out.get("status"), "failed")
        self.assertEqual(out["terminal_model_error"]["category"], "quota_exhausted")
        self.assertNotIn("plan", out)

    def test_plan_strategy_degrades_when_model_replies_without_a_plan(self):
        """模型输出无效时才降级，配额仍是程序的硬约束。"""

        async def _run():
            state = {
                "user_message": "生成一个带入户门的单层住宅",
                "design_brief": {"component_quota": {"door": {"min": 1, "max": 2}}},
                "suggested_components": ["door"],
            }
            reply = SimpleNamespace(content='{"kinds": []}', token_usage=None)

            async def fake_invoke(_llm, _messages):
                return reply

            with patch("app.agent.plan.strategy.invoke_llm", fake_invoke):
                return await plan_node(state)

        out = asyncio.run(_run())
        self.assertNotIn("status", out)
        self.assertTrue(out["plan_diag"]["used_fallback"])
        self.assertEqual(
            [item["kind"] for item in out["plan"]["items"] if item["op"] == "generate"],
            ["door"],
        )


if __name__ == "__main__":
    unittest.main()
