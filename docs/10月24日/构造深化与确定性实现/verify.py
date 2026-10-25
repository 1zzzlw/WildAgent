"""构造系统回归：生产展开/验收/装配，模型与检索替身明确标记。"""
import asyncio
from copy import deepcopy
from math import cos, sin, hypot
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
os.chdir(ROOT / "wild-server")
sys.path.insert(0, str(ROOT / "wild-server"))
from config import config
config.rag.auto_sync = False
from app.design.construction_systems import construct_system, construction_spec, construction_review, validate_construction
from app.design.contracts import DesignDocument
from app.design.compilation import project_drawing
from app.agent.plan.implementation import _accept_group, run_marker_generate
from app.agent.plan.workflow import plan_node
from app.agent.plan.contracts import PlanDocument
from app.agent.design_flow.compile import compile_node
from app.agent.generation.architecture.design_workflow import draft_design, refine_construction

checks = []


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    checks.append(name)


def rejects(name, function):
    try:
        function()
    except ValueError:
        checks.append(name)
    else:
        raise AssertionError("没有拒绝："+name)


def opening_spec(kind):
    spec = {"system": "framed_opening", "frameWidth": 0.06, "frameDepth": 0.14, "frameMaterial": "frame",
            "surround": {"width": 0.08, "depth": 0.06, "embed": 0.015, "material": "facade_primary"}}
    if kind == "window":
        spec.update(glassDepth=0.02, glassMaterial="glass", verticalMullions=2, horizontalMullions=1, mullionWidth=0.035)
    else:
        spec.update(system="entrance", leafDepth=0.04, leafMaterial="door", interaction={"mode": "swing", "hingeSide": "left", "openAngle": 90}, canopy={"width": 2.0, "depth": 1.4,
            "thickness": 0.18, "clearance": 0.35, "material": "structure",
            "soffit": {"thickness": 0.06, "embed": 0.015, "material": "accent"}, "posts": {"width": 0.12, "baseY": 0, "material": "accent"}})
    return spec


def band_spec(axis="x"):
    return {"system": "layered_band", "axis": axis, "layers": [
        {"fraction": 0.25, "depth_ratio": 0.65, "material": "facade_primary"},
        {"fraction": 0.5, "depth_ratio": 0.8, "material": "accent"},
        {"fraction": 0.25, "depth_ratio": 1, "material": "structure"}]}


saved = json.loads((ROOT / "docs/10月19日优化/执行证据/真实生成-03-流程验证/state.json").read_text(encoding="utf-8"))
source_document = deepcopy(saved["design_document"])
roles = {r["role"]: r["materialId"] for r in source_document["decisions"]["materials"]["resolved_plan"]["roles"]}
base_materials = saved["skeleton_blueprint"]["materials"]


def geometry_checks():
    for x, z, width, depth, angle in ((0, 0, 6, 6, 0), (13, -7, 9, 5, 0), (-12, 8, 5, 9, 0), (4, 18, 8, 6, 0.37)):
        corners = [(x+u*cos(angle)-v*sin(angle), z+u*sin(angle)+v*cos(angle))
                   for u, v in ((0, 0), (width, 0), (width, depth), (0, depth))]
        walls = [{"id": f"wall_{i}", "type": "wall", "from": [*a[:1], 0, a[1]],
                  "to": [b[0], 3.6, b[1]], "thickness": 0.2, "material": "wall_finish"}
                 for i, (a, b) in enumerate(zip(corners, corners[1:]+corners[:1]))]
        base = {"meta": {"version": "1.1"}, "materials": deepcopy(base_materials), "assets": {},
                "geometry": {"elements": walls, "components": []}}
        for wall in walls:
            for kind in ("window", "door"):
                length = hypot(wall["to"][0]-wall["from"][0], wall["to"][2]-wall["from"][2])
                marker = {"id": kind+wall["id"], "type": kind, "host": wall["id"], "construction_materials": roles,
                          "diagram_host": deepcopy(wall), "entity": {"parentWall": wall["id"], "from": [(length-1.2)/2, 1 if kind == "window" else 0, 0]},
                          "design": {"type": kind, "size": {"width": 1.2, "height": 1.5 if kind == "window" else 2.4},
                                     "placement": {"face": "front"}, "form": {"construction": opening_spec(kind)}}}
                original = deepcopy(marker)
                row = construct_system(marker, base)
                candidate, entities, _ = _accept_group(base, row, marker)
                check(f"accepted_{x}_{z}_{kind}_{wall['id']}", not construction_review(candidate, entities, marker)["errors"] and marker == original)
                changed = deepcopy(entities)
                changed.pop()
                check(f"missing_member_{x}_{z}_{kind}_{wall['id']}", bool(construction_review(candidate, changed, marker)["errors"]))
                # 共墙合并后真实墙可能反向；装饰与洞口必须仍安装在同一世界位置。
                reversed_marker = deepcopy(marker)
                reversed_marker["diagram_host"]["id"] = "diagram_shared"
                reversed_marker["diagram_host"]["from"] = [wall["to"][0], 0, wall["to"][2]]
                reversed_marker["diagram_host"]["to"] = [wall["from"][0], 3.6, wall["from"][2]]
                reversed_marker["entity"]["parentWall"] = "diagram_shared"
                reversed_marker["entity"]["from"][0] = length-marker["entity"]["from"][0]-1.2
                remapped = construct_system(reversed_marker, base)
                _accept_group(base, remapped, reversed_marker)
                check(f"shared_wall_{x}_{z}_{kind}_{wall['id']}", remapped == row)
        for axis in ("x", "z"):
            marker = {"id": "band", "type": "cornice", "construction_materials": roles, "design": {
                "type": "cornice", "size": {"width": 3 if axis == "x" else 0.3, "height": 0.24, "depth": 0.3 if axis == "x" else 3},
                "placement": {"position": [x+2, 4, z+2]}, "form": {"construction": band_spec(axis)}}}
            row = construct_system(marker, base)
            _, _, _ = _accept_group(base, row, marker)
            check(f"layered_extent_{x}_{z}_{axis}", abs(sum(e["dimensions"][1] for e in row["geometry"]["elements"])-0.24) < 1e-8)
    bad = {"type": "window", "size": {"width": 1.2, "height": 1.5}, "form": {"construction": opening_spec("window")}}
    bad["form"]["construction"]["verticalMullions"] = 99
    rejects("reject_no_glazing_clearance", lambda: validate_construction(bad))
    bad["form"]["construction"] = {"system": "invented"}
    rejects("reject_unknown_system", lambda: validate_construction(bad))


async def pipeline_checks():
    document = deepcopy(source_document)
    for component in document["decisions"]["components"]:
        if component["type"] in {"door", "window"}:
            component["form"]["construction"] = opening_spec(component["type"])
    document["decisions"]["components"].append({"id": "front_band", "type": "cornice", "host": "main_vol",
        "size": {"width": 6, "height": 0.28, "depth": 0.32}, "placement": {"position": [3, 3.15, -0.25]},
        "form": {"construction": band_spec()}})
    document = DesignDocument.model_validate(document)
    resolved = project_drawing(document)
    state = {"design_document": document.model_dump(mode="json"), "resolved_design": resolved.model_dump(mode="json"),
             "component_fragments": {}, "component_diagnostics": {}, "thinking_mode": False,
             "session_id": "construction-offline", "user_message": "离线构造装配回归"}
    state.update(await plan_node(state))
    originals = {mid: (diag, record) for diag in saved["component_diagnostics"].values() for mid, record in diag["implementations"].items()}
    old_entities = {e["id"]: e for values in saved["component_fragments"].values() for e in values}
    counts = {"llm": 0, "rag": 0}

    async def reply(_llm, messages, **kwargs):
        counts["llm"] += 1
        context = json.loads(messages[-1]["content"])
        rows = []
        for marker in context["markers"]:
            if marker.get("design", {}).get("form", {}).get("construction"):
                raise AssertionError("完整构造不应交给模型重写")
            diag, record = originals[marker["id"]]
            rows.append({"id": marker["id"], "geometry": {k: [deepcopy(old_entities[i]) for i in record["entity_ids"] if i in diag.get(k, [])] for k in ("elements", "components")},
                         "materials": diag.get("materials", {}), "assets": diag.get("assets", {})})
        return SimpleNamespace(content=json.dumps({"implementations": rows}), finish_reason="stop", token_usage=None, call_id="fixture")

    def retrieve(*args, **kwargs):
        counts["rag"] += 1
        return {"text": "offline fixture", "has_shape_reference": True}

    with patch("app.llm.client.create_llm", return_value=None), patch("app.llm.invocation.invoke_llm", side_effect=reply), \
            patch("app.agent.plan.knowledge_tool.search_knowledge_result", side_effect=retrieve):
        for item in PlanDocument.model_validate(state["plan"]).items:
            updates, status, _, message, trace = await run_marker_generate(state, item)
            check("pipeline_"+item.id+"_"+message, status == "succeeded")
            for key in ("component_fragments", "component_diagnostics"):
                state[key].update(updates[key])
        for item in PlanDocument.model_validate(state["plan"]).items:
            if any(construction_spec(m["design"]) for m in resolved.component_markers if m["id"] in item.target["marker_ids"]):
                updates, status, _, _, trace = await run_marker_generate(state, item)
                check("resume_no_duplicate_"+item.id, status == "succeeded"
                      and updates["component_fragments"][item.id] == state["component_fragments"][item.id]
                      and sum(t.get("model_calls", 0) for t in trace) == 0)
        compiled = await compile_node(state)
    check("compile_complete", compiled["status"] == "complete" and compiled["compile_report"]["design_complete"])
    check("only_unresolved_work_uses_model", counts == {"llm": 3, "rag": 3})
    construction = [t for d in state["component_diagnostics"].values() for t in d["trace"] if t.get("tool") == "construct_system"]
    check("four_constructions_zero_model_calls", len(construction) == 4 and all(t["model_calls"] == 0 for t in construction))
    for name, data in (("design.json", document.model_dump(mode="json")), ("state.json", state), ("compile.json", compiled)):
        (HERE / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (HERE / "constructed.wild").write_text(json.dumps(compiled["merged_blueprint"], ensure_ascii=False, indent=2), encoding="utf-8")
    # 注入已定位的构造冲突，验证执行/装配不会转交模型猜参数。
    item = next(i for i in PlanDocument.model_validate(state["plan"]).items if i.kind == "door")
    failed_state = deepcopy(state)
    failed_state["component_diagnostics"].pop(item.id)
    failed_state["component_fragments"].pop(item.id)
    with patch("app.agent.plan.implementation.construct_system", side_effect=ValueError("门窗套嵌入深度超过宿主墙厚")), \
            patch("app.llm.invocation.invoke_llm", side_effect=AssertionError("构造冲突不能调用模型")):
        updates, _, _, _, trace = await run_marker_generate(failed_state, item)
        for key in ("component_fragments", "component_diagnostics"):
            failed_state[key].update(updates[key])
        failure = await compile_node(failed_state)
    check("construction_conflict_stops_without_llm", sum(t.get("model_calls", 0) for t in trace) == 0
          and all(r["stop_reason"] == "construction_design_conflict" for r in updates["component_diagnostics"][item.id]["implementations"].values()))
    check("construction_conflict_blocks_delivery", failure["status"] == "failed" and not failure["compile_report"]["repair"]["attempted"])


async def refinement_checks():
    raw = deepcopy(source_document["decisions"])
    targets = [c for c in raw["components"] if c["type"] in {"window", "door"}]
    payload = {"details": [{"ids": [c["id"]], "construction": opening_spec(c["type"]), "reason": "保持洞口，补构造分工"} for c in targets]}

    def validate(candidate):
        project_drawing(DesignDocument.model_validate({**source_document, "decisions": candidate}))

    async def reply(*args, **kwargs):
        return SimpleNamespace(content=json.dumps(payload), finish_reason="stop", token_usage=None)

    with patch("app.agent.generation.architecture.design_workflow.create_llm", return_value=None), \
            patch("app.agent.generation.architecture.design_workflow.invoke_llm", side_effect=reply):
        revised, diag = await refine_construction(raw, user_request="fixture", diagram_hosts=[], validate=validate)
        check("refinement_applies_form_only", diag["status"] == "accepted" and revised["volumes"] == raw["volumes"]
              and all(a["size"] == b["size"] and a["placement"] == b["placement"] for a,b in zip(raw["components"], revised["components"])))
        payload["details"][0]["construction"]["canopy"]["width"] = 20
        rejected, diag = await refine_construction(raw, user_request="fixture", diagram_hosts=[], validate=validate)
        check("refinement_conflict_preserves_valid_groups", diag["status"] == "partial"
              and rejected["components"][0] == raw["components"][0]
              and sum(d["selected"] for d in diag["decisions"]) == 2)
        payload["details"][1]["construction"] = None
        payload["details"][2]["construction"] = None
        rejected, diag = await refine_construction(raw, user_request="fixture", diagram_hosts=[], validate=validate)
        check("no_valid_refinement_retains_original", rejected == raw and diag["status"] == "rejected")
        payload["details"][0]["ids"] = ["unapproved"]
        rejected, diag = await refine_construction(raw, user_request="fixture", diagram_hosts=[], validate=validate)
        check("refinement_cannot_add_markers", rejected == raw and diag["status"] == "rejected")
    with patch("app.agent.generation.architecture.design_workflow.create_llm", return_value=None), \
            patch("app.agent.generation.architecture.design_workflow.invoke_llm", side_effect=OSError("fixture service unavailable")):
        rejected, diag = await refine_construction(raw, user_request="fixture", diagram_hosts=[], validate=validate)
    check("optional_refinement_service_failure_retains_draft", rejected == raw and diag["status"] == "rejected" and diag["error_type"] == "OSError")


async def malformed_draft_check():
    failure = json.loads((HERE / "construction_smoke_20261024_191241/state.json").read_text(encoding="utf-8"))
    original = failure["architecture_diag"]["rejected_attempts"][0]["output"]
    calls = []

    async def reply(_llm, messages, **kwargs):
        calls.append(messages)
        content = original if len(calls) == 1 else json.dumps(source_document["decisions"])
        return SimpleNamespace(content=content, finish_reason="stop", token_usage=None)

    with patch("app.agent.generation.architecture.design_workflow.create_llm", return_value=None), \
            patch("app.agent.generation.architecture.design_workflow.invoke_llm", side_effect=reply):
        result, diag = await draft_design(base_prompt="fixture", user_request="fixture", max_attempts=2)
    repair_data = json.loads(calls[1][0]["content"].split("\n上一稿：")[-1])
    check("malformed_real_draft_preserved_for_revision", repair_data["unparsed_output"] == original
          and result == source_document["decisions"] and diag["settled"])


async def main():
    geometry_checks()
    await pipeline_checks()
    await refinement_checks()
    await malformed_draft_check()
    report = {"ok": True, "count": len(checks), "checks": checks, "real_model_calls": 0}
    (HERE / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "checks": len(checks)}))


if __name__ == "__main__":
    asyncio.run(main())
