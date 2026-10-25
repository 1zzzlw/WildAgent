"""以保存的真实输入/输出作离线定位；不改变生产函数或运行记录。"""
import asyncio
from copy import deepcopy
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
from app.agent.plan.construction import expand_implementation
from app.agent.plan.implementation import _bind_materials, _accept_group
from app.design.parametric import expand_parameters
from app.design.contracts import DesignDocument
from app.design.compilation import project_drawing
from app.agent.generation.architecture.design_workflow import refine_construction
from app.utils.json_extractor import extract_json_object

states, traces = {}, {}
for sid in ("session_1792828902444", "session_1792838578836"):
    states[sid] = json.loads((HERE / sid / "state.json").read_text(encoding="utf-8"))
    traces[sid] = json.loads(next((ROOT / "wild-server/storage/sessions/rag_traces" / sid).glob("*.json")).read_text(encoding="utf-8"))


def request_context(sid, attempt):
    trace = traces[sid]
    call = next(c for c in trace["llm_calls"] if c["call_id"] == attempt["call_id"])
    return json.loads(trace["llm_inputs"][call["messages_ref"]]["messages"][-1]["content"])


def attempt_for(sid, item, stage="generate"):
    return next(t for t in states[sid]["component_diagnostics"][item]["trace"] if t.get("stage") == stage)


def result_of(function):
    try:
        function()
        return {"passed": True}
    except Exception as exc:
        return {"passed": False, "error": str(exc)}


async def main():
    report = {"new_model_calls": 0}
    sid = "session_1792828902444"
    attempt = attempt_for(sid, "generate_8")
    context = request_context(sid, attempt)
    source = extract_json_object(attempt["output"], outer_only=True)
    lights = []
    for row in source["implementations"]:
        marker = next(m for m in states[sid]["resolved_design"]["component_markers"] if m["id"] == row["id"])
        expanded, _ = expand_implementation(row, marker, context)
        expanded, _ = _bind_materials(context["existing_blueprint"], expanded, marker, context["material_roles"])
        probe_marker = deepcopy(marker)
        probe_marker["design"].pop("material_role", None)
        lights.append({"id": row["id"], "material_id": marker["material_id"],
            "nested_body_materials": [b.get("material") for e in expanded["geometry"]["components"] for b in e.get("body", [])],
            "actual_acceptance": result_of(lambda: _accept_group(context["existing_blueprint"], expanded, marker)),
            "isolating_material_check_only": result_of(lambda: _accept_group(context["existing_blueprint"], expanded, probe_marker))})
    report["light_material_check"] = lights
    sid = "session_1792838578836"
    attempt = attempt_for(sid, "generate_14")
    context = request_context(sid, attempt)
    rows = extract_json_object(attempt["output"], outer_only=True)["implementations"]
    nesting = []
    for row in rows:
        marker = next(m for m in states[sid]["resolved_design"]["component_markers"] if m["id"] == row["id"])
        expanded, _ = expand_implementation(row, marker, context)
        nesting.append({"id": row["id"], "expanded_element_types": [type(e).__name__ for e in expanded["geometry"]["elements"]],
                       "reported_error": attempt["errors"][row["id"]]})
    report["repeat_shape_error"] = nesting
    attempt = attempt_for(sid, "generate_10")
    context = request_context(sid, attempt)
    row = next(r for r in extract_json_object(attempt["output"], outer_only=True)["implementations"]
               if r["id"] == "sofa_living")
    marker = next(m for m in states[sid]["resolved_design"]["component_markers"] if m["id"] == row["id"])
    expanded, _ = expand_implementation(row, marker, context)
    expanded, _ = _bind_materials(context["existing_blueprint"], expanded, marker, context["material_roles"])
    report["sofa_placement_check"] = {
        "approved_position": marker["design"]["placement"]["position"],
        "actual_position": expanded["geometry"]["elements"][0]["position"],
        "actual_acceptance": result_of(lambda: _accept_group(context["existing_blueprint"], expanded, marker)),
        "recorded_review": states[sid]["component_diagnostics"]["generate_10"]["implementations"][row["id"]]["geometry_review"],
        "note": "X drift is 15m; Y uses different center/base anchors and is not compared directly."}
    facts = {"wall": {"from": [7, 0, 0]}}
    report["keyword_property"] = {expression: result_of(lambda: expand_parameters({"parameters": {}, "x": expression}, facts=facts))
                                  for expression in ("=facts.wall.from[0]", '=facts.wall["from"][0]')}
    saved = states[sid]
    recorded = saved["architecture_diag"]["construction_refinement"]
    original = saved["design_document"]["decisions"]

    async def original_reply(*args, **kwargs):
        return SimpleNamespace(content=recorded["output"], token_usage=recorded.get("token_usage"), call_id=recorded["call_id"], finish_reason="stop")

    def validate(candidate):
        project_drawing(DesignDocument.model_validate({**saved["design_document"], "decisions": candidate}))

    with patch("app.agent.generation.architecture.design_workflow.create_llm", return_value=None), \
            patch("app.agent.generation.architecture.design_workflow.invoke_llm", side_effect=original_reply):
        revised, diag = await refine_construction(original, user_request=saved["user_message"],
            diagram_hosts=saved["drawing_hosts"], validate=validate)
    report["current_refinement_replay"] = {k: v for k, v in diag.items() if k not in ("output", "token_usage")}
    original_input = request_context(sid, recorded)
    report["runtime_refinement_host_count"] = len(original_input["diagram_hosts"])
    report["current_drawing_host_count"] = len(saved["drawing_hosts"])
    (HERE / "probe.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
