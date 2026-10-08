"""材质角色名白名单：`ResolvedMaterialPlan` 必须同时容纳建筑与物件两支角色表。

为什么值得单独立一个测试文件：`resolved_plan` 会被写进
`DesignDocument.decisions.materials`，而 `decisions` 是**带标签联合**——同一份
`ResolvedMaterialPlan` 模型同时承载两套角色表：

- 建筑：`facade_primary / structure / floor / frame / door / glass / roof / ground / accent`
  （`material.plan.ROLE_SPECS`）
- 物件：`wood / metal / glass / stone / fabric / accent`
  （`material.plan.OBJECT_ROLE_SPECS`，物件侧没有 `frame`，用 `metal`）

2026-09-23 实测缺陷：角色字面量只写了建筑侧，物件材质方案走到
`resolver.attach_material_plan()` 的 `DesignDocument.model_validate()` 时
**直接 ValidationError（wood/metal/stone/fabric 四项全不认）**，真模型跑
`生成一个桌子` 就断在 `material_plan` 节点——而测试全绿，因为端到端测试把
`material_planner` 整个替换成了桩件，这一步根本没执行。
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest
from typing import get_args

from pydantic import ValidationError

from app.agent.generation.material.plan import OBJECT_ROLE_SPECS, ROLE_SPECS, resolve_material_plan
from app.agent.generation.objects import normalize_object_plan
from app.design.contracts import (
    ArchitectureMaterialRoleName,
    DesignDocument,
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
        # `material/workflow.py` 传进来的就是 `state["design_document"]`（dict）。
        material_plan = resolve_material_plan(None, [], self.plan, "")
        updated = attach_material_plan(self.document.model_dump(mode="json"), material_plan)
        self.assertEqual(updated.decisions.kind, "object")


def _instance_plan(material_role: str) -> dict:
    """基线 trace 的建筑方案 + 一条带材质表态的构件实例。"""

    fixture = Path(__file__).parents[1] / "fixtures" / "design_trace_baseline.json"
    plan = json.loads(fixture.read_text(encoding="utf-8"))["normalized_plan"]
    plan["components"] = [{
        "type": "window",
        "host": "left_wing_L1_left",
        "size": {"width": 1.25, "height": 1.4},
        "form": {"frameWidth": 0.11},
        "material_role": material_role,
    }]
    return plan


class InstanceMaterialRoleTest(unittest.TestCase):
    """实例上的 `material_role` 必须能被材质节点接住 —— 这是那条链的收口点。

    2026-10-08 实测缺陷：玻璃幕墙场景模型给构件实例写 `material_role: "metal"`
    （**材质名**），`DesignDocument` 的引用完整性校验直接 raise，而
    `material/workflow.py` 调 `attach_material_plan` 时**没有 try/except**
    ⇒ 整轮生成终止在材质节点。两件事都错了：

    - 词表没给模型（`design_blocks` 的 components 契约只写了字段名，KB 里唯一的
      "材质角色"表列的是材质名：玻璃/金属/木材/石材/瓦）⇒ 它只能借名字；
    - 校验器比编译器还严：`compile._material_name_for_role` 本来就同时认
      角色名与蓝图材质名（`metal` → 同一个金属材质），这里却只认角色名。
    """

    REQUEST = "生成一栋玻璃幕墙的别墅"

    def _attach(self, material_role: str) -> tuple[DesignDocument, list[str]]:
        plan = _instance_plan(material_role)
        document = build_design_document(plan, session_id="role_repair", source_request=self.REQUEST)
        material_plan = resolve_material_plan(None, [], plan, self.REQUEST)
        repairs: list[str] = []
        updated = attach_material_plan(document, material_plan, role_repairs=repairs)
        return updated, repairs

    def test_material_name_is_normalized_to_its_role(self):
        # `metal` 是建筑侧 `frame` 的 materialId：同一个材质，不该让整轮生成失败。
        updated, repairs = self._attach("metal")

        self.assertEqual(updated.decisions.components[0].material_role, "frame")
        self.assertTrue(repairs, "归一必须记账，否则'模型写错词表'这件事永远查不出来")

    def test_role_the_plan_cannot_cover_is_downgraded_not_fatal(self):
        # `stone` 在建筑角色表里没有自己的材质（物件侧才有）：降级为"没表态"，
        # 编译器按派生模板的默认材质走 —— 与"能力缺失只标记、不阻断"同一口径。
        updated, repairs = self._attach("stone")

        self.assertIsNone(updated.decisions.components[0].material_role)
        self.assertTrue(any("stone" in item for item in repairs))

    def test_correct_role_is_left_untouched(self):
        updated, repairs = self._attach("glass")

        self.assertEqual(updated.decisions.components[0].material_role, "glass")
        self.assertEqual(repairs, [])

    def test_document_validator_keeps_its_teeth(self):
        # 放宽到"编译器认得的两类写法"，不是关掉校验：名字背后真的没有材质时照旧拒绝。
        # 这里绕过 attach（正常链路上归一已经先把它降级了）。
        plan = _instance_plan("stone")
        document = build_design_document(plan, session_id="role_strict", source_request=self.REQUEST)
        data = document.model_dump(mode="json")
        data["decisions"]["materials"] = {
            "keywords": [],
            "resolved_plan": resolve_material_plan(None, [], plan, self.REQUEST),
        }

        with self.assertRaises(ValidationError):
            DesignDocument.model_validate(data)

    def test_plan_material_id_passes_the_document_validator(self):
        plan = _instance_plan("metal")
        document = build_design_document(plan, session_id="role_materialid", source_request=self.REQUEST)
        data = document.model_dump(mode="json")
        data["decisions"]["materials"] = {
            "keywords": [],
            "resolved_plan": resolve_material_plan(None, [], plan, self.REQUEST),
        }

        validated = DesignDocument.model_validate(data)

        self.assertEqual(validated.decisions.components[0].material_role, "metal")


class DesignBlockRoleVocabularyTest(unittest.TestCase):
    """图纸提示词必须给出角色词表，且词表来自**唯一来源**（角色表本身）。"""

    def test_component_block_contract_renders_the_role_table(self):
        from app.agent.generation.architecture.design_blocks import BLOCK_BY_NAME
        from app.agent.generation.architecture.design_workflow import render_block_contract

        text = render_block_contract(BLOCK_BY_NAME["components"])

        self.assertNotIn("{material_roles}", text, "占位符没被渲染，模型看到的是花括号")
        missing = [role for role in ROLE_SPECS if role not in text]
        self.assertEqual(missing, [], f"角色表里的这些成员没进提示词：{missing}")

    def test_contracts_without_placeholders_are_returned_verbatim(self):
        from app.agent.generation.architecture.design_blocks import BLOCK_BY_NAME
        from app.agent.generation.architecture.design_workflow import render_block_contract

        # 挑一个契约里确实没有占位符的块：渲染函数对它是恒等变换。
        block = BLOCK_BY_NAME["structure"]

        self.assertEqual(render_block_contract(block), block.contract)


if __name__ == "__main__":
    unittest.main()