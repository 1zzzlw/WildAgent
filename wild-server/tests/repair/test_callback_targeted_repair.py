import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.agent.nodes.callback_node import callback_node
from app.agent.nodes.validate_node import validate_node
from app.agent.graph import build_generation_graph


def _state_blueprint() -> dict:
    return {
        "meta": {"version": "1.1", "type": "building", "name": "callback-test"},
        "geometry": {
            "elements": [{
                "id": "wall_front",
                "type": "wall",
                "from": [0, 0, 0],
                "to": [6, 3, 0],
                "thickness": 0.2,
            }],
            "components": [
                {
                    "id": "door_front",
                    "type": "door",
                    "parentWall": "wall_front",
                    "from": [2.0, 0, 0],
                    "width": 1.2,
                    "height": 2.2,
                },
                {
                    "id": "window_front",
                    "type": "window",
                    "parentWall": "wall_front",
                    "from": [2.8, 0.9, 0],
                    "width": 1.4,
                    "height": 1.2,
                },
            ],
        },
        "materials": {},
        "behaviors": {},
    }


class _FakeLLM:
    def __init__(self, content=None):
        self.content = content or '''
        [{
          "tool": "move_opening",
          "arguments": {"entity_id": "door_front", "along": 0.5},
          "reason": "移出与门的重叠区"
        }]
        '''

    async def ainvoke(self, _messages):
        return SimpleNamespace(content=self.content)


class _QuotaError(RuntimeError):
    status_code = 403


class _FailingLLM:
    async def ainvoke(self, _messages):
        raise _QuotaError("Free quota exhausted")


class CallbackTargetedRepairTest(unittest.IsolatedAsyncioTestCase):
    async def test_callback_model_failure_preserves_retry_counts_and_stops(self):
        blueprint = _state_blueprint()
        validation = await validate_node({"merged_blueprint": blueprint})
        state = {
            **validation,
            "merged_blueprint": blueprint,
            "skeleton_blueprint": blueprint,
            "skeleton_summary": "一面 6m 长墙",
            "retry_count": 0,
            "max_retries": 3,
            "component_retry_counts": {},
            "thinking_mode": False,
        }

        with (
            patch("app.agent.nodes.callback_node.create_llm", return_value=_FailingLLM()),
            patch(
                "app.services.agent_service.agent_service.spec_loader.load_many",
                return_value="",
            ),
        ):
            result = await callback_node(state)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["retry_count"], 1)
        self.assertTrue(result["component_retry_counts"])
        self.assertEqual(result["terminal_model_error"]["category"], "quota_exhausted")
        self.assertNotIn("Free quota", result["error"])

    async def test_callback_commits_only_tool_action_that_reduces_errors(self):
        blueprint = _state_blueprint()
        validation = await validate_node({"merged_blueprint": blueprint})
        skeleton = {
            **blueprint,
            "geometry": {
                "elements": blueprint["geometry"]["elements"],
                "components": [],
            },
        }
        state = {
            **validation,
            "merged_blueprint": blueprint,
            "skeleton_blueprint": skeleton,
            "skeleton_summary": "一面 6m 长墙",
            "door_fragments": [blueprint["geometry"]["components"][0]],
            "window_fragments": [blueprint["geometry"]["components"][1]],
            "retry_count": 0,
            "max_retries": 3,
            "component_retry_counts": {},
            "thinking_mode": False,
        }

        with (
            patch("app.agent.nodes.callback_node.create_llm", return_value=_FakeLLM()),
            patch(
                "app.services.agent_service.agent_service.spec_loader.load_many",
                return_value="",
            ),
        ):
            result = await callback_node(state)

        self.assertTrue(result["repair_audit"]["accepted"])
        self.assertEqual(result["repair_audit"]["after_issue_count"], 0)
        self.assertEqual(result["component_fragments"]["door"][0]["from"][0], 0.5)
        self.assertEqual(
            result["merged_blueprint"]["geometry"]["components"][0]["from"][0],
            0.5,
        )
        self.assertNotIn("window_fragments", result)
        self.assertEqual(state["window_fragments"][0]["from"][0], 2.8)

    async def test_validate_node_preserves_retry_metrics(self):
        result = await validate_node({
            "merged_blueprint": _state_blueprint(),
            "retry_count": 2,
            "max_retries": 3,
        })

        self.assertEqual(result["retry_count"], 2)
        self.assertEqual(result["max_retries"], 3)

    def test_callback_routes_to_validation_without_remerge(self):
        graph = build_generation_graph(enable_callback=True).get_graph()
        edges = {(edge.source, edge.target) for edge in graph.edges}

        self.assertIn(("callback", "final_validate"), edges)
        self.assertNotIn(("callback", "merge"), edges)

    async def test_callback_can_add_component_required_by_design_quota(self):
        blueprint = _state_blueprint()
        blueprint["geometry"]["components"] = []
        design_brief = {
            "component_quota": {"door": {"min": 1, "max": 1}},
            "facade_plan": {"wall_front": {"max_openings": 1}},
        }
        validation = await validate_node({
            "merged_blueprint": blueprint,
            "design_brief": design_brief,
            "merge_diag": {
                "design_errors": ["door 数量 0 少于设计下限 1"],
            },
        })
        action = '''
        [{
          "tool": "add_entity",
          "arguments": {
            "repair_target": "design:door",
            "entity": {
              "id": "door_front_added",
              "type": "door",
              "parentWall": "wall_front",
              "from": [2.5, 0, 0],
              "width": 1.0,
              "height": 2.2
            }
          },
          "reason": "补齐设计配额要求的主入口"
        }]
        '''
        state = {
            **validation,
            "merged_blueprint": blueprint,
            "skeleton_blueprint": blueprint,
            "skeleton_summary": "一面 6m 长墙",
            "design_brief": design_brief,
            "retry_count": 0,
            "max_retries": 3,
            "component_retry_counts": {},
            "thinking_mode": False,
        }

        with (
            patch("app.agent.nodes.callback_node.create_llm", return_value=_FakeLLM(action)),
            patch(
                "app.services.agent_service.agent_service.spec_loader.load_many",
                return_value="",
            ),
        ):
            result = await callback_node(state)

        self.assertTrue(result["repair_audit"]["accepted"])
        self.assertEqual(result["repair_audit"]["after_issue_count"], 0)
        self.assertEqual(result["component_fragments"]["door"][0]["id"], "door_front_added")

    async def test_callback_can_remove_related_opening_for_facade_overage(self):
        blueprint = _state_blueprint()
        design_brief = {
            "component_quota": {},
            "facade_plan": {"wall_front": {"max_openings": 1}},
        }
        validation = await validate_node({
            "merged_blueprint": blueprint,
            "design_brief": design_brief,
            "merge_diag": {
                "design_errors": [
                    "墙 wall_front 有 2 个门窗，超过立面上限 1"
                ],
            },
        })
        skeleton = {
            **blueprint,
            "geometry": {
                "elements": blueprint["geometry"]["elements"],
                "components": [],
            },
        }
        action = '''
        [{
          "tool": "remove_entity",
          "arguments": {"entity_id": "window_front"},
          "reason": "删除立面上明确超额且与门重叠的窗"
        }]
        '''
        state = {
            **validation,
            "merged_blueprint": blueprint,
            "skeleton_blueprint": skeleton,
            "skeleton_summary": "一面 6m 长墙",
            "design_brief": design_brief,
            "door_fragments": [blueprint["geometry"]["components"][0]],
            "window_fragments": [blueprint["geometry"]["components"][1]],
            "retry_count": 0,
            "max_retries": 3,
            "component_retry_counts": {},
            "thinking_mode": False,
        }

        with (
            patch("app.agent.nodes.callback_node.create_llm", return_value=_FakeLLM(action)),
            patch(
                "app.services.agent_service.agent_service.spec_loader.load_many",
                return_value="",
            ),
        ):
            result = await callback_node(state)

        self.assertTrue(result["repair_audit"]["accepted"])
        self.assertEqual(result["repair_audit"]["after_issue_count"], 0)
        self.assertEqual(result["component_fragments"]["window"], [])
        self.assertNotIn("door_fragments", result)
        self.assertEqual(state["door_fragments"][0]["id"], "door_front")
        self.assertEqual(len(state["window_fragments"]), 1)


if __name__ == "__main__":
    unittest.main()
