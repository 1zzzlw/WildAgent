"""使用真实编译图验证 generate/edit/chat 三条执行分支。"""

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


async def _skeleton(_state: dict) -> dict:
    return {
        "skeleton_blueprint": {"meta": {"name": "graph"}, "geometry": {"elements": []}},
        "suggested_components": [],
        "status": "generating",
    }


async def _merge(state: dict) -> dict:
    return {"merged_blueprint": state["skeleton_blueprint"], "status": "validating"}


async def _validate(state: dict) -> dict:
    return {
        "final_blueprint": state["merged_blueprint"],
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
            patch.object(graph_module, "skeleton_generator", _skeleton),
            patch.object(graph_module, "merge_fragments_node", _merge),
            patch.object(graph_module, "get_implemented_components", return_value=[]),
            patch.object(graph_module, "resolve_component_suggestions", return_value=[]),
            patch("app.agent.nodes.validate_node.validate_node", _validate),
        )
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        return graph_module.build_generation_graph(enable_callback=False)

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
