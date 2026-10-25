"""离线回归：真实生产函数 + 明确标注的模型回复替身，不访问模型或 RAG。"""
from copy import deepcopy
from pathlib import Path
import asyncio
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
os.chdir(ROOT / "wild-server")
sys.path.insert(0, str(ROOT / "wild-server"))

from config import config
config.rag.auto_sync = False

from app.design.parametric import expand_parameters
from app.agent.plan.construction import expand_implementation
from app.agent.plan.implementation import _item_context, _accept_fragment, _bind_materials, run_marker_generate
from app.agent.plan.workflow import plan_node
from app.agent.plan.contracts import PlanDocument
from app.agent.design_flow.compile import compile_node
from app.agent.generation.architecture.design_workflow import draft_design
from app.design.contracts import DesignDocument
from app.design.compilation import project_drawing
from app.design.coordinates import design_geometry_context
from app.utils.json_extractor import extract_json_object
from app.agent.generation.spatial.geometry import subtract_rectangles
from app.agent.generation.spatial.stair_openings import cut_stair_openings
from app.design.relations import component_geometry_review, place_opening_group
from app.agent.validation.candidate import evaluate_candidate


checks = []


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    checks.append(name)


def rejects(name, operation):
    try:
        operation()
    except ValueError:
        checks.append(name)
    else:
        raise AssertionError("未拒绝：" + name)


def response(value):
    return SimpleNamespace(content=json.dumps(value, ensure_ascii=False), reasoning=None,
                           token_usage=None, finish_reason="stop", call_id="offline-fixture")


def numeric_checks():
    for width in (2.8, 6.3, 11.4):
        for axis in (0, 2):
            source = {"parameters": {"w": width, "n": 7, "step": "=w/(n-1)"},
                      "elements": [{"$repeat": {"count": "=n", "var": "i", "value": {
                          "id": "bar_${i}", "position": ["=-w/2+i*step", 0, 0] if axis == 0 else [0, 0, "=-w/2+i*step"]}}}]}
            before = deepcopy(source)
            result, evidence = expand_parameters(source)
            check(f"repeat_{width}_{axis}", len(result["elements"]) == 7
                  and abs(result["elements"][0]["position"][axis]+width/2) < 1e-9
                  and abs(result["elements"][-1]["position"][axis]-width/2) < 1e-9
                  and len({e["id"] for e in result["elements"]}) == 7)
            check(f"deterministic_{width}_{axis}", expand_parameters(source) == (result, evidence) and source == before)
    nested = {"parameters": {}, "grid": [{"$repeat": {"count": 2, "var": "x", "values": [
        {"$repeat": {"count": 3, "var": "z", "value": {"id": "grid_${x}_${z}"}}}]}}]}
    check("nested_flat_repeat", len(expand_parameters(nested)[0]["grid"]) == 6)
    facts = {"target": {"id": "wall_1", "point": [2, 3, 4], "text": "=do_not_execute"}}
    before = deepcopy(facts)
    result, _ = expand_parameters({"parameters": {}, "copy": "=facts.target", "id": "copy_${facts.target.id}"}, facts=facts)
    result["copy"]["point"][0] = 99
    check("facts_are_read_only_data", facts == before and result["copy"]["text"] == "=do_not_execute"
          and result["id"] == "copy_wall_1")
    for expression in ("__import__('os')", "facts.__class__", "open('secret')", "[i for i in range(10)]",
                       "1/0", "sqrt(-1)", "1e309", "2**10000000", "'x'*1000000", "True+1"):
        rejects("reject_expression_" + expression, lambda e=expression: expand_parameters({"parameters": {}, "x": "="+e}))
    rejects("parameter_cycle", lambda: expand_parameters({"parameters": {"a": "=b", "b": "=a"}}))
    rejects("reserved_parameter", lambda: expand_parameters({"parameters": {"facts": 1}}))
    rejects("oversized_repeat", lambda: expand_parameters({"parameters": {}, "x": [{"$repeat": {"count": 5000, "value": 1}}]}))
    rejects("fractional_repeat", lambda: expand_parameters({"parameters": {}, "x": [{"$repeat": {"count": 2.5, "value": 1}}]}))
    rejects("nested_budget", lambda: expand_parameters({"parameters": {}, "x": [{"$repeat": {"count": 100, "var": "a", "values": [
        {"$repeat": {"count": 100, "var": "b", "value": 1}}]}}]}))
    rejects("broken_outer_json", lambda: extract_json_object('{"parameters":{},"x":4.2+1.2}', outer_only=True, raise_on_error=True))
    check("legacy_json_unchanged", expand_parameters({"label": "=literal", "value": 2}) == ({"label": "=literal", "value": 2}, {}))
    base = {"materials": {"actual_wood": {"color": "#876543"}}}
    row = {"geometry": {"components": [{"material": "structure", "frameMaterial": "structure"}]}}
    bound, bindings = _bind_materials(base, row, {"type": "primitive"}, {"structure": "actual_wood"})
    check("approved_material_role_binding", bound["geometry"]["components"][0]["material"] == "actual_wood"
          and bindings == {"structure": "actual_wood"} and row["geometry"]["components"][0]["material"] == "structure")
    base["materials"]["structure"] = {"color": "#ffffff"}
    bound, _ = _bind_materials(base, row, {"type": "primitive"}, {"structure": "actual_wood"})
    check("explicit_material_id_has_priority", bound["geometry"]["components"][0]["material"] == "structure")
    parts = subtract_rectangles((0, 0, 8, 6), [(2, 2, 4, 4), (3, 3, 5, 5)])
    check("overlapping_void_area", sum((c-a)*(d-b) for a, b, c, d in parts) == 41)
    scene = {"geometry": {"elements": [
        {"id": "slab", "type": "floor", "from": [0, 2.8, 0], "to": [8, 2.8, 6], "thickness": 0.2},
        {"id": "stair", "type": "stair", "from": [3, 0, 1], "to": [3, 3, 4], "width": 1.2}]}}
    check("stair_cut_applied", cut_stair_openings(scene) == ["slab"])
    before = deepcopy(scene)
    check("stair_cut_idempotent", not cut_stair_openings(scene) and scene == before)


def slab_checks():
    for x, z, width, depth in ((0, 0, 8, 6), (13, -7, 6, 8), (-12, 9, 10, 5)):
        design = {"massing": {"shape": "box", "width": width, "depth": depth, "floors": 2,
                              "modeled_floors": 2, "floor_height": 3},
                  "volumes": [{"id": "v", "x": x, "z": z, "width": width, "depth": depth, "start_floor": 1, "end_floor": 2}],
                  "floor_layouts": [{"floor": 1, "level": 0.4}, {"floor": 2, "level": 3.7,
                     "rooms": [{"id": "void", "void": True, "bounds": {"x": x+1, "z": z+1, "width": 2, "depth": 2}}]}]}
        geo = design_geometry_context(design)
        context = {"levels": geo["levels"], "volume_geometry": geo["volumes"], "diagram_hosts": []}
        marker = {"id": "building_body", "type": "building_body", "design": design}
        row = {"id": "building_body", "parameters": {}, "slabs": [{"id": "upper", "volume": "v", "floor": 2,
                "thickness": 0.17, "material": "stone"}]}
        result, _ = expand_implementation(row, marker, context)
        floors = result["geometry"]["elements"]
        area = sum((f["to"][0]-f["from"][0])*(f["to"][2]-f["from"][2]) for f in floors)
        check(f"slab_top_void_translation_{x}_{z}", abs(area-(width*depth-4)) < 1e-9
              and all(abs(f["from"][1]+f["thickness"]-3.7) < 1e-9 for f in floors))
        invalid = deepcopy(row)
        invalid["slabs"][0]["floor"] = 3
        rejects(f"unknown_floor_{x}_{z}", lambda: expand_implementation(invalid, marker, context))


async def pipeline_checks():
    saved = json.loads((ROOT / "docs/10月19日优化/执行证据/真实生成-03-流程验证/state.json").read_text(encoding="utf-8"))
    document = DesignDocument.model_validate(saved["design_document"])
    resolved = project_drawing(document)
    state = {"design_document": document.model_dump(mode="json"), "resolved_design": resolved.model_dump(mode="json"),
             "component_fragments": {}, "component_diagnostics": {}, "thinking_mode": False,
             "session_id": "oct24-offline", "user_message": "离线装配回归"}
    state.update(await plan_node(state))
    plan = PlanDocument.model_validate(state["plan"])
    originals = {r_id: (diag, record) for diag in saved["component_diagnostics"].values()
                 for r_id, record in diag["implementations"].items()}
    old_entities = {e["id"]: e for entities in saved["component_fragments"].values() for e in entities}
    body = {"id": "building_body", "parameters": {"t": 0.15},
            "walls": [{"$repeat": {"items": "=facts.diagram_hosts", "var": "wall", "value": {
                "host": "=wall.id", "thickness": 0.2, "material": "wall_finish"}}}],
            "slabs": [{"$repeat": {"items": "=facts.levels", "var": "level", "values": [
                {"$repeat": {"items": "=level.volume_ids", "var": "volume", "value": {
                    "id": "body_slab_${volume}_${level.index}", "volume": "=volume", "floor": "=level.index",
                    "thickness": "=t", "material": "floor_finish"}}}]}}]}
    replies = 0

    async def invoke(_llm, messages, **kwargs):
        nonlocal replies
        replies += 1
        context = json.loads(messages[-1]["content"])
        rows = []
        for marker in context["markers"]:
            mid = marker["id"]
            if mid == "building_body":
                rows.append(deepcopy(body))
                continue
            diag, record = originals[mid]
            ids = record["entity_ids"]
            rows.append({"id": mid, "parameters": {},
                         "geometry": {bucket: [deepcopy(old_entities[i]) for i in ids if i in diag.get(bucket, [])]
                                      for bucket in ("elements", "components")},
                         "materials": diag.get("materials", {}), "assets": diag.get("assets", {})})
        return response({"implementations": rows})

    with patch("app.llm.client.create_llm", return_value=None), patch("app.llm.invocation.invoke_llm", side_effect=invoke), \
            patch("app.agent.plan.knowledge_tool.search_knowledge_result", return_value={"text": "offline fixture", "has_shape_reference": True}):
        for item in plan.items:
            updates, status, _, summary, _ = await run_marker_generate(state, item)
            check("production_marker_" + item.id + "_" + summary, status == "succeeded")
            for key in ("component_fragments", "component_diagnostics"):
                state[key].update(updates.get(key, {}))
        # 如装配意外要求模型修复，替身将报错，不能用额外模型调用掩盖失败。
        compiled = await compile_node(state)
    check("production_compile_complete", compiled["status"] == "complete" and compiled["compile_report"]["design_complete"])
    check("one_reply_per_item", replies == len(plan.items))
    records = [r for d in state["component_diagnostics"].values() for r in d["implementations"].values()]
    check("accepted_fingerprints", all(r.get("entity_fingerprint") and r["status"] == "implemented" for r in records))
    body_diag = next(d for d in state["component_diagnostics"].values() if "building_body" in d["implementations"])
    evidence = next(t["construction"]["building_body"] for t in body_diag["trace"] if t.get("construction"))
    check("construction_trace", evidence["repeated_items"] == 6 and len(evidence["constructed"]) == 5)
    (HERE / "offline.wild").write_text(json.dumps(compiled["merged_blueprint"], ensure_ascii=False, indent=2), encoding="utf-8")
    (HERE / "offline-pipeline.json").write_text(json.dumps({"model_replies": "fixtures", "paid_calls": 0,
        "compile_report": compiled["compile_report"], "construction": evidence}, ensure_ascii=False, indent=2), encoding="utf-8")

    # 使用真实片段验收确认参数化入口不能绕过尺寸/宿主约束。
    marker = resolved.component_markers[0]
    ctx = _item_context(state, {marker["id"]: marker}, state["skeleton_blueprint"])
    bad = deepcopy(body)
    bad["walls"] = [{"host": "missing_host", "thickness": 0.2, "material": "wall_finish"}]
    rejects("invalid_host", lambda: expand_implementation(bad, marker, ctx))
    duplicate = deepcopy(body)
    duplicate["walls"] = [{"host": ctx["diagram_hosts"][0]["id"], "thickness": 0.2, "material": "wall_finish"}]*2
    rejects("duplicate_constructed_id", lambda: expand_implementation(duplicate, marker, ctx))
    duplicate = deepcopy(body)
    duplicate["slabs"] = [{"id": "one", "volume": "main_vol", "floor": 1, "thickness": 0.15, "material": "floor_finish"},
                           {"id": "two", "volume": "main_vol", "floor": 1, "thickness": 0.15, "material": "floor_finish"}]
    rejects("duplicate_slab", lambda: expand_implementation(duplicate, marker, ctx))
    native_marker = {"id": "screen", "type": "primitive", "host": "", "design": {
        "size": {"width": 2, "height": 1, "depth": 0.2}, "placement": {"position": [0, 0.5, 0]}}}
    wrong_size, _ = expand_implementation({"id": "screen", "parameters": {"w": 3}, "geometry": {
        "elements": [{"id": "screen_part", "type": "primitive", "shape": "box", "position": [0, 0.5, 0],
                      "dimensions": ["=w", 1, 0.2], "material": "wall_finish"}], "components": []}}, native_marker, {})
    _, _, rejected, _ = _accept_fragment(state["skeleton_blueprint"], wrong_size, native_marker)
    check("expanded_geometry_cannot_bypass_size", rejected is not None)

    fresh = {**state, "component_fragments": {}, "component_diagnostics": {}}
    attempts = []
    async def repair_reply(_llm, messages, **kwargs):
        context = json.loads(messages[-1]["content"])
        attempts.append(context)
        source = deepcopy(body)
        if len(attempts) == 1:
            source["parameters"]["t"] = -0.15
        return response({"implementations": [source]})
    with patch("app.llm.client.create_llm", return_value=None), patch("app.llm.invocation.invoke_llm", side_effect=repair_reply), \
            patch("app.agent.plan.knowledge_tool.search_knowledge_result", return_value={"text": "offline fixture", "has_shape_reference": True}):
        updates, status, _, _, _ = await run_marker_generate(fresh, plan.items[0])
    check("constructor_failure_local_repair", status == "succeeded" and len(attempts) == 2
          and attempts[1]["failed_implementations"]["building_body"]["parameters"]["t"] == -0.15
          and "thickness" in attempts[1]["validation_feedback"]["building_body"])

    # 设计端必须返回展开后的图纸；修订仍经过路径权限检查。
    raw = deepcopy(saved["architecture_plan"])
    raw["parameters"] = {"width": 6}
    raw["massing"]["width"] = "=width"
    raw["volumes"][0]["width"] = "=width"
    def validate(value):
        check("design_expanded_before_validate", value["massing"]["width"] == 6 and "parameters" not in value)
    async def design_reply(*args, **kwargs):
        return response(raw)
    with patch("app.agent.generation.architecture.design_workflow.create_llm", return_value=None), \
            patch("app.agent.generation.architecture.design_workflow.invoke_llm", side_effect=design_reply):
        plan_result, diag = await draft_design(base_prompt="fixture", user_request="fixture", validate=validate)
    check("design_returns_expanded_data", plan_result["massing"]["width"] == 6 and len(diag["parameter_expansions"]) == 1)
    revision_calls = 0
    async def revision_reply(*args, **kwargs):
        nonlocal revision_calls
        revision_calls += 1
        if revision_calls == 1:
            candidate = deepcopy(raw)
            candidate["parameters"]["width"] = 7
            candidate["volumes"][0]["width"] = 6
            return response(candidate)
        return response({"parameters": {}, "operations": [{"op": "replace", "path": "/massing/width",
                            "value": "=facts.current_design.volumes[0].width"}]})
    def require_width(value):
        if value["massing"]["width"] != 6:
            raise ValueError("/massing/width：本例范围必须保持 6")
    with patch("app.agent.generation.architecture.design_workflow.create_llm", return_value=None), \
            patch("app.agent.generation.architecture.design_workflow.invoke_llm", side_effect=revision_reply):
        revised, diag = await draft_design(base_prompt="fixture", user_request="fixture", validate=require_width)
    check("parametric_design_patch", revised["massing"]["width"] == 6 and revision_calls == 2
          and revised["concept"] == raw["concept"] and diag["repairs"][0]["validated"])


async def main():
    numeric_checks()
    slab_checks()
    await pipeline_checks()
    live = HERE / "parametric_smoke_20261024_092741"
    if (live / "state.json").exists():
        saved = json.loads((live / "state.json").read_text(encoding="utf-8"))
        blueprint = saved["final_blueprint"]
        entities = {e["id"]: e for bucket in ("elements", "components") for e in blueprint["geometry"][bucket]}
        records = {mid: record for diag in saved["component_diagnostics"].values() for mid, record in diag["implementations"].items()}
        markers = {m["id"]: m for m in saved["resolved_design"]["component_markers"]}
        for mid, record in records.items():
            review = component_geometry_review(blueprint, [entities[i] for i in record["entity_ids"]], markers[mid])
            check("saved_model_geometry_" + mid, not review["errors"])
        # 用真实产物删去本就由图纸确定的字段，验证程序补齐后仍通过同一片段验收。
        for mid, marker in markers.items():
            owned = records[mid]["entity_ids"]
            if len(owned) != 1:
                continue
            original = entities[owned[0]]
            kind = original["type"]
            omitted = ({"parentWall", "from"} | (set(marker["design"].get("size", {})) & {"width", "height"})
                       if kind in {"door", "window"} else
                       {"span", "depth", "position", "roofType", "ridgeAxis"} if kind == "roof" else
                       {"dimensions", "position"} if kind == "primitive" and original.get("shape") == "box" and marker["type"] == "primitive" else set())
            if not omitted:
                continue
            base = deepcopy(blueprint)
            bucket = next(k for k in ("elements", "components") if original in base["geometry"][k])
            base["geometry"][bucket] = [e for e in base["geometry"][bucket] if e["id"] not in owned]
            source = {"id": mid, "geometry": {bucket: [{k: v for k, v in original.items() if k not in omitted}]}}
            context = _item_context(saved, {mid: marker}, base)
            completed, evidence = expand_implementation(source, marker, context)
            completed, _ = place_opening_group(base, completed, marker)
            _, _, rejected, _ = _accept_fragment(base, completed, marker)
            check("native_completion_" + mid, rejected is None and bool(evidence.get("completed_fields")))
            check("native_preserves_design_" + mid, completed["geometry"][bucket][0] == original)
            check("native_no_input_mutation_" + mid, not (omitted & source["geometry"][bucket][0].keys()))
            if kind == "primitive":
                rotated = deepcopy(source)
                rotated["geometry"][bucket][0]["rotation"] = [0, 0.5, 0]
                result, _ = expand_implementation(rotated, marker, context)
                check("native_rotation_keeps_local_geometry_" + mid, "dimensions" not in result["geometry"][bucket][0])
                grouped = deepcopy(source)
                grouped["geometry"][bucket].append({"id": mid+"_part", "type": "primitive", "shape": "box"})
                result, _ = expand_implementation(grouped, marker, context)
                check("native_group_keeps_relative_geometry_" + mid, "dimensions" not in result["geometry"][bucket][0])
                curved_marker = deepcopy(marker)
                curved_marker["design"]["form"]["shape"] = "cylinder"
                result, _ = expand_implementation(source, curved_marker, context)
                check("native_keeps_explicit_shape_" + mid, "dimensions" not in result["geometry"][bucket][0])
        evaluation = evaluate_candidate(blueprint, design_document=saved["design_document"],
                                        design_brief=saved["design_brief"], source="oct24_final_code_replay")
        check("saved_model_final_validation", not evaluation["errors"])
        (live / "validation-latest.json").write_text(json.dumps({"ok": not evaluation["errors"],
            "snapshot": evaluation["snapshot"]}, ensure_ascii=False, indent=2), encoding="utf-8")
        # 回放真实失败回复，验证角色解析实际解决引用错误，无新增模型请求。
        diag = next(d for d in saved["component_diagnostics"].values() if "cornice_long" in d["implementations"])
        attempt = next(t for t in diag["trace"] if t.get("stage") == "generate")
        row = extract_json_object(attempt["output"], outer_only=True, raise_on_error=True)["implementations"][0]
        base = deepcopy(blueprint)
        owned = set(records["cornice_long"]["entity_ids"])
        for bucket in ("elements", "components"):
            base["geometry"][bucket] = [e for e in base["geometry"][bucket] if e["id"] not in owned]
        ctx = _item_context(saved, {"cornice_long": markers["cornice_long"]}, base)
        row, _ = expand_implementation(row, markers["cornice_long"], ctx)
        row, bindings = _bind_materials(base, row, markers["cornice_long"], ctx["material_roles"])
        _, _, rejected, _ = _accept_fragment(base, row, markers["cornice_long"])
        check("saved_material_failure_resolved", rejected is None and "structure" in bindings)
    report = {"ok": True, "count": len(checks), "checks": checks, "model_calls": 0,
              "scope": "生产函数离线回归，模型与检索使用明确替身；不证明真实模型效果"}
    (HERE / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "checks": len(checks), "model_calls": 0}))


if __name__ == "__main__":
    asyncio.run(main())
