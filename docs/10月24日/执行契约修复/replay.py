"""保存回复的几何回放；修正样本独立保存，不覆盖原始建筑或已批准设计。"""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import patch

from verify import ROOT, HERE, STATES, recorded, expand_bind
from app.agent.generation.architecture.design_workflow import refine_construction
from app.design.contracts import DesignDocument
from app.design.compilation import project_drawing
from app.design.construction_systems import construct_system, construction_spec
from app.agent.plan.implementation import _accept_group, _accept_fragment, implementation_records


async def main():
    sid = "session_1792838578836"
    state = STATES[sid]
    document = deepcopy(state["design_document"])
    reply = state["architecture_diag"]["construction_refinement"]

    async def saved_reply(*args, **kwargs):
        return SimpleNamespace(content=reply["output"], token_usage=None, call_id="offline-saved-reply", finish_reason="stop")

    def validate(decisions):
        project_drawing(DesignDocument.model_validate({**document, "decisions": decisions}))

    with patch("app.agent.generation.architecture.design_workflow.create_llm", return_value=None), \
         patch("app.agent.generation.architecture.design_workflow.invoke_llm", side_effect=saved_reply):
        revised, diag = await refine_construction(document["decisions"], user_request=state["user_message"],
                                                  diagram_hosts=state["drawing_hosts"], validate=validate)
    document["decisions"] = revised
    resolved = project_drawing(DesignDocument.model_validate(document))
    roles = {r["role"]: r["materialId"] for r in state["material_plan"]["roles"]}
    markers = resolved.model_dump(mode="json")["component_markers"]
    records = implementation_records(state)
    base = json.loads((ROOT / "wild-server/storage/scenes/2026-10-24" / (sid+"_现代双层独栋别墅.wild")).read_text(encoding="utf-8"))
    outcomes = []
    selected = [m for m in markers if construction_spec(m["design"]) is not None]
    replacing = {eid for marker in selected for eid in records.get(marker["id"], {}).get("entity_ids", [])}
    for bucket in ("elements", "components"):
        base["geometry"][bucket] = [e for e in base["geometry"][bucket] if e["id"] not in replacing]
    for marker in selected:
        marker["construction_materials"] = roles
        try:
            row = construct_system(marker, base)
            candidate, accepted, rejected, record = _accept_fragment(base, row, marker,
                dependent_markers=markers, diagram_hosts=state["drawing_hosts"])
            if rejected:
                raise ValueError(rejected["error"])
            base = candidate
            outcomes.append({"id": marker["id"], "passed": True, "entity_ids": record["entity_ids"]})
        except (ValueError, TypeError, KeyError) as exc:
            outcomes.append({"id": marker["id"], "passed": False, "error": str(exc)})

    rows, old_markers, context = recorded("generate_5", "repair_2")
    roof, roof_evidence = expand_bind(rows[0], old_markers[rows[0]["id"]], context)
    try:
        base, _, _ = _accept_group(base, roof, old_markers[rows[0]["id"]])
        roof_acceptance = {"passed": True}
    except ValueError as exc:
        roof_acceptance = {"passed": False, "error": str(exc)}

    # 只演示模型可省略已由图纸确定的字段；不是声称旧回复的错误坐标直接通过。
    rows, old_markers, context = recorded("generate_10")
    sofa = deepcopy(rows[0])
    sofa["geometry"]["elements"][0].pop("position")
    sofa["geometry"]["elements"][0].pop("dimensions")
    sofa, sofa_evidence = expand_bind(sofa, old_markers[sofa["id"]], context)
    sofa_ids = records[sofa["id"]]["entity_ids"]
    for bucket in ("elements", "components"):
        base["geometry"][bucket] = [e for e in base["geometry"][bucket] if e["id"] not in sofa_ids]
    base, _, _ = _accept_group(base, sofa, old_markers[sofa["id"]])

    report = {"new_model_calls": 0, "source_session": sid, "refinement_status": diag["status"],
              "construction_geometry": outcomes, "roof_placement": roof_evidence,
              "roof_acceptance": roof_acceptance,
              "sofa_completion": sofa_evidence,
              "scope": "Saved responses plus a missing-fields furniture fixture; partial building, not an end-to-end model generation."}
    (HERE / "replay-second.wild").write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
    (HERE / "replay-design.json").write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    (HERE / "replay.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"new_model_calls": 0, "construction_geometry": outcomes}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
