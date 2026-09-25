"""楼梯通道的几何回归；纯标准库测试可独立运行，无需模型或网络。"""

from copy import deepcopy
import unittest

from app.agent.generation.stair_openings import cut_stair_openings, stair_opening_issues


def floor(identifier, y):
    return {"id": identifier, "type": "floor", "from": [0, y, 0], "to": [10, y, 10],
            "thickness": 0.2, "material": "concrete"}


def blueprint(stairs, floors):
    return {"geometry": {"elements": floors + stairs}}


def area(elements, y):
    return sum(abs((f["to"][0] - f["from"][0]) * (f["to"][2] - f["from"][2]))
               for f in elements if f["type"] == "floor" and f["from"][1] == y)


class StairOpeningTests(unittest.TestCase):
    def test_both_axes_directions_widths_and_heights(self):
        for axis in (0, 2):
            for reverse in (False, True):
                for width, height in ((1.2, 3.0), (1.8, 4.2)):
                    with self.subTest(axis=axis, reverse=reverse, width=width, height=height):
                        start, end = [5, 0, 5], [5, height, 5]
                        start[axis], end[axis] = (8, 2) if reverse else (2, 8)
                        stair = {"type": "stair", "id": "s", "from": start, "to": end, "width": width}
                        bp = blueprint([stair], [floor("ground", 0), floor("upper", height), floor("roof", height * 2)])
                        self.assertTrue(stair_opening_issues(bp))
                        self.assertEqual(cut_stair_openings(bp), ["upper"])
                        self.assertFalse(stair_opening_issues(bp))
                        elements = bp["geometry"]["elements"]
                        self.assertAlmostEqual(area(elements, height), 100 - 6 * width)
                        self.assertEqual(area(elements, 0), 100)
                        self.assertEqual(area(elements, height * 2), 100)
                        # 上端向外 0.5m 的平台必须还在。
                        landing = list(end)
                        landing[axis] += -0.5 if reverse else 0.5
                        self.assertTrue(any(f["type"] == "floor" and f["from"][1] == height
                                            and f["from"][0] <= landing[0] <= f["to"][0]
                                            and f["from"][2] <= landing[2] <= f["to"][2] for f in elements))
                        snapshot = deepcopy(bp)
                        self.assertEqual(cut_stair_openings(bp), [])
                        self.assertEqual(bp, snapshot)

    def test_multiple_flights_and_existing_split_slabs(self):
        stairs = [{"id": f"s{i}", "type": "stair", "from": [5, i * 3, 2 if i % 2 == 0 else 8],
                   "to": [5, (i + 1) * 3, 8 if i % 2 == 0 else 2], "width": 2} for i in range(3)]
        bp = blueprint(stairs, [floor(f"f{i}", i * 3) for i in range(4)])
        cut_stair_openings(bp)
        self.assertFalse(stair_opening_issues(bp))
        for y in (3, 6, 9):
            self.assertEqual(area(bp["geometry"]["elements"], y), 88)
        ids = [e["id"] for e in bp["geometry"]["elements"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_overlapping_stairs_do_not_double_subtract(self):
        stairs = [{"id": f"s{x}", "type": "stair", "from": [x, 0, 2],
                   "to": [x, 3, 8], "width": 2} for x in (4, 5)]
        bp = blueprint(stairs, [floor("f", 3)])
        cut_stair_openings(bp)
        self.assertAlmostEqual(area(bp["geometry"]["elements"], 3), 82)
        self.assertFalse(stair_opening_issues(bp))

    def test_translated_template_instances(self):
        stair = {"id": "s", "type": "stair", "from": [5, 0, 2], "to": [5, 3, 8], "width": 2}
        bp = {"geometry": {"elements": [], "templates": {"plate": floor("plate", 0), "flight": stair},
                           "instances": [{"id": "upper", "ref": "plate", "position": [10, 3, 20]},
                                         {"id": "stair", "ref": "flight", "position": [10, 0, 20]}]}}
        original_templates = deepcopy(bp["geometry"]["templates"])
        self.assertTrue(stair_opening_issues(bp))
        self.assertEqual(cut_stair_openings(bp), ["upper"])
        self.assertFalse(stair_opening_issues(bp))
        self.assertEqual(bp["geometry"]["templates"], original_templates)
        self.assertEqual(area(bp["geometry"]["elements"], 3), 88)
        self.assertEqual(len(bp["geometry"]["instances"]), 1)

    def test_no_stair_or_nonintersecting_stair_keeps_slabs(self):
        for stairs in ([], [{"id": "s", "type": "stair", "from": [20, 0, 2], "to": [20, 3, 8], "width": 2}]):
            bp = blueprint(stairs, [floor("f", 3)])
            original = deepcopy(bp)
            self.assertEqual(cut_stair_openings(bp), [])
            self.assertEqual(bp, original)

    def test_opening_across_two_slabs_preserves_total_area_and_properties(self):
        left, right = floor("left", 3), floor("right", 3)
        left["to"][0], right["from"][0] = 5, 5
        ground = floor("ground", 0)
        ground["thickness"] = 0.5
        stair = {"id": "s", "type": "stair", "from": [5, 0, 2], "to": [5, 3, 8], "width": 2}
        bp = blueprint([stair], [ground, left, right])
        self.assertEqual(cut_stair_openings(bp), ["left", "right"])
        self.assertEqual(area(bp["geometry"]["elements"], 3), 88)
        self.assertEqual(area(bp["geometry"]["elements"], 0), 100)
        for element in bp["geometry"]["elements"]:
            if element["type"] == "floor" and element["from"][1] == 3:
                self.assertEqual(element["thickness"], 0.2)
                self.assertEqual(element["material"], "concrete")
        self.assertFalse(stair_opening_issues(bp))


if __name__ == "__main__":
    unittest.main()
