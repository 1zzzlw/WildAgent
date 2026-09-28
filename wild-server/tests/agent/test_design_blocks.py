"""设计期"逐块起草"（§1.6）的单元测试。

这个文件盯三件事，缺一件就等于没测：

1. **块表是常量且自洽**：依赖序、档位闭集、字段→块唯一映射。
   字段归属重复会让两个块都写同一个字段 → 必然分叉。
2. **块契约只拦"能精确定义"的**：`facade` 的 pattern 长度；`components` 的配额是否非空。
   🔴 特别钉住一条**反面教训**：不许拿"下游一定会覆盖的值"当门禁 ——
   `door`/`window` 的上下限由归一化按立面 pattern 派生，曾用"必须完全相等"去判，
   真模型连错 3 次导致**整块被丢弃**（连累 railing/canopy 等真正会被用的配额）。
3. **执行器语义**：逐块落定、带证据重试、**失败不阻断**（用户红线）、
   **模型服务故障必须上抛**（否则会被当成"这一块写不出来"静默吞掉）。

`_BLOCK_MAX_ATTEMPTS` 是**有界**的：坏图上无界重试会烧光预算，所以"三次就放弃"要钉住。
"""

import asyncio
import contextlib
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.agent.generation.architecture import design_blocks
from app.agent.generation.architecture.design_blocks import (
    BLOCK_BY_NAME,
    DESIGN_BLOCKS,
    DesignBlock,
    block_of_field,
    blocks_for_level,
    ordered_blocks,
)
from app.agent.generation.architecture.design_workflow import (
    _BLOCK_MAX_ATTEMPTS,
    _pick_block_fields,
    build_block_prompt,
    check_block_contract,
    draft_design_blocks,
)

#: 四面都用同一份"3 开间、1 门 5 窗"的立面：door=4、window=20。
_FACE = {
    "bays": 3,
    "ground_pattern": ["door", "window", "window"],
    "upper_pattern": ["window", "window", "window"],
}

_FULL_PAYLOAD = {
    "massing": {"floors": 2},
    "volumes": [
        {
            "id": "v1",
            "role": "primary",
            "x": 0,
            "z": 0,
            "width": 12,
            "depth": 10,
            "start_floor": 1,
            "end_floor": 2,
        }
    ],
    "structural_grid": {"x": [4, 4, 4], "z": [5, 5]},
    "circulation": {"kind": "stair"},
    "facades": {face: dict(_FACE) for face in ("front", "back", "left", "right")},
    "roof": {"type": "gable"},
    # 🔴 必须带一个**非派生**类型的配额：door/window/roof 由系统派生，只写它们会被判
    # "这一块什么都没贡献"（见 check_block_contract 里的反面教训）。
    "component_quota": {
        "door": {"min": 4, "max": 4},
        "window": {"min": 20, "max": 20},
        "railing": {"min": 2, "max": 2},
    },
}


def _json(payload) -> str:
    return json.dumps(payload, ensure_ascii=False)


class BlockTableTest(unittest.TestCase):
    def test_every_field_belongs_to_exactly_one_block(self):
        owner: dict[str, str] = {}
        for block in DESIGN_BLOCKS:
            for field in block.fields:
                self.assertNotIn(
                    field, owner, f"{field} 同时属于 {owner.get(field)} 与 {block.name}"
                )
                owner[field] = block.name

    def test_block_of_field_round_trips_and_rejects_system_fields(self):
        for block in DESIGN_BLOCKS:
            for field in block.fields:
                self.assertIs(block_of_field(field), block)
        # complexity 由档位解析给出，不属于任何块 —— 认不出必须返回 None，不许猜。
        self.assertIsNone(block_of_field("complexity"))
        self.assertIsNone(block_of_field("profile"))

    def test_declared_dependencies_exist_in_the_table(self):
        names = {block.name for block in DESIGN_BLOCKS}
        for block in DESIGN_BLOCKS:
            for dep in block.depends_on:
                self.assertIn(dep, names, f"{block.name} 依赖了不存在的块 {dep}")

    def test_ordered_blocks_is_a_topological_order_for_every_level(self):
        all_names = {block.name for block in DESIGN_BLOCKS}
        for level in ("minimal", "simple", "standard", "detailed", "没见过的档位"):
            order = [block.name for block in ordered_blocks(level)]
            self.assertEqual(len(order), len(set(order)), f"{level}: 有块被排了两次")
            index = {name: i for i, name in enumerate(order)}
            for block in DESIGN_BLOCKS:
                if block.name not in index:
                    continue
                for dep in block.depends_on:
                    if dep in index:
                        self.assertLess(
                            index[dep], index[block.name], f"{level}: {dep} 必须排在 {block.name} 前"
                        )
            # 档位只决定"用哪几块"，不许出现表外的块。
            self.assertLessEqual(set(order), all_names)

    def test_standard_level_starts_with_massing_and_ends_with_components(self):
        order = [block.name for block in ordered_blocks("standard")]
        self.assertEqual(order[0], "massing")
        self.assertEqual(order[-1], "components")

    def test_levels_are_monotonic_and_unknown_falls_back_to_standard(self):
        minimal = set(blocks_for_level("minimal"))
        simple = set(blocks_for_level("simple"))
        standard = set(blocks_for_level("standard"))
        self.assertTrue(minimal < simple, "simple 必须严格包含 minimal 之外的内容")
        self.assertLessEqual(simple, standard)
        # 认不出按 standard：**宁可多写不可少写**（少写会制造 "没人表态" 的 defaulted）。
        self.assertEqual(blocks_for_level("这档位不存在"), blocks_for_level("standard"))
        self.assertEqual(blocks_for_level(None), blocks_for_level("standard"))
        self.assertEqual(blocks_for_level(""), blocks_for_level("standard"))

    def test_ordered_blocks_raises_on_a_cycle_instead_of_returning_a_partial_order(self):
        # 负例：表是常量，有环属于写错，必须炸而不是静默吐一个残缺顺序。
        cyclic = (
            DesignBlock(name="a", fields=("f1",), depends_on=("b",), parallel_group=None, contract=""),
            DesignBlock(name="b", fields=("f2",), depends_on=("a",), parallel_group=None, contract=""),
        )
        with patch.object(design_blocks, "DESIGN_BLOCKS", cyclic), patch.object(
            design_blocks, "_BLOCKS_BY_LEVEL", {"standard": ("a", "b")}
        ):
            with self.assertRaises(ValueError):
                ordered_blocks("standard")


class BlockContractTest(unittest.TestCase):
    def test_missing_required_field_is_named_in_the_evidence(self):
        issue = check_block_contract(BLOCK_BY_NAME["massing"], {"massing": {"floors": 2}}, {})
        self.assertIn("volumes", issue)

    def test_complete_block_passes(self):
        picked = {"massing": {"floors": 2}, "volumes": [{"id": "v1"}]}
        self.assertEqual(check_block_contract(BLOCK_BY_NAME["massing"], picked, {}), "")

    def test_facade_pattern_length_must_equal_bays(self):
        block = BLOCK_BY_NAME["facade"]
        good = {"facades": {"front": dict(_FACE)}}
        self.assertEqual(check_block_contract(block, good, {}), "")

        bad = {"facades": {"front": {"bays": 3, "ground_pattern": ["door"], "upper_pattern": ["window"] * 3}}}
        self.assertIn("不一致", check_block_contract(block, bad, {}))

    def test_facade_rejects_bays_that_are_not_a_positive_integer(self):
        block = BLOCK_BY_NAME["facade"]
        for bays in (0, -1, True, "3", None):
            spec = {"bays": bays, "ground_pattern": [], "upper_pattern": []}
            self.assertNotEqual(
                check_block_contract(block, {"facades": {"front": spec}}, {}), "", bays
            )

    def test_facade_rejects_empty_facades(self):
        block = BLOCK_BY_NAME["facade"]
        self.assertNotEqual(check_block_contract(block, {"facades": {}}, {}), "")

    def test_components_quota_must_not_be_empty(self):
        block = BLOCK_BY_NAME["components"]
        for quota in ({}, [], None, "x"):
            self.assertNotEqual(
                check_block_contract(block, {"component_quota": quota}, {}), "", repr(quota)
            )

    def test_components_quota_of_only_derived_kinds_is_rejected(self):
        """door/window/roof 由系统派生 —— 只写它们等于这一块什么都没贡献。"""

        block = BLOCK_BY_NAME["components"]
        only_derived = {
            "component_quota": {
                "door": {"min": 4, "max": 4},
                "window": {"min": 20, "max": 20},
                "roof": {"min": 1, "max": 1},
            }
        }
        issue = check_block_contract(block, only_derived, {})
        self.assertIn("door/window/roof", issue)

    def test_components_quota_numbers_of_derived_kinds_are_not_checked(self):
        """🔴 反面教训：door/window 的**数值**不许再当门禁。

        2026-09-28 真模型实测：这条检查让模型连错 3 次 ⇒ **整块 `components` 被判未定稿丢弃**，
        连带丢掉 railing / canopy / cornice 这些真正会被用的配额，还白烧 ~90s。
        归一化本来就会按立面 pattern 覆盖这三类的值。
        """

        block = BLOCK_BY_NAME["components"]
        wildly_wrong = {
            "component_quota": {
                "door": {"min": 999, "max": 999},
                "window": {"min": 0, "max": 0},
                "railing": {"min": 2, "max": 2},
            }
        }
        self.assertEqual(check_block_contract(block, wildly_wrong, {}), "")

    def test_components_quota_is_accepted_without_facades_settled(self):
        """配额是否合格**不依赖** facades 是否定稿（派生值不参与判定）。"""

        block = BLOCK_BY_NAME["components"]
        picked = {"component_quota": {"railing": {"min": 2, "max": 2}}}
        self.assertEqual(check_block_contract(block, picked, {}), "")
        self.assertEqual(
            check_block_contract(block, picked, {"facades": {face: dict(_FACE) for face in _FACE}}), ""
        )

    def test_pick_block_fields_drops_foreign_fields(self):
        picked = _pick_block_fields(
            {"roof": {"type": "gable"}, "massing": {"floors": 9}}, BLOCK_BY_NAME["roof"]
        )
        self.assertEqual(picked, {"roof": {"type": "gable"}})
        self.assertEqual(_pick_block_fields("不是对象", BLOCK_BY_NAME["roof"]), {})
        self.assertEqual(_pick_block_fields(None, BLOCK_BY_NAME["roof"]), {})

    def test_block_prompt_appends_instead_of_rewriting_the_base(self):
        first = build_block_prompt("BASE", BLOCK_BY_NAME["massing"], {})
        self.assertTrue(first.startswith("BASE"), "基础提示词必须原样保留在最前")
        self.assertIn("这是第一块", first)

        later = build_block_prompt("BASE", BLOCK_BY_NAME["facade"], {"massing": {"floors": 2}})
        self.assertTrue(later.startswith("BASE"))
        self.assertIn("已定稿的前序块", later)
        self.assertIn('"floors": 2', later)
        self.assertIn("本轮只写一个设计块", later)


class DraftExecutorTest(unittest.TestCase):
    """执行器：逐块落定 / 带证据重试 / 失败不阻断 / 模型故障上抛。

    🔴 **默认通道是工具循环**（`app.agent.plan.tool_loop.run_tool_loop`，§2.7 的试算工具挂在它上面），
    所以桩件默认打在它那儿；`probe=False` 时改成打在 `invoke_llm` 上，
    专门覆盖"流式/显式关闭试算"的那条通道。**两条通道都要有覆盖**——
    只钉一条，另一条改了没人知道。
    """

    def _run(self, payloads, *, level="standard", error=None, thinking_mode=False, probe=True):
        calls: list[str] = []
        queue = list(payloads)

        def _next() -> str:
            return queue.pop(0) if queue else "这不是 JSON"

        async def fake_run_tool_loop(*, system_prompt, **_kwargs):
            calls.append(system_prompt)
            if error is not None:
                # 工具循环**吞掉**模型异常并记进 diag（那是给 plan 条目用的语义）；
                # 设计块路径必须把它翻回异常 —— 否则"服务坏了"会被当成"模型不会写"。
                return SimpleNamespace(text="", trace=[], diag={"error": str(error)})
            return SimpleNamespace(
                text=_next(),
                trace=[],
                diag={"token_usage": {"input": 1, "output": 1, "total": 2}},
            )

        async def fake_invoke(_llm, messages):
            calls.append(messages[0]["content"])
            if error is not None:
                raise error
            return SimpleNamespace(
                content=_next(), token_usage={"input": 1, "output": 1, "total": 2}
            )

        patches = (
            [patch("app.agent.plan.tool_loop.run_tool_loop", fake_run_tool_loop)]
            if probe
            else [
                patch(
                    "app.agent.generation.architecture.design_workflow.create_llm",
                    lambda **_kwargs: object(),
                ),
                patch(
                    "app.agent.generation.architecture.design_workflow.invoke_llm", fake_invoke
                ),
            ]
        )
        with contextlib.ExitStack() as stack:
            for item in patches:
                stack.enter_context(item)
            draft, diag = asyncio.run(
                draft_design_blocks(
                    base_prompt="BASE",
                    user_request="生成一个两层别墅",
                    level=level,
                    thinking_mode=thinking_mode,
                    allow_probe=probe,
                )
            )
        return draft, diag, calls

    def test_all_blocks_settle_on_the_first_try(self):
        draft, diag, calls = self._run([_json(_FULL_PAYLOAD)] * len(DESIGN_BLOCKS))

        self.assertEqual(diag["unsettled_blocks"], [])
        self.assertEqual(set(draft), {f for b in DESIGN_BLOCKS for f in b.fields})
        self.assertEqual([item["attempts"] for item in diag["blocks"]], [1] * len(DESIGN_BLOCKS))
        self.assertEqual(len(calls), len(DESIGN_BLOCKS))
        self.assertEqual(diag["token_usage"]["total"], 2 * len(DESIGN_BLOCKS))

    def test_a_block_that_never_settles_does_not_block_the_rest(self):
        """用户红线：某块写不出来就**留空**交下游兜底，不许掐掉整轮生成。"""

        draft, diag, calls = self._run([])

        self.assertEqual(draft, {})
        self.assertEqual(diag["unsettled_blocks"], [b.name for b in DESIGN_BLOCKS])
        # 有界：每块恰好试满上限就放弃。
        self.assertEqual(set(item["attempts"] for item in diag["blocks"]), {_BLOCK_MAX_ATTEMPTS})
        self.assertEqual(len(calls), _BLOCK_MAX_ATTEMPTS * len(DESIGN_BLOCKS))

    def test_retry_carries_the_evidence_back_to_the_model(self):
        # minimal 档只有 massing + facade；massing 第一次缺 volumes，第二次补齐。
        bad_massing = _json({"massing": {"floors": 2}})
        draft, diag, calls = self._run([bad_massing, _json(_FULL_PAYLOAD), _json(_FULL_PAYLOAD)], level="minimal")

        self.assertIn("massing", draft)
        self.assertEqual(diag["unsettled_blocks"], [])
        self.assertIn("上一次输出未通过", calls[1])
        self.assertIn("volumes", calls[1])
        self.assertEqual(diag["blocks"][0]["attempts"], 2)
        self.assertEqual(diag["blocks"][1]["attempts"], 1)

    def test_unsettled_block_records_its_last_issue(self):
        draft, diag, _ = self._run([], level="minimal")
        self.assertEqual(draft, {})
        for item in diag["blocks"]:
            self.assertFalse(item["settled"])
            self.assertTrue(item["last_issue"])

    def test_settled_block_does_not_keep_a_stale_issue(self):
        _, diag, _ = self._run([_json(_FULL_PAYLOAD)] * len(DESIGN_BLOCKS), level="minimal")
        for item in diag["blocks"]:
            self.assertTrue(item["settled"])
            self.assertEqual(item["last_issue"], "")

    def test_model_failure_propagates_instead_of_being_swallowed(self):
        """模型服务故障必须上抛：调用方要拿它走 `model_failure_result` 终止本轮。"""

        with self.assertRaises(RuntimeError):
            self._run([_json(_FULL_PAYLOAD)], error=RuntimeError("quota exhausted"))

    def test_only_the_selected_levels_blocks_are_drafted(self):
        _, diag, calls = self._run([_json(_FULL_PAYLOAD)] * 2, level="minimal")
        self.assertEqual([item["block"] for item in diag["blocks"]], ["massing", "facade"])
        self.assertEqual(len(calls), 2)

    def test_diag_records_the_level_it_used(self):
        _, diag, _ = self._run([_json(_FULL_PAYLOAD)] * 2, level="minimal")
        self.assertEqual(diag["level"], "minimal")

    # ── 两条通道都要覆盖：默认（工具循环）与非默认（纯 invoke）──

    def test_plain_channel_also_settles_and_reports_probe_off(self):
        """显式关掉试算时退回纯 invoke 通道；语义必须与默认通道一致。"""

        draft, diag, calls = self._run(
            [_json(_FULL_PAYLOAD)] * 2, level="minimal", probe=False
        )

        self.assertEqual(diag["unsettled_blocks"], [])
        self.assertEqual(set(draft), {"massing", "volumes", "facades"})
        self.assertEqual(len(calls), 2)
        self.assertFalse(diag["probe_tool"])
        self.assertIn("关闭", diag["probe_tool_disabled_reason"])

    def test_plain_channel_propagates_model_failure(self):
        with self.assertRaises(RuntimeError):
            self._run(
                [_json(_FULL_PAYLOAD)], level="minimal", probe=False,
                error=RuntimeError("quota exhausted"),
            )


if __name__ == "__main__":
    unittest.main()
