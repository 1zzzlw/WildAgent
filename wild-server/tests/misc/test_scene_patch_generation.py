import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.agent_service import (
    AgentService,
    _build_scene_summary,
    _extract_patch_artifact,
    _validate_scene_patch_operations,
)


def _blueprint() -> dict:
    return {
        "meta": {"version": "1.1", "type": "building", "name": "patch-test"},
        "geometry": {
            "elements": [{
                "id": "wall_front",
                "type": "wall",
                "from": [0, 0, 4],
                "to": [6, 3, 4],
                "thickness": 0.2,
            }],
            "components": [],
        },
        "materials": {},
        "behaviors": {},
    }


class _FakeLLM:
    def __init__(self, *messages):
        self.messages = messages
        self.calls = 0

    async def ainvoke(self, _messages):
        response = self.messages[min(self.calls, len(self.messages) - 1)]
        self.calls += 1
        return response


def _service(first_message, recovery_message=None) -> AgentService:
    service = AgentService.__new__(AgentService)
    service.spec_loader = SimpleNamespace(load_many=lambda *_args, **_kwargs: "")
    service.llm = _FakeLLM(first_message, recovery_message or SimpleNamespace(
        content="", additional_kwargs={}, response_metadata={},
    ))
    return service


class ScenePatchGenerationTest(unittest.IsolatedAsyncioTestCase):
    async def test_legal_scene_patch_reaches_patch_branch(self):
        message = SimpleNamespace(
            content='''{
              "operations":[{
                "op":"update_element",
                "id":"wall_front",
                "changes":{"thickness":0.3}
              }],
              "summary":"加厚前墙"
            }''',
            additional_kwargs={},
            response_metadata={},
        )
        service = _service(message)

        with patch(
            "app.services.agent_service.run_validation_pipeline",
            return_value=[],
        ):
            result = await service.query_patch(
                "把前墙加厚",
                _blueprint(),
            )

        self.assertIsNone(result.error)
        self.assertEqual(result.patch["operations"][0]["op"], "update_element")
        self.assertEqual(result.structured_source, "content")
        self.assertFalse(result.structured_recovery_used)
        self.assertEqual(service.llm.calls, 1)

    async def test_patch_can_fall_back_to_reasoning_content(self):
        message = SimpleNamespace(
            content="",
            additional_kwargs={
                "reasoning_content": '''{
                  "operations":[{
                    "op":"update_element",
                    "id":"wall_front",
                    "changes":{"thickness":0.22}
                  }],
                  "summary":"调整前墙"
                }''',
            },
            response_metadata={},
        )
        service = _service(message)

        with patch(
            "app.services.agent_service.run_validation_pipeline",
            return_value=[],
        ):
            result = await service.query_patch(
                "调整前墙",
                _blueprint(),
            )

        self.assertIsNone(result.error)
        self.assertEqual(result.structured_source, "reasoning")
        self.assertFalse(result.structured_recovery_used)

    async def test_missing_patch_gets_one_format_recovery(self):
        first = SimpleNamespace(
            content="我会在建筑旁边增加一个构件。",
            additional_kwargs={},
            response_metadata={},
        )
        recovered = SimpleNamespace(
            content='''{"patch":{
              "operations":[{
                "op":"update_element",
                "id":"wall_front",
                "changes":{"thickness":0.25}
              }],
              "summary":"调整墙厚"
            }}''',
            additional_kwargs={},
            response_metadata={},
        )
        service = _service(first, recovered)

        with patch(
            "app.services.agent_service.run_validation_pipeline",
            return_value=[],
        ):
            result = await service.query_patch(
                "调整墙厚",
                _blueprint(),
            )

        self.assertIsNone(result.error)
        self.assertEqual(result.patch["summary"], "调整墙厚")
        self.assertEqual(result.structured_source, "recovery_content")
        self.assertTrue(result.structured_recovery_used)
        self.assertEqual(service.llm.calls, 2)

    async def test_add_beside_building_does_not_mutate_current_blueprint(self):
        current = _blueprint()
        message = SimpleNamespace(
            content='''{
              "operations":[{
                "op":"add_element",
                "element":{
                  "id":"wall_detached",
                  "type":"wall",
                  "from":[8,0,4],
                  "to":[10,3,4],
                  "thickness":0.2
                }
              }],
              "summary":"在建筑旁边新增独立墙体"
            }''',
            additional_kwargs={},
            response_metadata={},
        )
        service = _service(message)

        with patch(
            "app.services.agent_service.run_validation_pipeline",
            return_value=[],
        ):
            result = await service.query_patch(
                "在建筑旁边新增一面独立墙，不修改原建筑",
                current,
            )

        self.assertIsNone(result.error)
        self.assertEqual(result.patch["operations"][0]["op"], "add_element")
        self.assertEqual(len(current["geometry"]["elements"]), 1)
        self.assertEqual(current["geometry"]["elements"][0]["thickness"], 0.2)

    async def test_add_material_alias_passes_operation_precheck(self):
        message = SimpleNamespace(
            content='''{
              "operations":[{
                "op":"add_material",
                "material_id":"wood_new",
                "material":{"baseColor":[0.4,0.2,0.1]}
              }],
              "summary":"新增家具木材"
            }''',
            additional_kwargs={},
            response_metadata={},
        )
        service = _service(message)

        with patch(
            "app.services.agent_service.run_validation_pipeline",
            return_value=[],
        ):
            result = await service.query_patch(
                "新增家具木材",
                _blueprint(),
            )

        self.assertIsNone(result.error)
        self.assertEqual(result.patch["operations"][0]["op"], "upsert_material")
        self.assertEqual(result.patch["operations"][0]["name"], "wood_new")

    async def test_patch_node_streams_model_reasoning_without_mutating_scene(self):
        from copy import deepcopy
        from app.agent.patch.workflow import patch_node
        from app.agent.runtime import bind_reasoning_callback, reset_reasoning_callback

        current = _blueprint()
        original = deepcopy(current)
        patch_text = '{"operations":[{"op":"update_element","id":"wall_front","changes":{"thickness":0.3}}],"summary":"加厚墙"}'
        service = _service(SimpleNamespace(content="", additional_kwargs={}))

        class StreamingModel:
            async def astream(self, _messages):
                yield SimpleNamespace(content="", additional_kwargs={"reasoning_content": "模型思考"})
                yield SimpleNamespace(content=patch_text, additional_kwargs={})

        service.thinking_llm = StreamingModel()
        deltas = []

        async def emit(node, delta):
            deltas.append((node, delta))

        token = bind_reasoning_callback(emit)
        try:
            with (
                patch("app.services.agent_service.agent_service", service),
                patch("app.services.agent_service.run_validation_pipeline", return_value=[]),
            ):
                result = await patch_node({
                    "user_message": "把前墙加厚", "current_blueprint": current,
                    "thinking_mode": True,
                })
        finally:
            reset_reasoning_callback(token)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["scene_patch"]["operations"][0]["id"], "wall_front")
        self.assertEqual(deltas, [("patch", "模型思考")])
        self.assertEqual(current, original)
        self.assertEqual(service.llm.calls, 0)

    async def test_patch_node_keeps_applicable_edit_and_reports_existing_validation_error(self):
        from app.agent.patch.workflow import patch_node
        from app.services.agent_service import PipelineStepResult

        message = SimpleNamespace(
            content='{"operations":[{"op":"update_element","id":"wall_front","changes":{"thickness":0.3}}],"summary":"加厚墙"}',
            additional_kwargs={}, response_metadata={},
        )
        service = _service(message)
        with (
            patch("app.services.agent_service.agent_service", service),
            patch("app.services.agent_service.run_validation_pipeline", return_value=[
                PipelineStepResult(1, "validate_collision", "❌ overlap", True, False),
            ]),
        ):
            result = await patch_node({
                "user_message": "把前墙加厚", "current_blueprint": _blueprint(),
            })
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["scene_patch"]["operations"][0]["id"], "wall_front")
        self.assertIn("validate_collision", result["scene_patch"]["summary"])
        self.assertIn("overlap", result["scene_patch"]["summary"])
        self.assertFalse(result["patch_diag"]["validation_passed"])

    def test_patch_precheck_rejects_unknown_or_missing_target(self):
        issues = _validate_scene_patch_operations(_blueprint(), {
            "operations": [
                {"op": "move_element", "id": "wall_front"},
                {"op": "update_element", "id": "missing", "changes": {"width": 2}},
            ],
        })

        self.assertEqual(len(issues), 2)
        self.assertIn("不受支持", issues[0])
        self.assertIn("目标不存在", issues[1])

    def test_scene_summary_keeps_full_xyz_coordinates(self):
        summary = _build_scene_summary(_blueprint())

        self.assertIn("from=[0, 0, 4]", summary)
        self.assertIn("to=[6, 3, 4]", summary)


class ScenePatchArtifactSelectionTest(unittest.TestCase):
    def test_patch_in_reasoning_wins_over_blueprint_in_content_for_edit(self):
        content = '''{
          "meta":{"version":"1.1","type":"building","name":"wrong"},
          "geometry":{"elements":[],"components":[]}
        }'''
        reasoning = '''{
          "operations":[{"op":"remove_element","id":"wall_front"}],
          "summary":"删除墙"
        }'''

        scene_patch, source = _extract_patch_artifact(
            content,
            reasoning,
        )

        self.assertIsNotNone(scene_patch)
        self.assertEqual(source, "reasoning")


if __name__ == "__main__":
    unittest.main()
