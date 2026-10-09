"""退台（stepped）体量的屋面承托 —— 2026-10-08 真实事故的守卫。

事故：底层 20×15、二层退到 14×9 的别墅，编译器给出一块覆盖整栋的屋面
（span 21.2 × depth 16.2 = 20×15 + 2×0.6 出檐）。但 ``get_roof_support_bounds``
按 ``roof.position[1]=7.0``（顶层墙顶）选承托墙 ⇒ 只选中层 14×9 的墙
⇒ ``fix_roof_coverage`` 把屋面"修"成 15.2×10.2
⇒ 与已审核实体不符 ⇒ ``approved_design_mutation`` 报 error，整轮生成失败。

修法：识别退台时改用**各层外轮廓的并集**（即底层那一圈墙）。

🔴 本文件最关键的不是"退台能修对"，而是**非退台必须一点不变**：
   ``get_roof_support_bounds`` 被 5 处调用（两个 validator + 两个 fix + 预览），
   一旦对普通建筑也改，就会把一大片原本正确的屋面改坏。
   所以每条"能修对"的用例都配一条"不许动别的"的反向用例。
"""
import json
import unittest
from pathlib import Path

from app.design.compilation import compile_document
from app.design.contracts import DesignDocument
from app.design.normalization import approved_compilation_changes
from app.tools.spatial_tools import (
    _stepped_support_y,
    fix_roof_coverage,
    get_roof_support_bounds,
)

_SESSION = Path(__file__).resolve().parents[2] / (
    "storage/sessions/session_1791461822471.json"
)


def run_tool(tool, blueprint):
    return getattr(tool, "func", tool)(blueprint)


def _wall(wall_id, x0, z0, x1, z1, y0, y1):
    return {"id": wall_id, "type": "wall", "thickness": 0.24,
            "from": [x0, y0, z0], "to": [x1, y1, z1]}


class SteppedRoofSupportTest(unittest.TestCase):
    """退台体量：屋面承托必须取各层外轮廓并集，不是"当层那一圈墙"。"""

    def _stepped(self) -> dict:
        """底层 20×15（y0~3.5）→ 二层退到 14×9（y3.5~7.0）。"""

        elements = [
            _wall("wall_front_1", 0, 0, 20, 0, 0.0, 3.5),
            _wall("wall_back_1", 20, 0, 20, 15, 0.0, 3.5),
            _wall("wall_left_1", 20, 15, 0, 15, 0.0, 3.5),
            _wall("wall_right_1", 0, 15, 0, 0, 0.0, 3.5),
            _wall("wall_front_2", 3, 2, 17, 2, 3.5, 7.0),
            _wall("wall_back_2", 17, 2, 17, 11, 3.5, 7.0),
            _wall("wall_left_2", 17, 11, 3, 11, 3.5, 7.0),
            _wall("wall_right_2", 3, 11, 3, 2, 3.5, 7.0),
            {"type": "roof", "id": "roof_01", "roofType": "flat",
             "span": 21.2, "depth": 16.2, "height": 0.0, "thickness": 0.25,
             "material": "roof", "position": [10.0, 7.0, 7.5]},
        ]
        return {"geometry": {"elements": elements, "components": []}}

    def test_support_bounds_cover_whole_footprint_not_just_top_storey(self):
        """这是事故的直接判据：承托轮廓必须是底层 20×15，不是二层 14×9。"""

        blueprint = self._stepped()
        elements = blueprint["geometry"]["elements"]
        walls = [e for e in elements if e.get("type") == "wall"]
        roof = next(e for e in elements if e.get("type") == "roof")

        bounds = get_roof_support_bounds(walls, roof)

        self.assertAlmostEqual(bounds["span"], 20.0, delta=0.01,
                               msg=f"span 应为底层 20m，实际 {bounds['span']}")
        self.assertAlmostEqual(bounds["depth"], 15.0, delta=0.01,
                               msg=f"depth 应为底层 15m，实际 {bounds['depth']}")
        self.assertAlmostEqual(bounds["center_x"], 10.0, delta=0.01)
        self.assertAlmostEqual(bounds["center_z"], 7.5, delta=0.01)

    def test_fix_leaves_stepped_roof_untouched(self):
        """🔴 事故的原始症状：`fix_roof_coverage` 把整栋屋面"修"小 6m。"""

        blueprint = self._stepped()
        before = dict(next(e for e in blueprint["geometry"]["elements"]
                           if e.get("type") == "roof"))

        output = run_tool(fix_roof_coverage, blueprint)

        after = next(e for e in blueprint["geometry"]["elements"]
                     if e.get("type") == "roof")
        self.assertEqual(before["depth"], after["depth"],
                         f"depth 被改坏：{before['depth']} → {after['depth']}；{output}")
        self.assertEqual(before["span"], after["span"],
                         f"span 被改坏：{before['span']} → {after['span']}")
        self.assertEqual(before["position"], after["position"],
                         f"position 被改坏：{before['position']} → {after['position']}")
        self.assertIn("无需修正", str(output))


class NonSteppedRoofSupportTest(unittest.TestCase):
    """🔴 反向守卫：非退台建筑的行为必须与改动前**完全一致**。

    这组用例是本修改的安全网 —— ``get_roof_support_bounds`` 被 5 处调用，
    对普通建筑误判就会把原本正确的屋面改坏。
    """

    def test_two_storey_same_footprint_is_not_treated_as_stepped(self):
        """上下层同尺寸的两层楼**不是**退台 ⇒ 不能合并成更大轮廓。"""

        elements = [
            _wall("wall_front_1", 0, 0, 14, 0, 0.0, 3.2),
            _wall("wall_back_1", 14, 0, 14, 10, 0.0, 3.2),
            _wall("wall_left_1", 14, 10, 0, 10, 0.0, 3.2),
            _wall("wall_right_1", 0, 10, 0, 0, 0.0, 3.2),
            _wall("wall_front_2", 0, 0, 14, 0, 3.2, 6.4),
            _wall("wall_back_2", 14, 0, 14, 10, 3.2, 6.4),
            _wall("wall_left_2", 14, 10, 0, 10, 3.2, 6.4),
            _wall("wall_right_2", 0, 10, 0, 0, 3.2, 6.4),
            {"type": "roof", "id": "roof_01", "roofType": "flat",
             "span": 15.2, "depth": 11.2, "height": 0.0, "thickness": 0.25,
             "material": "roof", "position": [7.0, 6.4, 5.0]},
        ]
        walls = [e for e in elements if e.get("type") == "wall"]
        roof = elements[-1]

        bounds = get_roof_support_bounds(walls, roof)

        self.assertAlmostEqual(bounds["span"], 14.0, delta=0.01)
        self.assertAlmostEqual(bounds["depth"], 10.0, delta=0.01)
        self.assertAlmostEqual(bounds["support_y"], 6.4, delta=0.01,
                               msg="同尺寸两层楼必须仍按当层标高判")

    def test_single_storey_is_unaffected(self):
        """单层建筑：最常见路径，必须零变化。"""

        elements = [
            _wall("wall_front_1", 0, 0, 12, 0, 0.0, 3.2),
            _wall("wall_back_1", 12, 0, 12, 9, 0.0, 3.2),
            _wall("wall_left_1", 12, 9, 0, 9, 0.0, 3.2),
            _wall("wall_right_1", 0, 9, 0, 0, 0.0, 3.2),
            {"type": "roof", "id": "roof_01", "roofType": "flat",
             "span": 13.2, "depth": 10.2, "height": 0.0, "thickness": 0.25,
             "material": "roof", "position": [6.0, 3.2, 4.5]},
        ]
        walls = [e for e in elements if e.get("type") == "wall"]
        bounds = get_roof_support_bounds(walls, elements[-1])
        self.assertAlmostEqual(bounds["span"], 12.0, delta=0.01)
        self.assertAlmostEqual(bounds["depth"], 9.0, delta=0.01)

    def test_upper_storey_larger_than_lower_is_not_stepped(self):
        """🔴 上层比下层**大**（悬挑）时不能反向合并 —— 只认"更小的那一圈"。

        只做"更大就合并"会在这种房子上把屋面按更大的一层算，凭空缩小。
        """

        elements = [
            _wall("wall_front_1", 3, 3, 12, 3, 0.0, 3.2),
            _wall("wall_back_1", 12, 3, 12, 12, 0.0, 3.2),
            _wall("wall_left_1", 12, 12, 3, 12, 0.0, 3.2),
            _wall("wall_right_1", 3, 12, 3, 3, 0.0, 3.2),
            _wall("wall_front_2", 0, 0, 15, 0, 3.2, 6.4),
            _wall("wall_back_2", 15, 0, 15, 15, 3.2, 6.4),
            _wall("wall_left_2", 15, 15, 0, 15, 3.2, 6.4),
            _wall("wall_right_2", 0, 15, 0, 0, 3.2, 6.4),
            {"type": "roof", "id": "roof_01", "roofType": "flat",
             "span": 16.2, "depth": 16.2, "height": 0.0, "thickness": 0.25,
             "material": "roof", "position": [7.5, 6.4, 7.5]},
        ]
        walls = [e for e in elements if e.get("type") == "wall"]
        bounds = get_roof_support_bounds(walls, elements[-1])
        # 当层是 15×15（更大），不该被拉回下层 9×9
        self.assertAlmostEqual(bounds["span"], 15.0, delta=0.01)
        self.assertAlmostEqual(bounds["depth"], 15.0, delta=0.01)


class SteppedDetectionUnitTest(unittest.TestCase):
    """`_stepped_support_y` 的判据本身：宁可不触发，不可误触发。"""

    def test_returns_none_without_lower_walls(self):
        tops = [(3.2, {"id": "w", "from": [0, 0, 0], "to": [10, 3.2, 0]})]
        self.assertIsNone(_stepped_support_y(tops, 3.2))

    def test_returns_none_when_lower_walls_are_same_size(self):
        wall = {"id": "w", "from": [0, 0, 0], "to": [10, 3.2, 10]}
        tops = [(3.2, wall), (6.4, dict(wall))]
        self.assertIsNone(_stepped_support_y(tops, 6.4))

    def test_returns_lower_y_when_lower_is_strictly_larger(self):
        lower = {"id": "w1", "from": [0, 0, 0], "to": [20, 3.5, 15]}
        upper = {"id": "w2", "from": [3, 3.5, 2], "to": [17, 7.0, 11]}
        self.assertEqual(_stepped_support_y([(3.5, lower), (7.0, upper)], 7.0), 3.5)

    def test_margin_larger_than_noise_does_not_trigger(self):
        """差异只有 0.1m（墙厚/浮点级）⇒ 不算"更小的那一圈"。"""

        lower = {"id": "w1", "from": [0, 0, 0], "to": [20.1, 3.5, 15.1]}
        upper = {"id": "w2", "from": [0.05, 3.5, 0.05], "to": [20.0, 7.0, 15.0]}
        self.assertIsNone(_stepped_support_y([(3.5, lower), (7.0, upper)], 7.0))

    def test_picks_the_closest_lower_yield(self):
        """三层退台（每层都更小）⇒ 取最接近当层的那层，不是最底层。"""

        tops = [
            (3.5, {"id": "w1", "from": [0, 0, 0], "to": [20, 3.5, 15]}),
            (7.0, {"id": "w2", "from": [2, 2, 1.5], "to": [18, 7.0, 13.5]}),
            (10.5, {"id": "w3", "from": [4, 4, 3], "to": [16, 10.5, 12]}),
        ]
        self.assertEqual(_stepped_support_y(tops, 10.5), 7.0)


@unittest.skipUnless(_SESSION.exists(), "真实事故会话不存在")
class RealSessionRegressionTest(unittest.TestCase):
    """用真实出错的那次 session 跑整条链，确保 error 真的消失。"""

    def test_no_approved_design_mutation_after_fix(self):
        """🔴 事故的原始报错：``approved_design_mutation`` 必须没有条目。"""

        payload = json.loads(_SESSION.read_text(encoding="utf-8"))
        turn = payload["turns"][-1]
        document = DesignDocument.model_validate(turn["design_document"])
        compiled = compile_document(document)

        blueprint = json.loads(json.dumps(compiled.blueprint))
        run_tool(fix_roof_coverage, blueprint)

        mutations = approved_compilation_changes(compiled.blueprint, blueprint)
        self.assertEqual(
            mutations, [],
            "已审核实体仍被改动："
            + "; ".join(f"{m['path']} {m.get('before')} → {m.get('after')}"
                        for m in mutations[:5]),
        )

    def test_stepped_roof_survives_the_fix_unchanged(self):
        payload = json.loads(_SESSION.read_text(encoding="utf-8"))
        turn = payload["turns"][-1]
        document = DesignDocument.model_validate(turn["design_document"])
        compiled = compile_document(document)
        blueprint = json.loads(json.dumps(compiled.blueprint))

        roof_before = next(e for e in blueprint["geometry"]["elements"]
                           if e.get("type") == "roof")
        before = dict(roof_before)
        run_tool(fix_roof_coverage, blueprint)
        after = dict(roof_before)

        self.assertEqual(before, after,
                         f"真实会话的屋面被改：{before} → {after}")

    def test_real_session_really_is_a_stepped_building(self):
        """守住前提：这条 session 确实是退台体量（否则上面两条是空转）。"""

        payload = json.loads(_SESSION.read_text(encoding="utf-8"))
        document = DesignDocument.model_validate(payload["turns"][-1]["design_document"])
        self.assertEqual(document.decisions.massing.shape, "stepped")
        widths = sorted(v.width for v in document.decisions.volumes)
        self.assertGreater(widths[-1], widths[0], "两个体量宽度应不同（退台）")


if __name__ == "__main__":
    unittest.main()