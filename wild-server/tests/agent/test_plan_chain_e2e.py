"""新链（plan 驱动）的端到端集成测试。

跑的是一张**真实编译的图**：真实的 classify → architecture → design_review →
skeleton → plan → execute ⇄ replanner → final_validate 拓扑，真实的 `expand_plan`
展开、真实的 `reconcile` 对账与有界终止判定。只把模型调用、RAG 与设计仓储换成
确定性 stub。

三个用例分别钉住三件事：

1. 正常路径：条目按顺序跑完，`done` 由产物事实决定，不是节点自称；
2. 失败重试：一条条目失败一次后重试成功，队列继续往下走；
3. 产物永不落地：重试预算耗尽后条目转 `abandoned` 并交付，**循环必须停下来**。
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from unittest.mock import patch

from langgraph.checkpoint.memory import InMemorySaver

import app.agent.graph as graph_module
import app.agent.plan.handlers as handlers_module
from app.agent.graph import build_generation_graph, plan_recursion_limit

_DESIGN_BRIEF = {
    "opening_slots": [
        {
            "id": "slot_door_1",
            "type": "door",
            "wall_id": "wall_south",
            "from": 1.0,
            "width": 1.0,
            "height": 2.2,
        }
    ],
    "component_quota": {"door": {"min": 1, "max": 2}},
}

_DOOR_FRAGMENT = {
    "id": "door_1",
    "type": "door",
    "parentWall": "wall_south",
    "from": 1.0,
    "width": 1.0,
    "height": 2.2,
}

_SKELETON = {
    "meta": {"name": "plan-chain"},
    "geometry": {
        "elements": [{"id": "wall_south", "type": "wall"}],
        "components": [],
    },
}


@dataclass
class _StubValidationResult:
    """`validate` 条目消费的校验结果（形状与真实 ValidationResult 一致）。"""

    name: str = "validate_blueprint_structure"
    has_error: bool = False
    has_warning: bool = False
    output: str = ""


async def _deterministic_replan(plan):
    """异常分支的模型调用：本用例只验证"调度不调模型也能收敛"，故用确定性决策。"""

    from app.agent.plan.replan import deterministic_decision

    decision = deterministic_decision(plan)
    return decision, {"decision_source": decision.source, "stubbed": True}


def _blueprint_with(door: dict | None) -> dict:
    return {
        "meta": {"name": "plan-chain-merged"},
        "geometry": {
            "elements": [{"id": "wall_south", "type": "wall"}],
            "components": [door] if door else [],
        },
    }


class _StubWorld:
    """把模型、检索与设计仓储替换成确定性 stub，图结构与计划逻辑保持真实。"""

    def __init__(self, *, fragment_replies, merge_blueprints):
        """``fragment_replies``：每次 generate 依次返回的分片列表；``merge_blueprints``：每次 merge 依次返回的蓝图。"""

        self.fragment_replies = list(fragment_replies)
        self.merge_blueprints = list(merge_blueprints)
        self.generate_calls = 0
        self.merge_calls = 0

    # ── 模型侧 stub ──

    async def _generator(self, _context):
        fragments = (
            self.fragment_replies[self.generate_calls]
            if self.generate_calls < len(self.fragment_replies)
            else []
        )
        self.generate_calls += 1
        return {
            "component_fragments": {"door": fragments},
            "component_diagnostics": {
                "door_gen": {"label": "门", "rag_chars": 120, "validation_passed": bool(fragments)},
            },
        }

    async def _validator(self, state):
        fragments = (state.get("component_fragments") or {}).get("door") or []
        return {
            "component_fragments": {"door": fragments},
            "component_diagnostics": {
                "door_val": {"label": "门", "validation_passed": True, "fragment_count": len(fragments)},
            },
        }

    async def _merge(self, _state, **_scope):
        blueprint = (
            self.merge_blueprints[self.merge_calls]
            if self.merge_calls < len(self.merge_blueprints)
            else _blueprint_with(None)
        )
        self.merge_calls += 1
        return {"merged_blueprint": blueprint, "status": "generating"}

    # ── 节点 stub ──

    def install(self, case: unittest.TestCase) -> None:
        async def classifier(_state):
            return {"intent": "generate"}

        async def plan_strategy(_state):
            from app.agent.plan.contracts import PlanKindStrategy, PlanStrategy

            return (
                PlanStrategy(
                    kinds=[
                        PlanKindStrategy(
                            kind="door", subtype="入户双开门", reason="用户点名要门"
                        )
                    ],
                    notes="单层住宅，重点在入口",
                    source="llm",
                ),
                {"strategy_source": "llm", "used_fallback": False},
            )

        async def architecture(_state):
            return {"architecture_plan": {"massing": {"floors": 1}}}

        async def material_plan(_state):
            return {"material_plan": {"roles": [{"role": "facade"}]}}

        def design_review(_state):
            return {"design_review_status": "approved"}

        async def skeleton(_state):
            # suggested_components 就是模型给出的"策略"：要不要做门由它决定
            return {
                "skeleton_blueprint": _SKELETON,
                "skeleton_summary": "一层主体",
                "design_brief": _DESIGN_BRIEF,
                "suggested_components": ["door"],
                "status": "generating",
            }

        async def validate(_state):
            return {
                "final_blueprint": _blueprint_with(_DOOR_FRAGMENT),
                "validation_results": [],
                "validation_error_count": 0,
                "validation_warning_count": 0,
                "status": "complete",
            }

        patches = (
            patch.object(graph_module, "classifier_node", classifier),
            patch.object(graph_module, "architecture_planner", architecture),
            patch.object(graph_module, "material_planner", material_plan),
            patch.object(graph_module, "design_review", design_review),
            patch.object(graph_module, "skeleton_generator", skeleton),
            patch.object(graph_module, "validate_node", validate),
            patch(
                "app.agent.generation.component_workflow.create_component_generator",
                lambda _config: self._generator,
            ),
            patch(
                "app.agent.generation.component_workflow.create_component_validator",
                lambda _config: self._validator,
            ),
            patch("app.agent.generation.assembly_workflow.merge_fragments_node", self._merge),
            # `validate` 条目消费的是校验流水线；本用例钉的是调度循环，不重复校验器自己的用例
            patch(
                "app.services.agent_service.run_validation_pipeline",
                lambda _blueprint: [_StubValidationResult()],
            ),
            patch("app.services.agent_service._final_errors", lambda _results: []),
            # plan/replanner 的模型边界用固定策略替代，其余展开、执行与对账保持真实
            patch("app.agent.plan.workflow.request_plan_strategy", plan_strategy),
            patch(
                "app.agent.plan.workflow.request_replan",
                lambda plan, state, **kwargs: _deterministic_replan(plan),
            ),
        )
        for item in patches:
            item.start()
            case.addCleanup(item.stop)
        # 处理器按构件类型缓存工厂产物：清掉以免上一个用例的 stub 泄漏到下一个
        case.addCleanup(handlers_module._GENERATORS.clear)
        case.addCleanup(handlers_module._VALIDATORS.clear)
        handlers_module._GENERATORS.clear()
        handlers_module._VALIDATORS.clear()


class PlanChainEndToEndTest(unittest.IsolatedAsyncioTestCase):
    def _run(self, world: _StubWorld, thread_id: str) -> dict:
        world.install(self)
        compiled = build_generation_graph(enable_callback=False, checkpointer=InMemorySaver())
        return compiled, {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": plan_recursion_limit(10, 3),
        }

    async def _invoke(self, world: _StubWorld, thread_id: str) -> dict:
        compiled, config = self._run(world, thread_id)
        return await compiled.ainvoke(
            {"user_message": "生成一个带入户门的单层住宅", "request_id": "req_plan_chain"},
            config,
        )

    def _plan(self, result: dict):
        from app.agent.plan.contracts import PlanDocument

        return PlanDocument.model_validate(result["plan"])

    async def test_happy_path_runs_every_item_once_and_finishes(self):
        world = _StubWorld(
            fragment_replies=[[_DOOR_FRAGMENT]],
            # 一组分片要过两次合并：批次合并（并入）+ 收尾合并（归一）。两者都是幂等的，
            # 所以返回同一份蓝图即可——真实实现里收尾合并也是以批次合并的产物为底本。
            merge_blueprints=[_blueprint_with(_DOOR_FRAGMENT)] * 2,
        )

        result = await self._invoke(world, "plan-chain-happy")

        plan = self._plan(result)
        # §3.3：每组一条 generate + 一条批次 merge，末尾收尾 merge + validate
        self.assertEqual(
            [item.op for item in plan.items], ["generate", "merge", "merge", "validate"]
        )
        self.assertEqual(
            [item.id for item in plan.items][:2], ["generate_door_01", "merge_door_01"]
        )
        self.assertEqual({item.status for item in plan.items}, {"done"})
        # 每条条目各跑一次：generate 不会被丢掉，两条 merge 也不会被 generate 卡住
        self.assertEqual(world.generate_calls, 1)
        self.assertEqual(world.merge_calls, 2)
        self.assertEqual(plan.iterations, 4)
        self.assertGreaterEqual(plan.budget["iterations"], len(plan.items))
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["current_item_id"], "validate_all_01")
        # 条目级审计轨迹：每条条目都有记录，否则出问题时无法归因
        self.assertEqual(
            set(result["tool_trace"]),
            {"generate_door_01", "merge_door_01", "merge_all_01", "validate_all_01"},
        )
        # plan_events 是**每轮的增量**（前端自己累加，见 §6.3）：最后一轮只带本轮变化
        events = result["plan_events"]
        self.assertTrue(events)
        self.assertEqual({"item_id", "status", "op", "kind"} - set(events[0]), set())
        self.assertIn("validate_all_01", {event["item_id"] for event in events})

    async def test_failed_generate_retries_then_continues(self):
        world = _StubWorld(
            fragment_replies=[[], [_DOOR_FRAGMENT]],
            merge_blueprints=[_blueprint_with(_DOOR_FRAGMENT)] * 4,
        )

        result = await self._invoke(world, "plan-chain-retry")

        plan = self._plan(result)
        generate = plan.item("generate_door_01")
        self.assertEqual(generate.status, "done")
        self.assertEqual(generate.run.attempts, 1)  # 只算失败的那一次
        self.assertEqual(world.generate_calls, 2)
        self.assertEqual({item.status for item in plan.items}, {"done"})

    async def test_batch_merge_repeats_after_retry_so_the_new_fragment_lands(self):
        """上游被退回时下游必须跟着失效（store.refresh_statuses 的下游失效规则）。

        没有这条规则，重跑出来的新分片会永远并不进蓝图——条目在生成侧"成功"，
        在交付侧却什么都没有，属于静默丢产物。
        """

        world = _StubWorld(
            fragment_replies=[[], [_DOOR_FRAGMENT]],
            merge_blueprints=[_blueprint_with(_DOOR_FRAGMENT)] * 4,
        )

        result = await self._invoke(world, "plan-chain-remerge")

        plan = self._plan(result)
        merge = plan.item("merge_door_01")
        self.assertEqual(merge.status, "done")
        self.assertEqual(merge.run.attempts, 0)  # 下游失效重跑不是失败，不烧重试额度
        # 第一次 generate 失败时批次合并还没资格跑，所以两次 merge 只对应成功那一轮
        self.assertEqual(world.merge_calls, 2)

    async def test_artifact_never_lands_is_abandoned_and_loop_stops(self):
        """产物永远并不进蓝图时，条目必须被有界地放弃——这是防死循环的主力。"""

        world = _StubWorld(
            fragment_replies=[[_DOOR_FRAGMENT]] * 8,
            merge_blueprints=[_blueprint_with(None)] * 16,  # 合并结果里没有门
        )

        result = await self._invoke(world, "plan-chain-abandon")

        plan = self._plan(result)
        generate = plan.item("generate_door_01")
        self.assertEqual(generate.status, "abandoned")
        self.assertEqual(generate.run.attempts, generate.run.max_attempts)
        # 循环有界：条目被放弃即终态，不会一直重跑
        self.assertLessEqual(world.generate_calls, generate.run.max_attempts + 1)
        # 局部失败不阻断交付：merge / validate 照常跑完
        self.assertEqual(plan.item("merge_all_01").status, "done")
        self.assertEqual(plan.item("validate_all_01").status, "done")
        self.assertEqual(result["status"], "complete")
        from app.agent.plan.store import terminal_stats

        self.assertEqual(terminal_stats(plan)["unfinished"], 0)


class ObjectChainEndToEndTest(unittest.IsolatedAsyncioTestCase):
    """物件需求（"生成一个桌子"）在**同一张真图**里走完整条链。

    这个用例存在的理由是一个曾经真实发生的缺陷：物件需求被判成建筑，用户拿到一栋房子
    当"桌子的替代品"。所以这里钉的不是"家具能生成"（那由 `test_object_plan.py` 钉），
    而是**三个必须同时成立的事实**：

    1. 图分叉到 `object_design`，`architecture` 一次都没进；
    2. 物件规格（逐件尺寸与摆位）通过 `design_brief.object_specs` 传到了下游；
    3. 交付蓝图里只有家具、**没有一片墙**——漏掉这一条，前两条对了也还是房子。
    """

    _TABLE_SPEC = {
        "kind": "furniture",
        "subtype": "table",
        "count": 1,
        "width": 1.8,
        "depth": 0.9,
        "height": 0.75,
        "placement": "置于场景中部",
    }
    _CHAIR_SPEC = {
        "kind": "furniture",
        "subtype": "chair",
        "count": 4,
        "width": 0.45,
        "depth": 0.5,
        "height": 0.9,
        "placement": "两两分列长边两侧、面向桌面",
    }

    def _object_plan(self) -> dict:
        return {
            "target_kind": "object",
            "concept": "胡桃木餐桌配四椅",
            "objects": [dict(self._TABLE_SPEC), dict(self._CHAIR_SPEC)],
            "design_rationale": ["只交付家具，不引入墙体与屋顶"],
        }

    def _furniture_elements(self) -> list[dict]:
        return [
            {
                "type": "furniture",
                "id": f"furniture_{spec['subtype']}_1",
                "subtype": spec["subtype"],
                "position": [0.0, 0.0, 0.0],
                "dimensions": {
                    "width": spec["width"],
                    "depth": spec["depth"],
                    "height": spec["height"],
                },
                "material": "wood",
            }
            for spec in (self._TABLE_SPEC, self._CHAIR_SPEC)
        ]

    def _install(self, case: unittest.TestCase, entered: dict):
        from app.agent.generation.objects.skeleton import (
            build_object_skeleton,
            object_design_brief,
        )
        from app.agent.plan.contracts import PlanKindStrategy, PlanStrategy

        async def classifier(_state):
            return {"intent": "generate", "intent_target_kind": "object"}

        async def object_design(_state):
            from app.design.resolver import build_design_document, resolve_design

            plan = self._object_plan()
            entered["object_design"] = True
            document = build_design_document(
                plan,
                session_id="session_object_e2e",
                source_request="生成一个桌子",
                building_type="asset",
            )
            return {
                "architecture_plan": plan,
                "design_document": document.model_dump(mode="json"),
                "resolved_design": resolve_design(document).model_dump(mode="json"),
                "design_review_status": "pending",
            }

        async def architecture(_state):
            entered["architecture"] = True
            return {"architecture_plan": {"massing": {"floors": 1}}}

        async def material_plan(_state):
            return {"material_plan": {"roles": [{"role": "wood"}]}}

        def design_review(_state):
            return {"design_review_status": "approved"}

        async def skeleton(state):
            # 真实骨架与真实设计清单：不桩，否则测不到 `object_specs` 这条通道。
            plan = state.get("architecture_plan") or {}
            brief = object_design_brief(plan)
            entered["design_brief"] = brief
            return {
                "skeleton_blueprint": build_object_skeleton(plan, "生成一个桌子"),
                "skeleton_summary": brief and "物件场景：无墙、无楼板" or "",
                "design_brief": brief,
                "suggested_components": list(plan.get("component_quota") or {}),
                "status": "generating",
            }

        async def plan_strategy(_state):
            return (
                PlanStrategy(
                    kinds=[
                        PlanKindStrategy(
                            kind="furniture", subtype="table", reason="用户点名要一张桌子"
                        )
                    ],
                    notes="物件场景，无宿主",
                    source="llm",
                ),
                {"strategy_source": "llm", "used_fallback": False},
            )

        async def validate(_state):
            return {
                "final_blueprint": {
                    "meta": {"name": "object-scene"},
                    "geometry": {"elements": self._furniture_elements(), "components": []},
                },
                "validation_results": [],
                "validation_error_count": 0,
                "validation_warning_count": 0,
                "status": "complete",
            }

        async def generate(_context):
            return {
                "component_fragments": {"furniture": self._furniture_elements()},
                "component_diagnostics": {
                    "furniture_gen": {"label": "家具", "rag_chars": 80, "validation_passed": True}
                },
            }

        async def validate_fragment(state):
            return {
                "component_fragments": {
                    "furniture": (state.get("component_fragments") or {}).get("furniture") or []
                },
                "component_diagnostics": {"furniture_val": {"label": "家具", "validation_passed": True}},
            }

        async def merge(_state, **_scope):
            return {
                "merged_blueprint": {
                    "meta": {"name": "object-scene"},
                    "geometry": {"elements": self._furniture_elements(), "components": []},
                },
                "status": "generating",
            }

        patches = (
            patch.object(graph_module, "classifier_node", classifier),
            patch.object(graph_module, "object_planner", object_design),
            patch.object(graph_module, "architecture_planner", architecture),
            patch.object(graph_module, "material_planner", material_plan),
            patch.object(graph_module, "design_review", design_review),
            patch.object(graph_module, "skeleton_generator", skeleton),
            patch.object(graph_module, "validate_node", validate),
            patch(
                "app.agent.generation.component_workflow.create_component_generator",
                lambda _config: generate,
            ),
            patch(
                "app.agent.generation.component_workflow.create_component_validator",
                lambda _config: validate_fragment,
            ),
            patch("app.agent.generation.assembly_workflow.merge_fragments_node", merge),
            patch(
                "app.services.agent_service.run_validation_pipeline",
                lambda _blueprint: [_StubValidationResult()],
            ),
            patch("app.services.agent_service._final_errors", lambda _results: []),
            patch("app.agent.plan.workflow.request_plan_strategy", plan_strategy),
            patch(
                "app.agent.plan.workflow.request_replan",
                lambda plan, state, **kwargs: _deterministic_replan(plan),
            ),
        )
        for item in patches:
            item.start()
            case.addCleanup(item.stop)
        case.addCleanup(handlers_module._GENERATORS.clear)
        case.addCleanup(handlers_module._VALIDATORS.clear)
        handlers_module._GENERATORS.clear()
        handlers_module._VALIDATORS.clear()

    async def test_object_request_never_enters_the_architecture_chain(self):
        entered: dict = {}
        self._install(self, entered)
        compiled = build_generation_graph(enable_callback=False, checkpointer=InMemorySaver())

        result = await compiled.ainvoke(
            {"user_message": "生成一个桌子", "request_id": "req_object_chain"},
            {
                "configurable": {"thread_id": "object-chain"},
                "recursion_limit": plan_recursion_limit(10, 3),
            },
        )

        # ① 分叉正确：进了物件链，建筑方案节点一次都没进
        self.assertTrue(entered.get("object_design"))
        self.assertNotIn("architecture", entered)

        # ② 逐件规格确实传到了下游（配额只有一行 note，承载不了两件家具各自的尺寸与摆位）
        specs = entered["design_brief"]["object_specs"]
        self.assertEqual([spec["subtype"] for spec in specs], ["table", "chair"])
        self.assertEqual([spec["width"] for spec in specs], [1.8, 0.45])
        self.assertEqual(specs[1]["placement"], "两两分列长边两侧、面向桌面")

        # ③ 交付的是家具，没有任何建筑元素
        from app.agent.plan.contracts import PlanDocument

        plan = PlanDocument.model_validate(result["plan"])
        self.assertEqual(plan.item("generate_furniture_01").op, "generate")
        self.assertEqual(
            {item.op for item in plan.items}, {"generate", "merge", "validate"}
        )
        self.assertNotIn("generate_wall_01", {item.id for item in plan.items})

        document = result["design_document"]
        self.assertEqual(document["decisions"]["kind"], "object")
        self.assertNotIn("massing", document["decisions"])

        elements = result["final_blueprint"]["geometry"]["elements"]
        self.assertEqual({element["type"] for element in elements}, {"furniture"})
        self.assertNotIn("wall", {element["type"] for element in elements})
        self.assertEqual(result["status"], "complete")


if __name__ == "__main__":
    unittest.main()
