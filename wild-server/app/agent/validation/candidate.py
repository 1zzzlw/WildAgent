"""同一候选的完整只读验收，供 callback 与 final_validate 共用。"""
from copy import deepcopy
from dataclasses import asdict

from app.agent.validation.diagnostics import (
    VALIDATOR_VERSION, ValidationSnapshot, blueprint_fingerprint, step_result_to_dict,
)
from app.agent.validation.design_constraints import (
    design_quota_shortfalls, validate_design_brief_constraints,
)
from app.agent.validation.issues import validation_issues_from_results


def evaluate_candidate(blueprint: dict, *, design_document=None, design_brief=None,
                       source: str = "") -> dict:
    """不发事件、不写 State、不修复；所有证据绑定传入的原始候选。"""
    from app.services.agent_service import PipelineStepResult, _final_errors, run_validation_pipeline
    from app.services.agent_delivery import final_validation_results, WARNING_GATE_MAX

    target = deepcopy(blueprint)
    results = run_validation_pipeline(target, log_steps=False, auto_fix=False)
    if target != blueprint:
        raise RuntimeError("只读校验器修改了候选，拒绝为原产物签发证据")

    def append(name, messages, *, warning=False, marker=None, entity_ids=()):
        if messages:
            result = PipelineStepResult(
                step="design", name=name,
                output="\n".join(f"{'⚠️' if warning else '❌'} [design] {m}" for m in messages),
                has_error=not warning, has_warning=warning,
                issues=[{"code": name, "marker_id": marker["id"], "design_path": marker["design_path"],
                         "entity_ids": list(entity_ids), "message": message,
                         "expected": marker["design"].get("size") or marker.get("floor_connections"),
                         "actual": {"entity_ids": list(entity_ids)}} for message in messages] if marker else None,
            )
            prior = next((r for r in results if r.step == "design" and r.name == name), None)
            if prior is None:
                results.append(result)
            else:
                prior.output += "\n" + result.output
                prior.has_error = prior.has_error or result.has_error
                prior.has_warning = prior.has_warning or result.has_warning
                if result.issues:
                    prior.issues = [*(prior.issues or []), *result.issues]

    from app.utils.blueprint_parser import validate_blueprint_schema
    append("validate_blueprint_schema", validate_blueprint_schema(blueprint))
    import json
    try:
        json.dumps(blueprint, allow_nan=False)
    except (ValueError, TypeError) as exc:
        append("validate_wild_json", [str(exc)])
    import jsonschema
    from app.agent.generation.capability import load_engine_schema
    schema = load_engine_schema()
    append("validate_wild_schema", ["WILD Schema 不可用"] if schema is None else
           [f"/{'/'.join(map(str, e.path))}: {e.message}" for e in jsonschema.Draft202012Validator(schema).iter_errors(blueprint)])

    design_errors = validate_design_brief_constraints(blueprint, design_brief, design_document=design_document)
    append("validate_design_brief", design_errors)
    append("design_quota_shortfall", design_quota_shortfalls(blueprint, design_brief), warning=True)
    fulfillment = None
    mutations = []
    approved_errors = []
    design_hash, revision = "", None
    if design_document:
        from app.design.contracts import DesignDocument, ObjectDecisions, DesignGap
        from app.design.resolver import _stable_hash
        from app.design.markers import IMPLEMENTATION_STAGES, body_floor_errors
        from app.design.compilation import project_drawing
        from app.design.fulfillment import evaluate_fulfillment, fulfillment_summary

        document = DesignDocument.model_validate(design_document)
        design_hash, revision = _stable_hash(document), document.revision
        if not isinstance(document.decisions, ObjectDecisions):
            implementation = (design_brief or {}).get("implementation") or {}
            if implementation.get("design_hash") != design_hash:
                append("implementation_version", ["落实记录与设计版本不一致"])
            records = implementation.get("records") or {}
            actual = {e["id"]: e for bucket in ("elements", "components")
                      for e in blueprint.get("geometry", {}).get(bucket, [])}
            markers = project_drawing(document).component_markers
            geometry_reviews = {}
            for marker in markers:
                record = records.get(marker["id"]) or {}
                if record.get("status") == "implemented":
                    ids = record.get("entity_ids") or []
                    if not ids or any(i not in actual for i in ids):
                        append("design_marker_fulfillment", [f"{marker['id']} 的实现实体缺失"])
                    elif blueprint_fingerprint([actual[i] for i in ids]) != record.get("entity_fingerprint"):
                        append("implementation_changed", [f"{marker['id']} 的实现被修改，需要重新执行构件校验"])
                    else:
                        if marker["type"] == "building_body":
                            append("design_body_footprint", body_floor_errors([actual[i] for i in ids], marker["design"]))
                        from app.design.relations import (opening_design_errors, roof_design_errors, railing_design_errors,
                                                          stair_design_errors, component_geometry_review)
                        marker["host_entity_ids"] = (records.get(marker.get("host")) or {}).get("entity_ids", [marker.get("host")])
                        append("design_opening_placement", opening_design_errors(blueprint, [actual[i] for i in ids], marker))
                        append("design_roof_surface", roof_design_errors(blueprint, [actual[i] for i in ids], marker))
                        append("design_railing_placement", railing_design_errors(blueprint, [actual[i] for i in ids], marker))
                        append("design_stair_connection", stair_design_errors(blueprint, [actual[i] for i in ids], marker),
                               marker=marker, entity_ids=ids)
                        review = component_geometry_review(blueprint, [actual[i] for i in ids], marker)
                        geometry_reviews[marker["id"]] = review
                        append("design_component_geometry", review["errors"], marker=marker, entity_ids=ids)
                elif record.get("status") == "abandoned":
                    attempts = record.get("attempts") or []
                    stages = {t.get("stage") for t in attempts}
                    lookup = next((t for t in attempts if t.get("tool") == "search_knowledge"), None)
                    references_checked = bool(lookup and (lookup.get("web_required") is False
                        or any(t.get("tool") == "web_search" for t in attempts)))
                    from app.agent.validation.issues import repeated_failed_candidate
                    finished = (set(IMPLEMENTATION_STAGES).issubset(stages) or "assembly_revision" in stages
                                or repeated_failed_candidate({**record, "marker_id": marker["id"]}))
                    if not record.get("reason") or (not record.get("dependency_failure") and (not finished or not references_checked)):
                        append("implementation_incomplete", [f"{marker['id']} 没有完成实现尝试，不能声明舍弃"])
                    if marker["id"] == "building_body":
                        append("implementation_incomplete", ["建筑主体未实现，无法交付建筑文件"])
                else:
                    append("implementation_incomplete", [f"{marker['id']} 没有落实记录"])
            gaps = evaluate_fulfillment(document, blueprint, design_hash)
            gaps.extend(DesignGap(id="review."+marker_id, constraint_id="design.geometry", status="needs_review",
                                  design_hash=design_hash, target=marker_id, expected="图纸关系与组合表达",
                                  actual=review["checked"], evidence="；".join(review["unverified"]))
                        for marker_id, review in geometry_reviews.items() if review["status"] == "needs_review")
            fulfillment = fulfillment_summary(gaps,
                design_hash=design_hash, superseded=sum(c.adoption == "superseded" for c in document.constraints))
            fulfillment["implementations"] = records
            for marker_id, record in records.items():
                if record.get("status") == "abandoned":
                    fulfillment["gaps"].append({"id": "implementation."+marker_id, "target": marker_id,
                        "status": "open", "expected": "落实图纸标记", "actual": "舍弃",
                        "evidence": record["reason"]})
                    fulfillment["total"] += 1
                    fulfillment["open"] += 1
            fulfillment["decided"] = fulfillment["satisfied"] + fulfillment["open"]
            fulfillment["satisfied_ratio"] = round(fulfillment["satisfied"]/fulfillment["decided"], 3) if fulfillment["decided"] else None
            fulfillment["decidable_coverage"] = round(fulfillment["decided"]/fulfillment["total"], 3) if fulfillment["total"] else None
            fulfillment["implementation_summary"] = {
                "implemented": sum(r.get("status") == "implemented" for r in records.values()),
                "abandoned": sum(r.get("status") == "abandoned" for r in records.values()),
                "design_complete": all((records.get(m["id"]) or {}).get("status") == "implemented" for m in markers),
                "relationships_verified": len(geometry_reviews) == len(markers)
                                          and all(r["status"] != "needs_review" for r in geometry_reviews.values()),
                "needs_review": sum(r["status"] == "needs_review" for r in geometry_reviews.values()),
                "verification": "geometry_checked_with_reported_review_gaps; rendering_requires_review"}
            fulfillment["blueprint_fingerprint"] = blueprint_fingerprint(blueprint)

    warning_count = sum(r.has_warning and not r.has_error for r in final_validation_results(results))
    if warning_count > WARNING_GATE_MAX:
        append("validate_delivery_warning_gate", [
            f"校验警告 {warning_count} 超过交付上限 {WARNING_GATE_MAX}，完整交付门禁未通过"])
    errors = _final_errors(results)
    issues = validation_issues_from_results(errors, blueprint)
    snapshot = ValidationSnapshot(
        blueprint_fingerprint=blueprint_fingerprint(blueprint), validator_version=VALIDATOR_VERSION,
        design_hash=design_hash, design_revision=revision,
        design_brief_fingerprint=blueprint_fingerprint(design_brief),
        status="partial" if errors else "complete",
        results=[step_result_to_dict(r) for r in results], design_errors=design_errors,
        issues=issues, fulfillment=fulfillment, error_count=len(errors),
        warning_count=warning_count, source=source,
    )
    return {"results": results, "errors": errors, "issues": issues,
            "snapshot": asdict(snapshot), "fulfillment": fulfillment,
            "approved_design_changes": mutations, "approved_design_errors": approved_errors}
