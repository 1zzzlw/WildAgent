"""设计收敛环（设计文档 §1.6 的第二半）的测试。

**为什么主循环对着一个假编译器测**：真编译器是确定性纯函数，它**不可能**被要求
从一份图纸产出一份"坏蓝图"——把最容易出错的那部分从模型侧搬到编译器侧，正是这次
重构的目的（§2.8）。所以"缺陷序列 → 只重出受影响的块 → 再编译"这段控制流，只能
用一个可控的缺陷源来测。真编译器这一侧的接线由
``test_real_compiler_converges_on_a_healthy_plan`` 单独钉住（本地跑真 ``compile_design``）。

本文件盯死四条红线：

1. 有界：迭代上限 / 缺陷数不下降 / 预算为 0 —— 三种都要停，且**模型调用次数有界**。
2. **只重出受影响的块**：`only_blocks` 必须是缺陷映射出来的那几块，不许整图重出。
3. **认不出的 `design_field` 不猜**：不映射块、不调模型、如实进 `unresolved`。
4. **模型故障不掐掉整轮生成**：原图纸保留、不抛异常、stop_reason 如实记录。
"""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.agent.compiler import MODE_DRY_RUN, CompileDefect
from app.agent.generation.architecture import design_blocks
from app.agent.generation.architecture.convergence import (
    blocking_defects,
    converge_design,
    defect_fingerprint,
    design_level_defects,
)
from app.agent.generation.architecture.design_blocks import (
    BLOCK_BY_NAME,
    DesignBlock,
    block_of_design_field,
)

_CONVERGENCE_MODULE = "app.agent.generation.architecture.convergence"
_DRAFT_TARGET = f"{_CONVERGENCE_MODULE}.draft_design_blocks"
_COMPILE_TARGET = f"{_CONVERGENCE_MODULE}.compile_design"


def _defect(
    severity: str = "error",
    design_field: str = "decisions.massing",
    evidence: str = "体积越界",
    code: str = "dimension_invalid",
) -> CompileDefect:
    return CompileDefect(
        code=code,
        severity=severity,
        target="target",
        evidence=evidence,
        design_field=design_field,
    )


class DesignFieldMappingTest(unittest.TestCase):
    """缺陷里的图纸项 → 该重出哪一块。**认不出必须返回 None**。"""

    def test_every_design_field_produced_by_the_compiler_maps_to_a_block(self):
        cases = {
            "decisions.massing": "massing",
            "decisions.volumes": "massing",
            "decisions.facades": "facade",
            "decisions.facades.front.ground_pattern": "facade",
            "decisions.facades.<face>": "facade",
            "decisions.roof": "roof",
            "decisions.structural_grid": "structure",
            "decisions.circulation": "structure",
            "decisions.component_quota": "components",
            "decisions.components[type=canopy]": "components",
        }
        for field, name in cases.items():
            block = block_of_design_field(field)
            self.assertIsNotNone(block, field)
            self.assertEqual(block.name, name, field)

    def test_unknown_or_blueprint_level_issues_are_not_guessed(self):
        for field in ("", None, "   ", "缺少顶层字段 'meta'", "decisions.unknown"):
            self.assertIsNone(block_of_design_field(field), repr(field))

    def test_prefix_matching_does_not_swallow_a_longer_word(self):
        # decisions.roofing ≠ decisions.roof：多一个字母就是另一件事，误配会去改错的块。
        self.assertIsNone(block_of_design_field("decisions.roofing"))
        self.assertIsNone(block_of_design_field("decisions.componentship"))


class DefectFilterTest(unittest.TestCase):
    def test_only_error_severity_enters_the_loop(self):
        result = SimpleNamespace(
            defects=[_defect(severity="error"), _defect(severity="warn", code="w")]
        )
        self.assertEqual([item.code for item in blocking_defects(result)], ["dimension_invalid"])

    def test_unmappable_defects_are_kept_out_of_the_revision_targets(self):
        defects = [
            _defect(design_field="decisions.massing"),
            _defect(design_field="", code="blueprint_level"),
        ]
        self.assertEqual(
            [item.design_field for item in design_level_defects(defects)], ["decisions.massing"]
        )

    def test_fingerprint_is_a_stable_set_of_the_three_identity_fields(self):
        fingerprint = defect_fingerprint([_defect(), _defect(), _defect(evidence="别的")])
        self.assertEqual(len(fingerprint), 2)
        self.assertIn(("dimension_invalid", "decisions.massing", "体积越界"), fingerprint)


class _FakeCompiler:
    """按序吐缺陷的假编译器；序列用尽后重复最后一项。"""

    def __init__(self, *defects_per_call: list[CompileDefect]) -> None:
        self.queue = list(defects_per_call)
        self.calls: list[dict] = []

    def __call__(self, plan, **kwargs):
        self.calls.append({"plan": plan, **kwargs})
        defects = self.queue.pop(0) if len(self.queue) > 1 else (self.queue[0] if self.queue else [])
        return SimpleNamespace(mode=MODE_DRY_RUN, blueprint=None, design_brief=None, defects=defects)


class _FakeDraft:
    """假执行器：记录被要求重出哪几块，返回预置草稿。"""

    #: 默认草稿是**能过归一化**的一版体量修订。用残缺的 facades 当默认会让
    #: `normalize_architecture_plan` 抛 IndexError（那条路径由专门的用例钉）。
    _DEFAULT = {"massing": {"floors": 3, "width": 15, "depth": 12}}

    def __init__(self, draft=None, *, error=None, settle: bool = True) -> None:
        self.draft = dict(self._DEFAULT) if draft is None else draft
        self.error = error
        self.settle = settle
        self.calls: list[dict] = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        draft = self.draft if self.settle else {}
        return draft, {"blocks": [], "unsettled_blocks": [] if self.settle else list(kwargs.get("only_blocks") or [])}


_PLAN = {"target_kind": "architecture", "massing": {"floors": 2}, "profile": "villa"}


def _converge(compiler, draft, **overrides):
    with patch(_COMPILE_TARGET, compiler), patch(_DRAFT_TARGET, draft):
        return asyncio.run(
            converge_design(
                plan=dict(_PLAN),
                raw_plan=None,
                user_message="生成一个两层别墅",
                complexity_profile=None,
                architecture_profile=None,
                thinking_mode=False,
                **overrides,
            )
        )


class ConvergenceLoopTest(unittest.TestCase):
    def test_converged_plan_never_touches_the_model(self):
        draft = _FakeDraft(error=AssertionError("收敛了就不该调模型"))
        outcome = _converge(_FakeCompiler([]), draft)

        self.assertEqual(outcome.diag["stop_reason"], "converged")
        self.assertEqual(outcome.diag["revisions"], 0)
        self.assertFalse(outcome.changed)
        self.assertEqual(draft.calls, [])
        # 合并基准是否给到，直接决定"重出某几块之后图纸会不会缩水"——必须可见。
        self.assertFalse(outcome.diag["raw_plan_available"])

    def test_mappable_defect_triggers_a_targeted_redraft_of_exactly_those_blocks(self):
        # 第 1 次编译：两条缺陷，分属 roof 与 facade；第 2 次：干净。
        compiler = _FakeCompiler(
            [
                _defect(design_field="decisions.roof", evidence="屋顶悬空"),
                _defect(design_field="decisions.facades.front.ground_pattern", evidence="门窗越界"),
            ],
            [],
        )
        draft = _FakeDraft()
        outcome = _converge(compiler, draft)

        self.assertEqual(outcome.diag["stop_reason"], "converged")
        self.assertEqual(outcome.diag["revisions"], 1)
        self.assertTrue(outcome.changed)
        # 🔴 只重出受影响的块 —— 不是整图重出。
        self.assertEqual(draft.calls[0]["only_blocks"], ["facade", "roof"])
        self.assertEqual(len(draft.calls), 1)
        # 缺陷作为**首轮证据**传进去（不让模型先白写一次再被驳）。
        self.assertEqual(len(draft.calls[0]["defects"]), 2)
        self.assertEqual(outcome.diag["initial_defects"], 2)
        self.assertEqual(outcome.diag["final_defects"], 0)

    def test_unmappable_defect_stops_without_guessing_a_block(self):
        compiler = _FakeCompiler([_defect(design_field="", code="blueprint_level", evidence="缺少顶层字段 'meta'")])
        draft = _FakeDraft(error=AssertionError("映射不到块就不许调模型"))
        outcome = _converge(compiler, draft)

        self.assertEqual(outcome.diag["stop_reason"], "converged")
        self.assertEqual(draft.calls, [])
        self.assertEqual(len(outcome.diag["unresolved"]), 1)
        self.assertFalse(outcome.changed)

    def test_no_progress_stops_after_the_configured_rounds(self):
        # 每一轮都把缺陷数维持在 1 —— 改了等于没改。
        compiler = _FakeCompiler([_defect()])
        draft = _FakeDraft()
        outcome = _converge(compiler, draft)

        self.assertEqual(outcome.diag["stop_reason"], "no_progress")
        self.assertEqual(outcome.diag["revisions"], 2)
        self.assertEqual(len(draft.calls), 2)

    def test_max_rounds_bounds_the_loop_even_when_it_keeps_improving(self):
        compiler = _FakeCompiler(
            [_defect(evidence=f"缺陷 {i}") for i in range(5, 0, -1)],
            [_defect(evidence="缺陷 4")],
            [_defect(evidence="缺陷 3")],
        )
        # 每次 evidence 不同 ⇒ 指纹在变，但条数在降：判进展只看条数。
        draft = _FakeDraft()
        outcome = _converge(compiler, draft, max_rounds=2)

        self.assertEqual(outcome.diag["stop_reason"], "max_rounds")
        self.assertEqual(outcome.diag["revisions"], 2)
        self.assertEqual(len(draft.calls), 2)

    def test_zero_budget_stops_before_any_model_call(self):
        compiler = _FakeCompiler([_defect()])
        draft = _FakeDraft(error=AssertionError("预算为 0 不该调模型"))
        outcome = _converge(compiler, draft, max_rounds=0)

        self.assertEqual(outcome.diag["stop_reason"], "max_rounds")
        self.assertEqual(outcome.diag["revisions"], 0)
        self.assertEqual(draft.calls, [])

    def test_model_failure_keeps_the_original_plan_and_never_raises(self):
        compiler = _FakeCompiler([_defect()])
        draft = _FakeDraft(error=RuntimeError("quota exhausted"))
        outcome = _converge(compiler, draft)

        self.assertEqual(outcome.diag["stop_reason"], "model_error")
        self.assertFalse(outcome.changed)
        self.assertEqual(outcome.plan, _PLAN)
        self.assertIn("quota exhausted", outcome.diag["rounds"][0]["model_error"])

    def test_empty_draft_stops_instead_of_burning_more_calls(self):
        compiler = _FakeCompiler([_defect()])
        draft = _FakeDraft(settle=False)
        outcome = _converge(compiler, draft)

        self.assertEqual(outcome.diag["stop_reason"], "no_draft")
        self.assertEqual(len(draft.calls), 1)
        self.assertFalse(outcome.changed)

    def test_scope_guard_refuses_to_redraft_outside_the_allowed_blocks(self):
        compiler = _FakeCompiler([_defect(design_field="decisions.facades")])
        draft = _FakeDraft(error=AssertionError("越界的块不该被重出"))
        outcome = _converge(compiler, draft, only_blocks=["roof"])

        self.assertEqual(outcome.diag["stop_reason"], "outside_scope")
        self.assertEqual(draft.calls, [])
        self.assertEqual(len(outcome.diag["unresolved"]), 1)

    def test_invalid_revision_keeps_the_previous_plan(self):
        """模型给的草稿让归一化抛错 ⇒ 保留上一版图纸，**不许**穿出异常掐掉生成。

        （2026-09-30：原触发器是"bays=1 缺 ground_pattern"的真实越界草稿；
        `_clamp_number` 根修后这份草稿已合法，改为强制归一化抛错，
        让本用例钉的"异常不得穿出收敛环"与具体触发方式解耦。越界本身
        由 test_architecture_plan.py::TestEntrancePunchWithinBays 钉。）
        """
        compiler = _FakeCompiler([_defect(design_field="decisions.facades")])
        draft = _FakeDraft({"facades": {"front": {"bays": 3, "ground_pattern": ["window"] * 3}}})

        with patch(
            "app.agent.generation.architecture.normalize_architecture_plan",
            side_effect=IndexError("list assignment index out of range"),
        ):
            outcome = _converge(compiler, draft)

        self.assertEqual(outcome.diag["stop_reason"], "invalid_revision")
        self.assertFalse(outcome.changed)
        self.assertEqual(outcome.plan, _PLAN)
        self.assertIn("normalize_error", outcome.diag["rounds"][0])

    def test_real_compiler_converges_on_a_healthy_plan(self):
        """真 ``compile_design`` 的接线：healthy 图纸一次就收敛，且不碰模型。"""

        from app.agent.generation.architecture import normalize_architecture_plan

        plan = normalize_architecture_plan(
            {"massing": {"floors": 2}}, user_message="生成一个两层别墅"
        )
        draft = _FakeDraft(error=AssertionError("没有设计级缺陷就不该调模型"))
        with patch(_DRAFT_TARGET, draft):
            outcome = asyncio.run(
                converge_design(
                    plan=plan,
                    raw_plan={"massing": {"floors": 2}},
                    user_message="生成一个两层别墅",
                    complexity_profile=None,
                    architecture_profile=None,
                    thinking_mode=False,
                )
            )

        self.assertEqual(outcome.diag["stop_reason"], "converged")
        self.assertEqual(outcome.diag["revisions"], 0)
        self.assertFalse(outcome.changed)
        self.assertEqual(outcome.plan, plan)
        self.assertEqual(draft.calls, [])
        self.assertTrue(outcome.diag["raw_plan_available"])


class DesignConvergenceNodeTest(unittest.TestCase):
    """节点只做状态读写；算法在领域层。这里钉的是三条边界。"""

    _NODE_COMPILE = _COMPILE_TARGET
    _NODE_DRAFT = _DRAFT_TARGET

    def _run(self, state, compiler, draft):
        from app.agent.nodes.design_convergence_node import design_convergence

        with patch(self._NODE_COMPILE, compiler), patch(self._NODE_DRAFT, draft):
            return asyncio.run(design_convergence(state))

    def test_object_plans_pass_through_untouched(self):
        draft = _FakeDraft(error=AssertionError("物件链不该进收敛环"))
        update = self._run({"architecture_plan": {"target_kind": "object"}}, _FakeCompiler([]), draft)
        self.assertEqual(update, {})
        self.assertEqual(draft.calls, [])

    def test_missing_plan_passes_through(self):
        self.assertEqual(self._run({}, _FakeCompiler([]), _FakeDraft()), {})
        self.assertEqual(self._run({"architecture_plan": {}}, _FakeCompiler([]), _FakeDraft()), {})

    def test_unchanged_plan_only_writes_the_diagnostic(self):
        state = {"architecture_plan": dict(_PLAN), "user_message": "生成一个两层别墅"}
        update = self._run(state, _FakeCompiler([]), _FakeDraft())
        self.assertEqual(set(update), {"design_convergence"})
        self.assertEqual(update["design_convergence"]["stop_reason"], "converged")

    def test_changed_plan_rewrites_the_plan_and_the_document(self):
        compiler = _FakeCompiler([_defect(design_field="decisions.facades")], [])
        draft = _FakeDraft()
        state = {"architecture_plan": dict(_PLAN), "user_message": "生成一个两层别墅"}

        fake_document = SimpleNamespace(model_dump=lambda mode="json": {"revision": 2})
        with patch(
            "app.agent.generation.architecture.workflow.build_design_document_or_error",
            lambda *args, **kwargs: fake_document,
        ), patch(
            "app.agent.nodes.design_convergence_node.resolve_design",
            lambda document: SimpleNamespace(model_dump=lambda mode="json": {"resolved": True}),
        ):
            update = self._run(state, compiler, draft)

        self.assertEqual(set(update), {"architecture_plan", "design_document", "resolved_design", "design_convergence"})
        self.assertNotEqual(update["architecture_plan"], _PLAN)
        self.assertEqual(update["design_document"], {"revision": 2})
        self.assertEqual(update["resolved_design"], {"resolved": True})

    def test_broken_converged_plan_is_reverted_not_written(self):
        """收敛把图纸改坏了 ⇒ 保留原图纸、如实记账，**不许**因此掐掉生成。"""

        compiler = _FakeCompiler([_defect(design_field="decisions.facades")], [])
        draft = _FakeDraft()
        state = {"architecture_plan": dict(_PLAN), "user_message": "生成一个两层别墅"}

        def _boom(*_args, **_kwargs):
            raise ValueError("体量覆盖面不足")

        with patch(
            "app.agent.generation.architecture.workflow.build_design_document_or_error", _boom
        ):
            update = self._run(state, compiler, draft)

        self.assertEqual(set(update), {"design_convergence"})
        self.assertTrue(update["design_convergence"]["reverted"])
        self.assertIn("体量覆盖面不足", update["design_convergence"]["document_error"])


class BlockTableContractTest(unittest.TestCase):
    """块表是常量，它的改动必须显式——这里钉住"块名闭集"与文档 §1.6 的表一致。"""

    def test_block_names_are_the_documented_set(self):
        self.assertEqual(
            [block.name for block in design_blocks.DESIGN_BLOCKS],
            ["massing", "structure", "facade", "roof", "components"],
        )

    def test_every_block_declares_a_non_empty_contract(self):
        for block in design_blocks.DESIGN_BLOCKS:
            self.assertIsInstance(block, DesignBlock)
            self.assertTrue(block.contract.strip(), block.name)
            self.assertTrue(block.fields, block.name)

    def test_components_depends_on_every_other_block(self):
        components = BLOCK_BY_NAME["components"]
        self.assertEqual(set(components.depends_on), {"massing", "structure", "facade", "roof"})


if __name__ == "__main__":
    unittest.main()
