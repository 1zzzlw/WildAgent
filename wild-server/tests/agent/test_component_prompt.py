"""实际构建组件提示词，覆盖生成前的代码路径；不依赖模型或网络。"""
import unittest

from app.agent.generation.components import COMPONENT_REGISTRY
from app.agent.prompts import build_component_prompt


class ComponentPromptTest(unittest.TestCase):
    def test_every_registered_component_builds_prompt(self):
        for component_type, config in COMPONENT_REGISTRY.items():
            with self.subTest(component_type=component_type):
                prompt = build_component_prompt("能力规则", component_type, "骨架摘要")
                self.assertIn(f"你是 {config.label} 组件生成专家", prompt)
                self.assertIn(f"只生成 {component_type}", prompt)
                self.assertIn("能力规则", prompt)
                self.assertIn("骨架摘要", prompt)

    def test_labels_do_not_replace_selected_quota_or_extra_rules(self):
        prompt = build_component_prompt(
            "", "balcony", "骨架", extra_rules="沿批准位置生成",
            design_brief={"component_quota": {"balcony": {"min": 2, "max": 2, "note": "两翼各一个"}},
                          "rag_reference": "已选阳台的宿主关系"},
        )
        self.assertIn("阳台总数: 2~2 个", prompt)
        self.assertIn("两翼各一个", prompt)
        self.assertIn("# 阳台 专属规则", prompt)
        self.assertIn("沿批准位置生成", prompt)
        self.assertIn("已选阳台的宿主关系", prompt)

    def test_opening_slots_stay_separate_for_door_and_window(self):
        brief = {"opening_slots": [
            {"type": "door", "wall_id": "door_host", "from": [1, 0, 0], "width": 1, "height": 2},
            {"type": "window", "wall_id": "window_host", "from": [2, 1, 0], "width": 1, "height": 1},
        ]}
        for component_type, own_host, other_host in (
            ("door", "door_host", "window_host"), ("window", "window_host", "door_host"),
        ):
            with self.subTest(component_type=component_type):
                prompt = build_component_prompt("", component_type, "骨架", design_brief=brief)
                self.assertIn(own_host, prompt)
                self.assertNotIn(other_host, prompt)

    def test_unmapped_label_falls_back_to_type_name(self):
        prompt = build_component_prompt("", "custom_type", "骨架")
        self.assertIn("你是 custom_type 组件生成专家", prompt)
        self.assertIn("楼梯 组件生成专家", build_component_prompt("", "stair", "骨架"))

    def test_opening_rules_do_not_reintroduce_fixed_building_templates(self):
        door_prompt = build_component_prompt(
            "", "door", "骨架", extra_rules=COMPONENT_REGISTRY["door"].extra_rules,
        )
        window_prompt = build_component_prompt(
            "", "window", "骨架", extra_rules=COMPONENT_REGISTRY["window"].extra_rules,
        )
        self.assertIn("服从 DesignDocument 解析出的槽位", door_prompt)
        self.assertIn("服从 DesignDocument 解析出的槽位", window_prompt)
        self.assertNotIn("一栋建筑通常只有 1~2 个门", door_prompt)
        self.assertNotIn("每面墙最多 2~3 个窗", window_prompt)

    def test_five_sections_keep_fixed_order(self):
        """五段顺序固定为 A → B → C → D → E（《动态节点设计规划》§4.3）。"""

        prompt = build_component_prompt("规范文本", "window", "骨架摘要")
        anchors = [
            "你是 窗 组件生成专家",   # A 角色定义
            "# 任务切片 · 本条目",     # B 任务切片
            "# 知识 · 字段与约束",     # C 知识
            "# 全局约束 · 程序推导",   # D 全局约束
            "# 输出格式",              # E 输出格式
        ]
        positions = [prompt.index(anchor) for anchor in anchors]
        self.assertEqual(positions, sorted(positions), "五段顺序被调换")

    def test_role_section_is_kind_invariant(self):
        """A 段跨类型共用同一份文本：新增 kind 时不该需要改动它。"""

        def role(kind: str) -> str:
            return build_component_prompt("规范", kind, "骨架").split("# 任务切片")[0]

        self.assertEqual(
            role("door").replace("door", "X").replace("门", "Y"),
            role("railing").replace("railing", "X").replace("栏杆", "Y"),
        )

    def test_output_template_is_kind_invariant_but_host_placeholder_is_data_driven(self):
        """E 段的**模板**跨类型恒定；示例里的宿主字段由注册表数据决定。

        这里刻意不要求 E 段逐字相同：`"parentWall": "wall_front"` 不是格式，
        而是一条宿主关系。给无宿主类型（家具、栏杆、屋顶……）的示例写宿主字段，
        会诱导模型凭空造一个挂不上去的 `parentWall`。
        因此不变量拆成两条——
          1. 模板本身恒定（新增 kind 不用改 E 段代码）；
          2. 宿主字段的出现与否只取决于 `required_fields`，不取决于类型名硬编码。
        """

        def output(kind: str) -> str:
            return "# 输出格式" + build_component_prompt("规范", kind, "骨架").split("# 输出格式", 1)[1]

        def template(text: str) -> str:
            # 去掉 JSON 示例行后，剩下的就是常量模板。
            return "\n".join(
                line for line in text.splitlines() if not line.startswith("[{")
            )

        self.assertEqual(template(output("door")), template(output("furniture")))

        # 宿主字段随注册表走：有 parentWall 的类型才在示例里出现它。
        for kind, config in COMPONENT_REGISTRY.items():
            with self.subTest(component_type=kind):
                example = output(kind)
                if "parentWall" in config.required_fields:
                    self.assertIn('"parentWall"', example)
                else:
                    self.assertNotIn(
                        "parentWall",
                        example,
                        f"{kind} 没有宿主，示例里不该出现 parentWall",
                    )

    def test_slots_are_sliced_for_every_kind_not_only_openings(self):
        """槽位切片对所有 kind 生效，不再只给门窗（§4.3 硬规定 3 的推广）。"""

        brief = {"opening_slots": [
            {"type": "door", "wall_id": "door_host", "from": [1, 0, 0], "width": 1, "height": 2},
            {"type": "balcony", "wall_id": "balcony_host", "from": [2, 1, 0], "width": 3, "height": 1},
        ]}
        balcony_prompt = build_component_prompt("", "balcony", "骨架", design_brief=brief)
        self.assertIn("balcony_host", balcony_prompt)
        self.assertNotIn("door_host", balcony_prompt)

        roof_prompt = build_component_prompt(
            "",
            "roof",
            "骨架",
            design_brief={
                "opening_slots": brief["opening_slots"],
                "roof_slots": [
                    {"id": "roof:main", "position": [0, 6.4, 0], "span": 8, "depth": 6}
                ],
            },
        )
        self.assertIn("roof:main", roof_prompt)
        self.assertNotIn("door_host", roof_prompt)

    def test_global_constraints_carry_materials_and_detail_level(self):
        """D 段承载程序推导的材质白名单与档位，模型只读。"""

        prompt = build_component_prompt(
            "规范", "window", "骨架",
            material_ids=["wall_brick", "glass_clear"],
            detail_level="detailed",
        )
        self.assertIn("材质 id 白名单", prompt)
        self.assertIn("glass_clear", prompt)
        self.assertIn("detailed", prompt)

    def test_object_specs_are_authoritative_for_host_less_components(self):
        """物件规格进 B 段，且不得夹带立面上限或宿主字段。"""

        brief = {"object_specs": [
            {"kind": "furniture", "subtype": "table", "count": 1,
             "width": 1.8, "depth": 0.9, "height": 0.75, "placement": "居中"},
            {"kind": "furniture", "subtype": "chair", "count": 4,
             "width": 0.45, "depth": 0.5, "height": 0.9, "placement": "沿长边两侧"},
        ]}
        prompt = build_component_prompt("规范", "furniture", "骨架", design_brief=brief)

        self.assertIn("本条目的物件规格", prompt)
        self.assertIn('"width": 1.8', prompt)
        self.assertIn("沿长边两侧", prompt)
        # 家具没有立面也没有宿主：立面上限不能出现；
        # 宿主只能以**否定规则**出现（"不要输出 parentWall"），不能以字段形式出现。
        self.assertNotIn("max_openings", prompt)
        self.assertIn("不要输出 `parentWall`", prompt)
        self.assertNotIn('"parentWall":', prompt)

    def test_object_specs_do_not_leak_into_other_component_types(self):
        """物件规格按 kind 切片，与槽位切片同一原则。"""

        brief = {"object_specs": [
            {"kind": "furniture", "subtype": "table", "count": 1,
             "width": 1.8, "depth": 0.9, "height": 0.75},
        ]}
        door_prompt = build_component_prompt("规范", "door", "骨架", design_brief=brief)

        self.assertNotIn("本条目的物件规格", door_prompt)
        self.assertNotIn("1.8", door_prompt)


if __name__ == "__main__":
    unittest.main()
