import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.agent_service import (
    AgentService,
    _build_scene_summary,
    _extract_response_artifacts,
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


class _FakeAgent:
    def __init__(self, message):
        self.message = message

    async def ainvoke(self, _payload, config=None):
        return {"messages": [self.message]}


class _FakeLLM:
    def __init__(self, message):
        self.message = message
        self.calls = 0

    async def ainvoke(self, _messages):
        self.calls += 1
        return self.message


def _service(first_message, recovery_message=None) -> AgentService:
    service = AgentService.__new__(AgentService)
    service._build_rag_queries = lambda *_args, **_kwargs: []
    service._agent_for_query = lambda *_args, **_kwargs: _FakeAgent(first_message)
    service.llm = _FakeLLM(
        recovery_message or SimpleNamespace(
            content="",
            additional_kwargs={},
            response_metadata={},
        )
    )
    return service


class ScenePatchGenerationTest(unittest.IsolatedAsyncioTestCase):
    async def test_text_intent_rejects_model_generated_blueprint(self):
        message = SimpleNamespace(
            content='''{
              "meta":{"version":"1.1","type":"building","name":"wrong"},
              "geometry":{"elements":[],"components":[]},
              "materials":{}
            }''',
            additional_kwargs={},
            response_metadata={},
        )
        service = _service(message)

        result = await service.query_structured(
            "你生成建筑的实现思路是什么",
            expected_output="text",
        )

        self.assertIsNone(result.blueprint)
        self.assertIn("text 意图收到不匹配的完整 Blueprint", result.error)

    async def test_blueprint_intent_rejects_plain_text_answer(self):
        message = SimpleNamespace(
            content="我可以先介绍一下建筑的设计方法。",
            additional_kwargs={},
            response_metadata={},
        )
        service = _service(message)

        result = await service.query_structured(
            "生成一座玻璃幕墙商业综合体",
            expected_output="blueprint",
        )

        self.assertIsNone(result.blueprint)
        self.assertEqual(result.error, "生成意图未返回可解析的完整 Blueprint")

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
            result = await service.query_structured(
                "把前墙加厚",
                _blueprint(),
                expected_output="patch",
            )

        self.assertIsNone(result.error)
        self.assertEqual(result.patch["operations"][0]["op"], "update_element")
        self.assertEqual(result.structured_source, "content")
        self.assertFalse(result.structured_recovery_used)
        self.assertEqual(service.llm.calls, 0)

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
            result = await service.query_structured(
                "调整前墙",
                _blueprint(),
                expected_output="patch",
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
            result = await service.query_structured(
                "调整墙厚",
                _blueprint(),
                expected_output="patch",
            )

        self.assertIsNone(result.error)
        self.assertEqual(result.patch["summary"], "调整墙厚")
        self.assertEqual(result.structured_source, "recovery_content")
        self.assertTrue(result.structured_recovery_used)
        self.assertEqual(service.llm.calls, 1)

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
            result = await service.query_structured(
                "在建筑旁边新增一面独立墙，不修改原建筑",
                current,
                expected_output="patch",
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
            result = await service.query_structured(
                "新增家具木材",
                _blueprint(),
                expected_output="patch",
            )

        self.assertIsNone(result.error)
        self.assertEqual(result.patch["operations"][0]["op"], "upsert_material")
        self.assertEqual(result.patch["operations"][0]["name"], "wood_new")

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

        blueprint, scene_patch, source = _extract_response_artifacts(
            content,
            reasoning,
            prefer_patch=True,
        )

        self.assertIsNone(blueprint)
        self.assertIsNotNone(scene_patch)
        self.assertEqual(source, "reasoning")


if __name__ == "__main__":
    unittest.main()
