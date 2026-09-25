"""合并节点的两种作用域（《动态节点设计规划》§3.3 / §4.4）。

钉住三件事，每一件都是"链能跑通"的前提：

1. **批次合并幂等**：同一条目重跑，产物必须一模一样。追加式实现会产出重复门窗，
   而配额检查只查区间、不查重复，重复会悄悄溜过验收（§4.4）。
2. **批次合并保守**：它只能并入自己那一组，不许删别的组、也不许删骨架自带的主体。
   它跑的时候后面还有分组没到场，此刻按配额剔超额会误伤。
3. **收尾合并以批次成果为底本**：分片已经并过一次，再并一遍就是重复元素。
"""

from __future__ import annotations

import unittest

from app.agent.generation.assembly_workflow import merge_fragments_node
from app.utils.fragment_merger import merge_fragment_batch

_SKELETON = {
    "meta": {"name": "batch-scope"},
    "geometry": {
        "elements": [
            {"id": "wall_s", "type": "wall", "from": [0, 0, 0], "to": [6, 3, 0], "thickness": 0.3},
            # 骨架自己出屋顶；批次合并绝不能把它当成"别人的元素"删掉
            {"id": "roof_main", "type": "roof", "roofType": "gable", "span": 6, "depth": 4},
        ],
        "components": [],
    },
    "materials": {},
}

_DOOR = {
    "id": "door_main",
    "type": "door",
    "parentWall": "wall_s",
    "from": [1.0, 0, 0],
    "width": 1.0,
    "height": 2.2,
    "interaction": "swing",
}

_WINDOW = {
    "id": "window_main",
    "type": "window",
    "parentWall": "wall_s",
    "from": [3.0, 1.0, 0],
    "width": 1.2,
    "height": 1.5,
}


def _brief() -> dict:
    """带一个与 ``_DOOR`` 对应的开口槽位。

    没有槽位的门窗会在收尾归一里被"剔除无槽位开口"删掉，那属于另一条既有规则，
    会把"有没有重复并入"这件事盖住。
    """

    return {
        "component_quota": {},
        "facade_plan": {},
        "opening_slots": [
            {
                "id": "slot_door_1",
                "type": "door",
                "wall_id": "wall_s",
                "from": [1.0, 0, 0],
                "width": 1.0,
                "height": 2.2,
            }
        ],
    }


def _ids(blueprint: dict, kind: str) -> list[str]:
    geometry = blueprint["geometry"]
    return [
        item["id"]
        for item in [*geometry["elements"], *geometry["components"]]
        if item.get("type") == kind
    ]


class FragmentBatchMergeTest(unittest.TestCase):
    def test_repeating_the_same_batch_changes_nothing(self):
        once = merge_fragment_batch(_SKELETON, [_DOOR])
        twice = merge_fragment_batch(once, [_DOOR])
        self.assertEqual(once, twice)
        self.assertEqual(_ids(twice, "door"), ["door_main"])

    def test_batch_keeps_the_skeleton_and_other_groups(self):
        # 先并门，再并窗：两次都不能动骨架的墙与屋顶，也不能动对方
        with_door = merge_fragment_batch(_SKELETON, [_DOOR])
        with_both = merge_fragment_batch(with_door, [_WINDOW])

        self.assertEqual(_ids(with_both, "wall"), ["wall_s"])
        self.assertEqual(_ids(with_both, "roof"), ["roof_main"])
        self.assertEqual(_ids(with_both, "door"), ["door_main"])
        self.assertEqual(_ids(with_both, "window"), ["window_main"])

    def test_fragment_in_state_is_not_mutated_when_the_id_conflicts(self):
        """合并只许改蓝图里的副本。

        撞 id 时 ``_insert_item`` 会给新元素加后缀；如果它改的是 state 里那份分片，
        下一轮收集到的 id 就变成了 ``window_main_1``，溯源对不上、重跑也会漂移。
        """

        base = merge_fragment_batch(_SKELETON, [_WINDOW])
        conflicting = {
            "id": "window_main",  # 与已并入的窗撞 id，但类型不同
            "type": "railing",
            "parentFloor": "floor_1",
            "path": [[0, 0, 0], [1, 0, 0]],
            "height": 1.1,
        }
        merged = merge_fragment_batch(base, [conflicting])

        self.assertEqual(conflicting["id"], "window_main")
        self.assertEqual(_ids(merged, "window"), ["window_main"])
        self.assertEqual(_ids(merged, "railing"), ["window_main_1"])


class MergeNodeScopeTest(unittest.IsolatedAsyncioTestCase):
    async def test_batch_scope_only_merges_its_own_group(self):
        result = await merge_fragments_node(
            {
                "skeleton_blueprint": _SKELETON,
                "design_brief": _brief(),
                "component_fragments": {"door": [_DOOR], "window": [_WINDOW]},
            },
            scope="batch",
            component_types=["door"],
        )

        blueprint = result["merged_blueprint"]
        self.assertEqual(result["merge_diag"]["scope"], "batch")
        self.assertEqual(_ids(blueprint, "door"), ["door_main"])
        # 组外的分片不归这一批管，必须等它自己的批次合并
        self.assertEqual(_ids(blueprint, "window"), [])

    async def test_batch_scope_skips_quota_pruning(self):
        """批次合并不做配额强制——超额构件留给收尾合并，否则会误删还没到场的分组。"""

        result = await merge_fragments_node(
            {
                "skeleton_blueprint": _SKELETON,
                "design_brief": {
                    "component_quota": {"door": {"min": 1, "max": 0}},
                    "facade_plan": {},
                    "opening_slots": [],
                },
                "component_fragments": {"door": [_DOOR]},
            },
            scope="batch",
            component_types=["door"],
        )
        self.assertEqual(_ids(result["merged_blueprint"], "door"), ["door_main"])

    async def test_final_scope_uses_the_batch_result_as_its_base(self):
        """收尾合并以批次成果为底本：批次并入过的东西不能凭空消失。

        判据用"只存在于批次成果里的元素"——若收尾合并从骨架重来一遍，它会不见；
        若它把分片再并一遍，门窗会翻倍。
        """

        batched = merge_fragment_batch(_SKELETON, [_DOOR])
        batched["geometry"]["elements"].append(
            {"id": "floor_from_batch", "type": "floor", "from": [0, 0, 0], "to": [3, 0, 3], "thickness": 0.2}
        )

        result = await merge_fragments_node(
            {
                "skeleton_blueprint": _SKELETON,
                "merged_blueprint": batched,
                "design_brief": _brief(),
                "component_fragments": {"door": [_DOOR]},
            }
        )

        blueprint = result["merged_blueprint"]
        element_ids = [item["id"] for item in blueprint["geometry"]["elements"]]
        self.assertIn("floor_from_batch", element_ids)
        self.assertEqual(_ids(blueprint, "door"), ["door_main"])

    async def test_final_scope_still_merges_when_no_batch_ran(self):
        """旧调用形状（只有分片、没有批次成果）仍要能一次性合并出来。"""

        result = await merge_fragments_node(
            {
                "skeleton_blueprint": _SKELETON,
                "design_brief": _brief(),
                "component_fragments": {"door": [_DOOR]},
            }
        )
        self.assertEqual(_ids(result["merged_blueprint"], "door"), ["door_main"])

    async def test_missing_skeleton_fails_fast(self):
        result = await merge_fragments_node({}, scope="batch", component_types=["door"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("骨架", result["error"])


if __name__ == "__main__":
    unittest.main()
