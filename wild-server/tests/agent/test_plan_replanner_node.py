"""replanner / execute / plan 三个节点的行为回归（《动态节点设计规划》§四、§五）。

与 ``test_plan_chain_e2e.py`` 的分工：那边跑完整图，这边只钉单个节点的契约——
尤其是"什么时候才调模型"这条成本红线（§5.1）。
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import app.agent.plan.workflow as workflow_module
from app.agent.plan.contracts import ItemRun, PlanItem
from app.agent.plan.store import new_plan
from app.agent.plan.workflow import execute_node, replanner_node


def _plan(*items: PlanItem):
    return new_plan(list(items))


def _state(plan, **extra):
    return {"plan": plan.model_dump(mode="json"), **extra}


class ReplannerModelCallTest(unittest.IsolatedAsyncioTestCase):
    """快路径不调模型；异常路径调一次且只能选闭集动作。"""

    async def _replanner(self, plan, *, decision=None, calls=None):
        from app.agent.plan.replan import ReplanDecision

        async def fake_request_replan(current_plan, state, **kwargs):
            if calls is not None:
                calls.append(current_plan.iterations)
            chosen = decision or ReplanDecision(
                action="give_up", reason="测试桩", source="llm"
            )
            return chosen, {"decision_source": chosen.source, "model_called": True}

        with patch.object(workflow_module, "request_replan", fake_request_replan):
            return await replanner_node(_state(plan))

    async def test_healthy_round_never_calls_the_model(self):
        """generate 已成功、merge 待跑：这是健康路径，一次模型调用都不该发生。"""

        plan = _plan(
            PlanItem(id="generate_door_01", op="generate", kind="door"),
            PlanItem(id="merge_all_01", op="merge", kind="all", depends_on=["generate_door_01"]),
        )
        calls: list[int] = []

        result = await self._replanner(plan, calls=calls)

        self.assertEqual(calls, [])
        self.assertNotIn("replan", result["replanner_diag"])
        self.assertEqual(result["replanner_diag"]["llm_calls_total"], 0)
        self.assertEqual(result["replanner_diag"]["iterations"], 1)

    async def test_failed_item_triggers_exactly_one_model_call(self):
        plan = _plan(
            PlanItem(
                id="generate_door_01",
                op="generate",
                kind="door",
                run=ItemRun(state="failed", attempts=1, max_attempts=3),
            )
        )
        calls: list[int] = []

        result = await self._replanner(plan, calls=calls)

        self.assertEqual(calls, [0])  # 一轮一次，不是每轮都调
        self.assertIn("replan", result["replanner_diag"])
        self.assertEqual(result["replanner_diag"]["llm_calls_total"], 1)

    async def test_first_failure_give_up_is_overridden_by_bounded_replacement(self):
        """模型不能在首次失败时跳过调整，直接结束整份计划。"""

        plan = _plan(
            PlanItem(
                id="generate_door_01",
                op="generate",
                kind="door",
                # 还有重试额度（reconcile 不会直接判 abandoned），所以异常分支会跑
                run=ItemRun(state="failed", attempts=1, max_attempts=3),
            )
        )

        result = await self._replanner(plan)

        stored = result["plan"]
        self.assertFalse(stored["give_up"])
        self.assertEqual(stored["items"][0]["run"]["state"], "idle")
        outcome = result["replanner_diag"]["replan"]["outcome"]
        self.assertEqual(outcome["action"], "replace_item")
        self.assertTrue(outcome["policy_override"])

    async def test_iteration_budget_still_leaves_final_merge_runnable(self):
        plan = _plan(
            PlanItem(id="generate_door_01", op="generate", kind="door"),
            PlanItem(
                id="merge_door_01",
                op="merge",
                kind="door",
                depends_on=["generate_door_01"],
                params={"scope": "batch"},
            ),
            PlanItem(
                id="merge_all_01",
                op="merge",
                kind="all",
                depends_on=["merge_door_01"],
                params={"scope": "final"},
            ),
            PlanItem(
                id="validate_all_01",
                op="validate",
                kind="all",
                depends_on=["merge_all_01"],
            ),
        )
        plan.budget = {"iterations": 1, "llm_calls": 99}

        result = await self._replanner(plan)

        stored = result["plan"]
        self.assertTrue(stored["give_up"])
        self.assertEqual(stored["items"][0]["status"], "skipped")
        self.assertEqual(stored["items"][1]["status"], "ready")
        self.assertEqual(result["replanner_diag"]["next_item_id"], "merge_door_01")

    async def test_rejected_decision_does_not_corrupt_the_plan(self):
        from app.agent.plan.replan import ReplanDecision

        plan = _plan(
            PlanItem(
                id="generate_door_01",
                op="generate",
                kind="door",
                run=ItemRun(state="failed", attempts=1, max_attempts=3),
            )
        )

        result = await self._replanner(
            plan,
            decision=ReplanDecision(action="replace_item", item_id="不存在_01", source="llm"),
        )

        outcome = result["replanner_diag"]["replan"]["outcome"]
        self.assertFalse(outcome["applied"])
        self.assertIn("不存在", outcome["rejected"])
        self.assertEqual(len(result["plan"]["items"]), 1)

    async def test_replace_item_handles_a_plan_whose_raw_snapshot_exceeds_field_limit(self):
        from app.agent.plan.replan import ReplanDecision

        items = [
            PlanItem(id=f"generate_component_{index:03d}", op="generate", kind="wall")
            for index in range(20)
        ]
        items[0].run = ItemRun(state="failed", attempts=1, max_attempts=3)
        plan = _plan(*items)

        result = await self._replanner(
            plan,
            decision=ReplanDecision(
                action="replace_item",
                item_id=items[0].id,
                reason="更换生成策略后重试",
                source="llm",
            ),
        )

        self.assertTrue(result["replanner_diag"]["replan"]["outcome"]["applied"])
        self.assertEqual(len(result["plan"]["last_progress_signature"]), 64)
        self.assertEqual(result["plan"]["items"][0]["run"]["state"], "idle")


class ExecuteNodeContractTest(unittest.IsolatedAsyncioTestCase):
    """execute 只做一条、写执行态、把审计轨迹挂在条目上。"""

    async def test_no_runnable_item_reports_and_returns(self):
        plan = _plan(
            PlanItem(id="validate_all_01", op="validate", kind="all", status="done"),
        )

        result = await execute_node(_state(plan))

        self.assertIsNone(result["current_item_id"])
        self.assertEqual(result["execute_diag"]["item_id"], None)

    async def test_deterministic_item_runs_without_counting_model_calls(self):
        plan = _plan(PlanItem(id="merge_all_01", op="merge", kind="all"))

        result = await execute_node(
            _state(plan, merged_blueprint={"geometry": {"elements": [], "components": []}})
        )

        self.assertEqual(result["execute_diag"]["op"], "merge")
        self.assertEqual(result["execute_diag"]["model_calls"], 0)
        self.assertEqual(result["plan"]["llm_calls"], 0)
        # 执行态由本节点写：一条条目跑过就必须留下 attempts / run_state 痕迹
        stored = result["plan"]["items"][0]
        self.assertEqual(stored["id"], "merge_all_01")
        self.assertNotEqual(stored["run"]["state"], "idle")

    async def test_prefetch_trace_does_not_count_as_a_model_call(self):
        """审计轨迹里的预取/确定性条目带 mode 字段，不能被误算成模型调用。"""

        plan = _plan(
            PlanItem(
                id="generate_door_01",
                op="generate",
                kind="door",
                params={"component_type": "door"},
            )
        )

        async def fake_handler(state, item):
            return (
                {"component_fragments": {"door": [{"id": "door_1", "type": "door"}]}},
                "succeeded",
                ["door_1"],
                "产出 1 个片段",
                [
                    {"tool": "search_knowledge", "mode": "prefetch", "ok": True, "chars": 120},
                    {"tool": "validate_component", "mode": "deterministic", "ok": True, "chars": 0},
                ],
            )

        with patch.dict(workflow_module.HANDLERS, {"generate": fake_handler}):
            result = await execute_node(_state(plan))

        self.assertEqual(result["execute_diag"]["model_calls"], 1)
        self.assertEqual(result["plan"]["llm_calls"], 1)

    async def test_independent_plan_group_executes_concurrently(self):
        active = 0
        max_active = 0

        async def fake_handler(state, item):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await __import__("asyncio").sleep(0)
            active -= 1
            fragment = {"id": f"{item.kind}_1", "type": item.kind}
            return (
                {"component_fragments": {item.kind: [fragment]}},
                "succeeded",
                [fragment["id"]],
                f"{item.kind} 批次完成",
                [],
            )

        plan = _plan(
            PlanItem(
                id="generate_door_01",
                op="generate",
                kind="door",
                params={"execution_mode": "parallel", "parallel_group": "openings"},
            ),
            PlanItem(
                id="generate_window_02",
                op="generate",
                kind="window",
                params={"execution_mode": "parallel", "parallel_group": "openings"},
            ),
        )

        with patch.dict(workflow_module.HANDLERS, {"generate": fake_handler}):
            result = await execute_node(_state(plan))

        self.assertEqual(max_active, 2)
        self.assertEqual(result["execute_diag"]["parallel_count"], 2)
        self.assertEqual(set(result["component_fragments"]), {"door", "window"})
        self.assertEqual(
            {item["run"]["state"] for item in result["plan"]["items"]},
            {"succeeded"},
        )


if __name__ == "__main__":
    unittest.main()
