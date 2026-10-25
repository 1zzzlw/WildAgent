"""真实失败片段和参数化反例；仅离线调用生产函数，不访问模型或 RAG。"""
from copy import deepcopy
import json
from math import cos
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "最新两次生成诊断"
os.chdir(ROOT / "wild-server")
sys.path.insert(0, str(ROOT / "wild-server"))
from config import config
config.rag.auto_sync = False
from app.agent.plan.construction import expand_implementation
from app.agent.plan.implementation import _accept_group, _accept_fragment, _bind_materials
from app.design.parametric import expand_parameters
from app.design.relations import component_geometry_review, roof_design_errors
from app.utils.json_extractor import extract_json_object

STATES, TRACES = {}, {}
for sid in ("session_1792828902444", "session_1792838578836"):
    STATES[sid] = json.loads((SOURCE / sid / "state.json").read_text(encoding="utf-8"))
    TRACES[sid] = json.loads(next((ROOT / "wild-server/storage/sessions/rag_traces" / sid).glob("*.json")).read_text(encoding="utf-8"))


def recorded(group, stage="generate", sid="session_1792838578836"):
    attempt = next(t for t in STATES[sid]["component_diagnostics"][group]["trace"] if t.get("stage") == stage)
    trace = TRACES[sid]
    call = next(c for c in trace["llm_calls"] if c["call_id"] == attempt["call_id"])
    context = json.loads(trace["llm_inputs"][call["messages_ref"]]["messages"][-1]["content"])
    rows = extract_json_object(attempt["output"], outer_only=True)["implementations"]
    markers = {m["id"]: m for m in STATES[sid]["resolved_design"]["component_markers"]}
    return rows, markers, context


def expand_bind(row, marker, context):
    expanded, evidence = expand_implementation(row, marker, context)
    expanded, _ = _bind_materials(context["existing_blueprint"], expanded, marker, context["material_roles"])
    return expanded, evidence


class ExecutionContractTests(unittest.TestCase):
    def test_actual_light_materials_and_wrong_material(self):
        rows, markers, context = recorded("generate_8", sid="session_1792828902444")
        for row in rows:
            with self.subTest(id=row["id"]):
                marker = markers[row["id"]]
                expanded, _ = expand_bind(row, marker, context)
                _accept_group(context["existing_blueprint"], expanded, marker)
                wrong = deepcopy(expanded)
                wrong["materials"]["wrong"] = {**context["existing_blueprint"]["materials"][marker["material_id"]],
                                               "baseColor": [1, 0, 1]}
                for part in wrong["geometry"]["components"][0]["body"]:
                    part["material"] = "wrong"
                with self.assertRaisesRegex(ValueError, "材质角色"):
                    _accept_group(context["existing_blueprint"], wrong, marker)
                wrong["geometry"]["components"][0]["material"] = marker["material_id"]
                with self.assertRaisesRegex(ValueError, "材质角色"):
                    _accept_group(context["existing_blueprint"], wrong, marker)
                for part in wrong["geometry"]["components"][0]["body"]:
                    part.pop("material")
                _accept_group(context["existing_blueprint"], wrong, marker)

    def test_actual_sofa_drift_rejected(self):
        rows, markers, context = recorded("generate_10")
        row = rows[0]
        expanded, _ = expand_bind(row, markers[row["id"]], context)
        with self.assertRaisesRegex(ValueError, "position|位置|中心"):
            _accept_group(context["existing_blueprint"], expanded, markers[row["id"]])
        _, _, rejected, record = _accept_fragment(context["existing_blueprint"], expanded, markers[row["id"]])
        self.assertIsNotNone(rejected)
        self.assertIsNone(record)

    def test_furniture_completion_and_dimensions(self):
        rows, markers, context = recorded("generate_10")
        source = rows[0]
        for x, y, z, height in ((15, .425, 8, .85), (-8, 4.5, 21, 1), (32, 7.3, -4, .6)):
            for angle in (0, .7, -1.2):
                with self.subTest(position=(x, y, z), angle=angle):
                    marker, row = deepcopy(markers[source["id"]]), deepcopy(source)
                    marker["design"]["placement"]["position"] = [x, y, z]
                    marker["entity"]["position"] = [x, y, z]
                    marker["design"]["size"]["height"] = height
                    entity = row["geometry"]["elements"][0]
                    entity.pop("position")
                    entity.pop("dimensions")
                    entity["rotation"] = [0, angle, 0]
                    original = deepcopy(row)
                    expanded, evidence = expand_bind(row, marker, context)
                    self.assertEqual(row, original)
                    actual = expanded["geometry"]["elements"][0]
                    self.assertEqual(actual["position"], [x, y-height/2, z])
                    self.assertEqual(actual["dimensions"]["height"], height)
                    candidate, entities, record = _accept_group(context["existing_blueprint"], expanded, marker)
                    self.assertIn("placement.position", record["geometry_review"]["checked"])
                    self.assertTrue(evidence["completed_fields"])
                    bad = deepcopy(expanded)
                    bad["geometry"]["elements"][0]["dimensions"]["width"] += .3
                    with self.assertRaisesRegex(ValueError, "width"):
                        _accept_group(context["existing_blueprint"], bad, marker)

    def test_actual_kitchen_shape_feedback(self):
        rows, markers, context = recorded("generate_14")
        for row in rows:
            with self.subTest(id=row["id"]):
                with self.assertRaisesRegex(ValueError, r"/geometry/elements/\d+.*values"):
                    expand_implementation(row, markers[row["id"]], context)

    def test_numeric_array_repeat_is_still_valid(self):
        payload = {"parameters": {}, "points": [{"$repeat": {"count": 3, "value": ["=i", 0, 0]}}]}
        result, _ = expand_parameters(payload)
        self.assertEqual(result["points"], [[0, 0, 0], [1, 0, 0], [2, 0, 0]])

    def test_parameter_feedback_and_safe_contract(self):
        for expression, expected in (("=facts.wall.from[0]", r'\["from"\]'),
                                     ("=i == 0 ? -1 : 1", "items"),
                                     ("=facts.marker.size.width", "design.size")):
            with self.subTest(expression=expression):
                with self.assertRaisesRegex(ValueError, expected):
                    expand_parameters({"parameters": {"i": 0}, "x": expression},
                                      facts={"wall": {"from": [4, 0, 0]}, "marker": {"design": {"size": {"width": 2}}}})
        for expression in ('=__import__("os")', '=facts.__class__', '=[x for x in [1]]'):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                expand_parameters({"parameters": {}, "x": expression})

    def test_known_buckets_are_normalized_without_dropping_entities(self):
        rows, markers, context = recorded("generate_10")
        row = deepcopy(rows[0])
        entity = row["geometry"]["elements"].pop()
        entity.pop("position")
        row["geometry"]["components"].append(entity)
        expanded, evidence = expand_bind(row, markers[row["id"]], context)
        self.assertEqual(len(expanded["geometry"]["elements"]), 1)
        self.assertEqual(expanded["geometry"]["components"], [])
        self.assertTrue(evidence["format_changes"])
        _accept_group(context["existing_blueprint"], expanded, markers[row["id"]])

    def test_misplaced_output_is_not_reported_empty(self):
        row = {"id": "light", "geometry": {"elements": [], "components": []}, "entities": [{"id": "light", "type": "light"}]}
        with self.assertRaisesRegex(ValueError, "/entities.*geometry"):
            expand_implementation(row, {"id": "light", "type": "light", "design": {}}, {})

    def test_recorded_roof_projection_alignment(self):
        rows, markers, context = recorded("generate_5", "repair_2")
        row, marker = rows[0], markers[rows[0]["id"]]
        expanded, evidence = expand_bind(row, marker, context)
        with self.assertRaisesRegex(ValueError, "封闭支承"):
            _accept_group(context["existing_blueprint"], expanded, marker)
        gaps = roof_design_errors(context["existing_blueprint"], expanded["geometry"]["elements"], marker)
        self.assertNotIn("wall_main_left_L1", " ".join(gaps))
        self.assertIn("wall_garage_wing_left_L1", " ".join(gaps))
        # 无墙时只验证投影；不能据此声称建筑已有支承。
        self.assertFalse(roof_design_errors({"geometry": {"elements": []}}, expanded["geometry"]["elements"], marker))
        self.assertTrue(evidence["placement_changes"])
        rerun, second = expand_implementation(expanded, marker, context)
        self.assertEqual(rerun, expanded)
        self.assertFalse(second.get("placement_changes"))

    def test_roof_axes_sizes_and_conflicts(self):
        rows, markers, context = recorded("generate_5", "repair_2")
        for axis in (0, 2):
            for angle in (-.38, .21):
                for x, z, width, depth, thickness, overhang in ((0, 0, 7, 6, .12, .4), (-13, 19, 9, 4, .25, .8)):
                    with self.subTest(axis=axis, angle=angle, width=width):
                        marker = deepcopy(markers[rows[0]["id"]])
                        marker["design"]["volume"].update(x=x, z=z, width=width, depth=depth)
                        marker["design"]["overhang"] = overhang
                        marker["design"]["ridge_axis"] = "x" if axis == 0 else "z"
                        marker["entity"]["position"] = [x+width/2, 3.6, z+depth/2]
                        dims = [(width+2*overhang)/(cos(angle) if axis == 2 else 1), thickness,
                                (depth+2*overhang)/(cos(angle) if axis == 0 else 1)]
                        rotation = [angle if axis == 0 else 0, 0, angle if axis == 2 else 0]
                        roof = {"id": "test_roof", "type": "primitive", "shape": "box", "dimensions": dims,
                                "rotation": rotation, "position": [x+width/2, 6, z+depth/2], "material": "roof"}
                        row = {"geometry": {"elements": [roof], "components": []}}
                        expanded, evidence = expand_implementation(row, marker, context)
                        self.assertTrue(evidence["placement_changes"])
                        self.assertEqual(expanded["geometry"]["elements"][0]["position"][1], 6)
                        self.assertFalse(roof_design_errors({"geometry": {"elements": []}}, expanded["geometry"]["elements"], marker))
                        roof["dimensions"][0] *= .5
                        short, evidence = expand_implementation(row, marker, context)
                        self.assertFalse(evidence.get("placement_changes"))
                        self.assertTrue(roof_design_errors(context["existing_blueprint"], short["geometry"]["elements"], marker))

    def test_roof_alignment_does_not_mask_support_or_design_conflicts(self):
        rows, markers, context = recorded("generate_5", "repair_2")
        marker = markers[rows[0]["id"]]
        expanded, _ = expand_bind(rows[0], marker, context)
        roof = expanded["geometry"]["elements"][0]
        roof["position"][1] = 0
        low, _ = expand_implementation(expanded, marker, context)
        with self.assertRaisesRegex(ValueError, "承托标高"):
            _accept_group(context["existing_blueprint"], low, marker)
        explicit = deepcopy(marker)
        explicit["design"]["placement"] = {"position": [12, 5, 8]}
        _, evidence = expand_implementation(rows[0], explicit, context)
        self.assertFalse(evidence.get("placement_changes"))
        expanded["geometry"]["elements"].append({**deepcopy(roof), "id": "other_panel"})
        _, evidence = expand_implementation(expanded, marker, context)
        self.assertFalse(evidence.get("placement_changes"))

    def test_tilted_furniture_does_not_use_vertical_anchor_formula(self):
        rows, markers, context = recorded("generate_10")
        row, marker = deepcopy(rows[0]), markers[rows[0]["id"]]
        entity = row["geometry"]["elements"][0]
        entity["rotation"] = [.3, 0, 0]
        entity.pop("position")
        expanded, _ = expand_implementation(row, marker, context)
        self.assertNotIn("position", expanded["geometry"]["elements"][0])
        review = component_geometry_review(context["existing_blueprint"], expanded["geometry"]["elements"], marker)
        self.assertEqual(review["status"], "needs_review")
        self.assertNotIn("placement.position", review["checked"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
