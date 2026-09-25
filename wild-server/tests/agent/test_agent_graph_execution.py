"""使用真实编译图验证 generate/edit/chat 三条执行分支与图拓扑。

本用例只钉两件别处没覆盖的事：

1. **拓扑形态**：generate 分支经过 architecture → material_plan → design_review →
   skeleton → plan → final_validate；图里**不再有** per-type 节点（``{ct}_gen`` /
   ``{ct}_val``）与旧计划层节点。
2. **旁路在分类处收尾**：chat / edit 直接结束，不进生成链。

条目级执行循环由 ``test_plan_chain_e2e.py`` 钉，这里只把 plan 桩成空计划。
"""

import unittest
from unittest.mock import patch

import app.agent.graph as graph_module


async def _classifier(state: dict) -> dict:
    message = state.get("user_message", "")
    if message.startswith("edit"):
        return {"intent": "edit"}
    if message.startswith("chat"):
        return {"intent": "chat"}
    return {"intent": "generate"}


async def _chat(_state: dict) -> dict:
    return {"chat_reply": "chat-ok", "status": "complete"}


async def _patch(_state: dict) -> dict:
    return {
        "scene_patch": {"operations": [], "summary": "patch-ok"},
        "status": "complete",
    }


async def _architecture(_state: dict) -> dict:
    return {"architecture_plan": {"required_components": []}}


async def _material_plan(_state: dict) -> dict:
    return {"material_plan": {"roles": [], "resolvedAssets": {}}}


def _design_review(_state: dict) -> dict:
    return {"design_review_status": "approved"}


async def _skeleton(_state: dict) -> dict:
    return {
        "skeleton_blueprint": {"meta": {"name": "graph"}, "geometry": {"elements": []}},
        "suggested_components": [],
        "status": "generating",
    }


async def _plan(_state: dict) -> dict:
    """空计划：展开为 0 条条目，图应直接收尾到 final_validate。"""

    return {"plan": {"items": [], "iterations": 0}}


async def _validate(state: dict) -> dict:
    return {
        "final_blueprint": state.get("merged_blueprint") or state["skeleton_blueprint"],
        "validation_results": [],
        "validation_error_count": 0,
        "validation_warning_count": 0,
        "status": "complete",
    }


class GenerationGraphExecutionTest(unittest.IsolatedAsyncioTestCase):
    def _build_graph(self):
        patches = (
            patch.object(graph_module, "classifier_node", _classifier),
            patch.object(graph_module, "chat_node", _chat),
            patch.object(graph_module, "patch_node", _patch),
            patch.object(graph_module, "architecture_planner", _architecture),
            patch.object(graph_module, "material_planner", _material_plan),
            patch.object(graph_module, "design_review", _design_review),
            patch.object(graph_module, "skeleton_generator", _skeleton),
            patch.object(graph_module, "plan_node", _plan),
            patch.object(graph_module, "validate_node", _validate),
        )
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        return graph_module.build_generation_graph(enable_callback=False)

    def test_graph_does_not_register_retired_floor_pipeline(self):
        node_names = set(self._build_graph().get_graph().nodes)

        self.assertTrue({
            "floor_space_analysis",
            "floor_layout",
            "floor_openings",
            "floor_validate",
            "floor_plan_design",
            "floor_plan_review",
            "approved_plan_assembler",
        }.isdisjoint(node_names))
        self.assertTrue({
            "classifier",
            "architecture",
            "material_plan",
            "design_review",
            "skeleton",
            "plan",
            "execute",
            "replanner",
            "final_validate",
        }.issubset(node_names))
        # per-type 节点与旧计划层不再存在：业务顺序在 plan 数据里，不在拓扑里
        self.assertFalse([name for name in node_names if name.endswith(("_gen", "_val"))])
        self.assertTrue({
            "merge",
            "planning_research",
            "web_research",
            "planner",
            "plan_validator",
            "plan_review",
        }.isdisjoint(node_names))

    def test_graph_exposes_only_public_input_fields(self):
        schema = self._build_graph().get_input_jsonschema()

        self.assertEqual(
            set(schema["properties"]),
            {
                "user_message",
                "request_id",
                "session_id",
                "building_type",
                "current_blueprint",
                "selection",
                "recent_messages",
                "workflow_state",
                "thinking_mode",
                "procedural_materials_enabled",
            },
        )
        self.assertEqual(schema.get("required"), ["user_message"])
        self.assertNotIn("execution_plan", schema["properties"])
        self.assertNotIn("architecture_plan", schema["properties"])
        self.assertNotIn("plan", schema["properties"])

    async def test_chat_branch_executes_chat_node(self):
        result = await self._build_graph().ainvoke({"user_message": "chat: hello"})
        self.assertEqual(result["intent"], "chat")
        self.assertEqual(result["chat_reply"], "chat-ok")
        self.assertNotIn("scene_patch", result)

    async def test_edit_branch_executes_patch_node(self):
        result = await self._build_graph().ainvoke({"user_message": "edit: widen door"})
        self.assertEqual(result["intent"], "edit")
        self.assertEqual(result["scene_patch"]["summary"], "patch-ok")
        self.assertNotIn("final_blueprint", result)

    async def test_generate_branch_reaches_final_validation(self):
        result = await self._build_graph().ainvoke({"user_message": "generate: house"})
        self.assertEqual(result["intent"], "generate")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["final_blueprint"]["meta"]["name"], "graph")
        # 空计划不进执行循环
        self.assertIsNone(result.get("current_item_id"))
