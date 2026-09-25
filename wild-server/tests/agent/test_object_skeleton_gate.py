"""物件骨架必须能通过骨架节点的预检——它的 `geometry.elements` **本来就是空的**。

物件场景的几何全部由 `plan` 派发的 `generate` 条目产出，骨架节点给的是一个空容器。
所以"`elements` 与 `components` 不能同时为空"这条**交付口径**的规则不能用在物件骨架上，
否则一张合法的桌子会被当场判成 `status=failed`。

2026-09-23 实测缺陷：真模型跑 `生成一个桌子` 走到 `skeleton` 节点时
`schema_issues = ['geometry.elements 和 geometry.components 不能同时为空']`，
整轮 `status=failed`。801 个测试全绿也照样漏——`tests/agent/test_plan_chain_e2e.py`
把 `skeleton_generator` 也桩掉了，这个预检从来没在物件场景下执行过。
同一文件里复杂度评估**早已**按同一理由跳过物件场景（`not object_scene`），
预检漏了那一句。
"""

from __future__ import annotations

import unittest

from app.agent.generation.material_plan import material_role_specs, resolve_material_plan
from app.agent.generation.objects import normalize_object_plan
from app.agent.generation.skeleton_workflow import skeleton_generator
from app.design.resolver import architecture_plan_from_document, build_design_document
from app.utils.blueprint_parser import validate_blueprint_schema

_MESSAGE = "生成一个桌子"

_EMPTY_BLUEPRINT = {
    "meta": {"version": "1.1", "type": "asset", "name": "空骨架"},
    "geometry": {"elements": [], "components": []},
}


def _object_state() -> dict:
    plan = normalize_object_plan(None, _MESSAGE)
    document = build_design_document(
        plan,
        session_id="test_object_skeleton_gate",
        source_request=_MESSAGE,
    )
    architecture_plan = architecture_plan_from_document(document)
    return {
        "user_message": _MESSAGE,
        "architecture_plan": architecture_plan,
        "design_document": document.model_dump(mode="json"),
        "material_plan": resolve_material_plan(None, [], architecture_plan, _MESSAGE),
        "thinking_mode": False,
    }


class EmptyGeometryRuleTest(unittest.TestCase):
    """交付口径不变：空蓝图仍然不合法。"""

    def test_default_validation_rejects_an_empty_blueprint(self):
        issues = validate_blueprint_schema(_EMPTY_BLUEPRINT)
        self.assertIn("geometry.elements 和 geometry.components 不能同时为空", issues)

    def test_opt_in_switches_that_rule_off_only(self):
        issues = validate_blueprint_schema(_EMPTY_BLUEPRINT, allow_empty_geometry=True)
        self.assertEqual(issues, [], "只应放过'同时为空'，其余结构问题照报")

    def test_opt_in_does_not_hide_other_structural_problems(self):
        broken = {
            "meta": {"version": "1.1", "type": "asset", "name": "坏蓝图"},
            "geometry": {
                "elements": [{"id": "a", "type": "furniture"}, {"id": "a", "type": "furniture"}],
                "components": [],
            },
        }
        issues = validate_blueprint_schema(broken, allow_empty_geometry=True)
        self.assertTrue(any("重复的构件 ID" in issue for issue in issues), issues)


class ObjectSkeletonPrecheckTest(unittest.IsolatedAsyncioTestCase):
    async def test_object_skeleton_is_not_rejected_for_being_empty(self):
        result = await skeleton_generator(_object_state())

        self.assertNotEqual(result.get("status"), "failed", result.get("error"))
        blueprint = result.get("skeleton_blueprint") or {}
        self.assertEqual(blueprint.get("geometry", {}).get("elements"), [])
        self.assertEqual(blueprint.get("meta", {}).get("type"), "asset")
        # 成功路径不写 `schema_issues`（只有失败分支才带），所以判"没有卡住"而不是"等于空列表"。
        self.assertFalse(result.get("skeleton_diag", {}).get("schema_issues"))

    async def test_object_design_brief_is_still_produced(self):
        # 空骨架不等于"没有清单"：家具数量靠 component_quota 表达。
        result = await skeleton_generator(_object_state())
        quota = (result.get("design_brief") or {}).get("component_quota") or {}
        self.assertIn("furniture", quota)

    async def test_architecture_scene_still_holds_the_strict_rule(self):
        # 对照：建筑方案的对象场景判据必须是 `is_object_plan`，不能顺手放宽全部。
        from app.design.resolver import is_object_plan

        state = _object_state()
        self.assertTrue(is_object_plan(state["architecture_plan"]))
        self.assertFalse(is_object_plan({"target_kind": "architecture"}))
        # 建筑角色表与物件角色表必须分得开，否则上面的 object_scene 也就没意义了。
        self.assertIsNot(material_role_specs({"target_kind": "architecture"}),
                         material_role_specs(state["architecture_plan"]))


if __name__ == "__main__":
    unittest.main()
