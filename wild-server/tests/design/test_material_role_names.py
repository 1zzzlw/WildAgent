"""材质角色名白名单：`ResolvedMaterialPlan` 必须同时容纳建筑与物件两支角色表。

为什么值得单独立一个测试文件：`resolved_plan` 会被写进
`DesignDocument.decisions.materials`，而 `decisions` 是**带标签联合**——同一份
`ResolvedMaterialPlan` 模型同时承载两套角色表：

- 建筑：`facade_primary / structure / floor / frame / door / glass / roof / ground / accent`
  （`material_plan.ROLE_SPECS`）
- 物件：`wood / metal / glass / stone / fabric / accent`
  （`material_plan.OBJECT_ROLE_SPECS`，物件侧没有 `frame`，用 `metal`）

2026-09-23 实测缺陷：角色字面量只写了建筑侧，物件材质方案走到
`resolver.attach_material_plan()` 的 `DesignDocument.model_validate()` 时
**直接 ValidationError（wood/metal/stone/fabric 四项全不认）**，真模型跑
`生成一个桌子` 就断在 `material_plan` 节点——而测试全绿，因为端到端测试把
`material_planner` 整个替换成了桩件，这一步根本没执行。
"""

from __future__ import annotations

import unittest
from typing import get_args

from pydantic import ValidationError

from app.agent.generation.material_plan import OBJECT_ROLE_SPECS, ROLE_SPECS, resolve_material_plan
from app.agent.generation.objects import normalize_object_plan
from app.design.contracts import (
    ArchitectureMaterialRoleName,
    MaterialRoleName,
    ObjectMaterialRoleName,
    ResolvedMaterialPlan,
)
from app.design.resolver import attach_material_plan, build_design_document


def _minimal_role(role: str) -> dict:
    return {"role": role, "materialId": f"m_{role}", "material": {"baseColor": [0.5, 0.5, 0.5]}}


class MaterialRoleNameParityTest(unittest.TestCase):
    """字面量与两张角色表逐键比对 —— 防止下次再单边漂移。"""

    def test_role_literal_equals_union_of_both_role_tables(self):
        expected = set(ROLE_SPECS) | set(OBJECT_ROLE_SPECS)
        actual = set(get_args(MaterialRoleName))
        self.assertEqual(
            actual,
            expected,
            "MaterialRoleName 与两张角色表不一致："
            f"字面量多出 {sorted(actual - expected)}；角色表多出 {sorted(expected - actual)}",
        )

    def test_architecture_and_object_aliases_are_the_two_tables(self):
        self.assertEqual(set(get_args(ArchitectureMaterialRoleName)), set(ROLE_SPECS))
        self.assertEqual(set(get_args(ObjectMaterialRoleName)), set(OBJECT_ROLE_SPECS))

    def test_object_roles_are_not_a_subset_of_architecture_roles(self):
        # 这条是"并集而不是复用"的证据：物件侧确实有建筑侧没有的角色名。
        self.assertTrue(set(OBJECT_ROLE_SPECS) - set(ROLE_SPECS))


class ResolvedMaterialPlanRoleTest(unittest.TestCase):
    def test_every_declared_role_validates(self):
        for role in get_args(MaterialRoleName):
            with self.subTest(role=role):
                plan = ResolvedMaterialPlan(roles=[_minimal_role(role)])
                self.assertEqual(plan.roles[0].role, role)

    def test_unknown_role_is_still_rejected(self):
        # 白名单放宽到并集，不是关掉校验。
        with self.assertRaises(ValidationError):
            ResolvedMaterialPlan(roles=[_minimal_role("unobtainium")])


class ObjectMaterialPlanRoundTripTest(unittest.TestCase):
    """物件方案 → 材质方案 → 写回设计文档。这正是 `material_plan` 节点的调用序列。"""

    def setUp(self):
        self.plan = normalize_object_plan(None, "生成一套餐桌椅，餐桌长1.8米")
        self.document = build_design_document(
            self.plan,
            session_id="test_material_role_names",
            source_request="生成一套餐桌椅，餐桌长1.8米",
        )

    def test_object_material_plan_survives_attach_material_plan(self):
        material_plan = resolve_material_plan(None, [], self.plan, "生成一套餐桌椅，餐桌长1.8米")
        self.assertTrue(material_plan["roles"], "物件材质方案不能为空")

        updated = attach_material_plan(self.document, material_plan)

        written = updated.decisions.materials.resolved_plan
        self.assertIsNotNone(written)
        self.assertEqual(
            [item.role for item in written.roles],
            [item["role"] for item in material_plan["roles"]],
        )
        object_roles = {item["role"] for item in material_plan["roles"]}
        self.assertTrue(
            object_roles - set(ROLE_SPECS),
            f"本用例必须覆盖到建筑侧没有的角色名，否则测不出并集问题：{sorted(object_roles)}",
        )

    def test_attach_material_plan_accepts_a_dict_document(self):
        # `material_workflow` 传进来的就是 `state["design_document"]`（dict）。
        material_plan = resolve_material_plan(None, [], self.plan, "")
        updated = attach_material_plan(self.document.model_dump(mode="json"), material_plan)
        self.assertEqual(updated.decisions.kind, "object")


if __name__ == "__main__":
    unittest.main()
