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

    def append(name, messages, *, warning=False):
        if messages:
            results.append(PipelineStepResult(
                step="design", name=name,
                output="\n".join(f"{'⚠️' if warning else '❌'} [design] {m}" for m in messages),
                has_error=not warning, has_warning=warning,
            ))

    from app.utils.blueprint_parser import validate_blueprint_schema
    append("validate_blueprint_schema", validate_blueprint_schema(blueprint))

    design_errors = validate_design_brief_constraints(blueprint, design_brief)
    append("validate_design_brief", design_errors)
    append("design_quota_shortfall", design_quota_shortfalls(blueprint, design_brief), warning=True)
    fulfillment = None
    mutations = []
    approved_errors = []
    design_hash, revision = "", None
    if design_document:
        from app.design.contracts import DesignDocument, ObjectDecisions
        from app.design.resolver import _stable_hash
        from app.design.compilation import compile_document, project_compilation, opening_drift
        from app.design.normalization import approved_compilation_changes
        from app.design.fulfillment import evaluate_fulfillment, fulfillment_summary

        document = DesignDocument.model_validate(design_document)
        design_hash, revision = _stable_hash(document), document.revision
        if not isinstance(document.decisions, ObjectDecisions):
            compiled = compile_document(document)
            resolved = project_compilation(document, compiled)
            append("review_opening_consistency", opening_drift(resolved, blueprint))
            mutations = approved_compilation_changes(compiled.blueprint, blueprint)
            append("approved_design_mutation", [
                f"已审核实体发生变化：{c['path']}，{c['before']!r} → {c['after']!r}；需要设计修订"
                for c in mutations])
            approved_errors = [d.to_dict() for d in compiled.defects if d.severity == "error"]
            append("approved_design_invalid", [d["evidence"] for d in approved_errors])
            entries = list((compiled.stats.get("instance_overrides") or {}).get("instance_entities") or [])
            fulfillment = fulfillment_summary(evaluate_fulfillment(
                document, blueprint, design_hash, entries,
                list((compiled.design_brief or {}).get("roof_slots") or [])),
                design_hash=design_hash,
                superseded=sum(c.adoption == "superseded" for c in document.constraints))
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
