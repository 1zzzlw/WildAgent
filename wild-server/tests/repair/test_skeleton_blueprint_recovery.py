import unittest
import json
from pathlib import Path
from unittest.mock import patch

from app.agent.nodes import skeleton_node
from app.agent.llm_invocation import merge_token_usage


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


class _InvalidMaterialsResponse:
    content = """
    {
      "meta": {"version": "1.1", "type": "building", "name": "错误材质容器"},
      "geometry": {
        "elements": [{
          "id": "wall_bad", "type": "wall",
          "from": [0, 0, 0], "to": [8, 3.2, 0], "thickness": 0.2
        }],
        "components": []
      },
      "materials": []
    }
    """
    response_metadata = {"finish_reason": "stop", "token_usage": {}}


class _InvalidMaterialsLLM:
    async def ainvoke(self, messages):
        return _InvalidMaterialsResponse()


class SkeletonBlueprintRecoveryTest(unittest.IsolatedAsyncioTestCase):
    async def test_zero_length_wall_hosts_are_rebuilt_before_dispatch(self):
        from app.agent.architecture_plan import normalize_architecture_plan
        case = json.loads((Path(__file__).resolve().parents[1] / "fixtures/degenerate_wall_hosts.json").read_text(encoding="utf-8"))
        plan = normalize_architecture_plan(case["architecture_plan"], case["user_message"])
        response = type("Response", (), {"content": json.dumps(case["skeleton_blueprint"]), "response_metadata": {}})()

        class LLM:
            async def ainvoke(self, messages):
                return response

        loader = type("Loader", (), {"last_results": [], "load_many": lambda *_args, **_kwargs: ""})()
        service = type("Service", (), {"spec_loader": loader})()
        with (
            patch.object(skeleton_node, "create_llm", return_value=LLM()),
            patch("app.services.agent_service.agent_service", service),
        ):
            result = await skeleton_node.skeleton_generator({
                "user_message": case["user_message"], "architecture_plan": plan,
                "thinking_mode": False,
            })
        self.assertNotIn("error", result)
        self.assertTrue(result["skeleton_diag"]["deterministic_fallback"])
        self.assertTrue(result["skeleton_diag"]["complexity"]["checks"]["valid_wall_hosts"])
        self.assertGreaterEqual(result["skeleton_diag"]["opening_slot_count"], 15)

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
        merged = merge_token_usage(
            {"input": 10, "output": 20, "total": 30},
            {"input": 5, "output": 7, "total": 12},
        )
        self.assertEqual(merged, {"input": 15, "output": 27, "total": 42})

    def test_skeleton_summary_uses_approved_slots_instead_of_fixed_opening_sizes(self):
        summary = skeleton_node._build_skeleton_summary({
            "geometry": {
                "elements": [{
                    "id": "wall_front",
                    "type": "wall",
                    "from": [0, 0, 0],
                    "to": [8, 3, 0],
                    "thickness": 0.2,
                }],
                "components": [],
            },
            "materials": {},
        }, {
            "opening_slots": [{
                "type": "window",
                "wall_id": "wall_front",
                "from": [1.3, 0.7, 0],
                "width": 2.4,
                "height": 1.9,
            }],
        })

        self.assertIn("优先逐字使用程序解析槽位", summary)
        self.assertNotIn("门宽 0.9~1.2m", summary)
        self.assertNotIn("窗宽 1.0~2.0m", summary)

    async def test_invalid_materials_container_uses_deterministic_skeleton_fallback(self):
        architecture_plan = {
            "concept": "低层住宅",
            "required_components": [],
        }
        fake_loader = type("Loader", (), {"last_results": [], "load_many": lambda *_args, **_kwargs: ""})()
        fake_service = type("Service", (), {"spec_loader": fake_loader})()

        with (
            patch.object(skeleton_node, "create_llm", return_value=_InvalidMaterialsLLM()),
            patch("app.services.agent_service.agent_service", fake_service),
        ):
            result = await skeleton_node.skeleton_generator({
                "user_message": "生成一个别墅",
                "architecture_plan": architecture_plan,
                "material_plan": {"roles": [], "resolvedAssets": {}},
                "thinking_mode": False,
            })

        self.assertNotIn("error", result)
        self.assertIn("skeleton_blueprint", result)
        self.assertEqual(
            result["skeleton_diag"]["deterministic_fallback_reason"],
            "模型骨架未通过 Schema 预检",
        )
        self.assertIsInstance(result["skeleton_blueprint"]["materials"], dict)


if __name__ == "__main__":
    unittest.main()
