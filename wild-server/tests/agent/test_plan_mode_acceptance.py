"""plan 模式的端到端图集成测试。

链路：动态任务 → 结构化要求 → 节点消费 → 验收结果。

这些用例运行的是**真实编译图**：真实的 planner/validator/review 契约、真实的
`interrupt` 审核暂停、真实的 `_planned_node` 阶段边界验收。只把模型调用、RAG
检索和设计仓储替换为确定性 stub，因此可以离线复现文档 §9 的验收标准。
"""

import json
import unittest
from unittest.mock import patch

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

import app.agent.graph as graph_module
from app.agent.planning.execution import build_execution_plan
from app.agent.planning.requirements import (
    compile_structured_requirements,
    initial_execution_progress,
    initialize_acceptance_results,
)


_PLAN_TASKS = [
    {
        "title": "确定两层主体",
        "objective": "确定建筑体量与层数",
        "phase": "architecture",
        "acceptance": ["建筑必须为两层"],
        "basis": "用户需求",
    },
    {
        "title": "生成主体结构",
        "objective": "生成主体并保证结构表达完整",
        "phase": "skeleton",
        "acceptance": ["主体必须包含柱和梁"],
        "basis": "用户需求",
    },
    {
        "title": "最终校验",
        "objective": "验证交付结果",
        "phase": "final_validate",
        "acceptance": ["完整校验零错误"],
        "basis": "WILD 协议",
    },
]


def _structure_blueprint(*element_types: str) -> dict:
    return {
        "meta": {"name": "plan-mode-graph"},
        "geometry": {
            "elements": [
                {"id": f"{item}_{index}", "type": item}
                for index, item in enumerate(element_types)
            ],
            "components": [],
        },
    }


class PlanModeAcceptanceTest(unittest.IsolatedAsyncioTestCase):
    """真实图上的计划—约束—执行—验收闭环。"""

    def _planner_payload(self, state: dict) -> dict:
        plan = build_execution_plan(
            request_id=str(state.get("request_id") or "req_graph_plan"),
            intent="generate",
            user_message=str(state.get("user_message") or "生成一个两层住宅"),
            planned_tasks=_PLAN_TASKS,
            planner_source="llm",
        )
        # 任务被归一化拒绝时会退化成 fallback 计划，用例必须显式失败而不是静默变弱。
        self.assertEqual(plan["planner_source"], "llm", plan["dynamic_tasks"])
        requirements = compile_structured_requirements(plan)
        return {
            "execution_plan": plan,
            "structured_requirements": requirements,
            "acceptance_results": initialize_acceptance_results(requirements),
            "execution_progress": initial_execution_progress("generate"),
            "execution_plan_status": "draft",
            "execution_plan_review_status": "pending",
            "plan_feedback_pending": False,
        }

    def _install_stubs(self, blueprint: dict) -> None:
        """替换模型、RAG 与设计仓储；图结构和计划契约保持真实。"""

        async def classifier(_state):
            return {"intent": "generate"}

        async def research(_state):
            return {"plan_research_summary": "已读取本地能力协议"}

        async def planner(state):
            return self._planner_payload(state)

        async def architecture(_state):
            return {
                "architecture_plan": {
                    "massing": {"floors": 2, "width": 12, "depth": 9},
                    "roof": {"type": "gable"},
                    "required_components": [],
                }
            }

        async def material_plan(_state):
            return {"material_plan": {"roles": [{"role": "facade"}], "resolvedAssets": {}}}

        def design_review(_state):
            return {"design_review_status": "approved"}

        async def skeleton(_state):
            return {
                "skeleton_blueprint": blueprint,
                "suggested_components": [],
                "status": "generating",
            }

        async def merge(_state):
            return {"merged_blueprint": blueprint, "status": "validating"}

        async def validate(_state):
            return {
                "final_blueprint": blueprint,
                "validation_results": [],
                "validation_error_count": 0,
                "validation_warning_count": 0,
                "status": "complete",
            }

        patches = (
            patch.object(graph_module, "classifier_node", classifier),
            patch.object(graph_module, "planning_research", research),
            patch.object(graph_module, "execution_planner", planner),
            patch.object(graph_module, "architecture_planner", architecture),
            patch.object(graph_module, "material_planner", material_plan),
            patch.object(graph_module, "design_review", design_review),
            patch.object(graph_module, "skeleton_generator", skeleton),
            patch.object(graph_module, "merge_fragments_node", merge),
            patch.object(graph_module, "get_implemented_components", return_value=[]),
            patch.object(graph_module, "resolve_component_suggestions", return_value=[]),
            patch("app.agent.nodes.validate_node.validate_node", validate),
        )
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    async def _run_plan_mode(self, blueprint: dict, thread_id: str) -> dict:
        """先跑到计划审核暂停，批准后继续跑到终态。"""

        self._install_stubs(blueprint)
        compiled = graph_module.build_generation_graph(
            enable_callback=False,
            checkpointer=InMemorySaver(),
        )
        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 80,
        }
        paused = await compiled.ainvoke(
            {
                "user_message": "生成一个两层住宅",
                "request_id": "req_graph_plan",
                "plan_mode": True,
            },
            config,
        )
        self.assertIn("__interrupt__", paused)
        self.assertEqual(paused["execution_plan_review_status"], "pending")
        return await compiled.ainvoke(
            Command(resume={"action": "confirm"}),
            config,
        )

    async def test_approved_plan_runs_all_stages_and_accepts_each_requirement(self):
        blueprint = _structure_blueprint("wall", "column", "beam")

        result = await self._run_plan_mode(blueprint, "plan-mode-happy")

        self.assertEqual(result["execution_plan_status"], "completed")
        self.assertEqual(
            {task["status"] for task in result["execution_plan"]["dynamic_tasks"]},
            {"completed"},
        )
        self.assertEqual(
            {item["status"] for item in result["acceptance_results"].values()},
            {"passed"},
        )
        for stage in ("architecture", "material_plan", "skeleton", "merge", "final_validate"):
            self.assertEqual(result["execution_progress"][stage]["status"], "completed")
        self.assertIsNotNone(result["final_blueprint"])

    async def test_running_success_does_not_hide_failed_business_acceptance(self):
        """节点全部运行成功，但批准的结构要求未实现时不得宣告完成。"""

        blueprint = _structure_blueprint("wall")

        result = await self._run_plan_mode(blueprint, "plan-mode-blocked")

        # 节点运行进度：最终校验节点本身跑完了。
        self.assertEqual(result["execution_progress"]["final_validate"]["status"], "completed")
        self.assertEqual(result["validation_error_count"], 0)
        # 业务完成状态：批准要求未实现，交付被阻断。
        self.assertEqual(result["execution_plan_status"], "failed")
        self.assertIn("业务验收未通过", result["error"])
        self.assertIsNone(result["final_blueprint"])

        failed_task = result["execution_plan"]["dynamic_tasks"][1]
        self.assertEqual(failed_task["status"], "failed")
        structural = result["acceptance_results"]["acc_task_2_1"]
        self.assertEqual(structural["status"], "failed")
        self.assertEqual(structural["observed"], {"column": 0, "beam": 0})
        self.assertEqual(structural["validator"], "element_presence")

    async def test_every_requirement_carries_a_traceable_consumer_and_result(self):
        """四条链可追踪：动态任务 → 结构化要求 → 消费节点 → 验收结果。"""

        blueprint = _structure_blueprint("wall", "column", "beam")

        result = await self._run_plan_mode(blueprint, "plan-mode-trace")

        tasks = {task["id"] for task in result["execution_plan"]["dynamic_tasks"]}
        requirements = result["structured_requirements"]
        results = result["acceptance_results"]
        self.assertEqual({item["source_task_id"] for item in requirements}, tasks)
        for requirement in requirements:
            self.assertTrue(requirement["consumers"])
            self.assertTrue(requirement["validator"])
            self.assertEqual(requirement["support_status"], "supported")
            outcome = results[requirement["source_acceptance_id"]]
            self.assertEqual(outcome["requirement_id"], requirement["id"])
            self.assertEqual(outcome["status"], "passed")
            self.assertEqual(outcome["validator"], requirement["validator"])

    async def test_plan_state_fields_stay_serializable_for_tracing(self):
        """新 State 字段必须能进入 checkpoint 与 Trace。"""

        blueprint = _structure_blueprint("wall", "column", "beam")

        result = await self._run_plan_mode(blueprint, "plan-mode-serializable")

        for field in (
            "structured_requirements",
            "acceptance_results",
            "execution_progress",
        ):
            json.dumps(result[field])


if __name__ == "__main__":
    unittest.main()
