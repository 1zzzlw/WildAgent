"""统一装配已有分片；编译失败集中修复一次，保留可编辑草稿。"""
from copy import deepcopy

from app.agent.state import GenerationState


def _repair_scope_errors(original, candidate, feedback):
    """补丁只能改变失败实体及其资源；新增实体必须归属已定位的图纸标记。"""
    def entities(blueprint):
        return {e["id"]: e for bucket in ("elements", "components")
                for e in blueprint.get("geometry", {}).get(bucket, [])}

    before, after = entities(original), entities(candidate)
    allowed = set(feedback["entity_ids"])
    errors = []
    removed = before.keys() - after.keys()
    outside = {i for i in before.keys() & after.keys() if before[i] != after[i] and i not in allowed}
    if removed:
        errors.append("修复删除了已有实体：" + ", ".join(sorted(removed)))
    if outside:
        errors.append("修复修改了失败范围之外的实体：" + ", ".join(sorted(outside)))
    added = after.keys() - before.keys()
    for entity_id in added:
        if not any(entity_id == marker_id or entity_id.startswith(marker_id + "_") for marker_id in feedback["marker_ids"]):
            errors.append(f"新增实体 {entity_id} 无法归属失败图纸标记")

    from app.services.agent_service import _MATERIAL_REFERENCE_FIELDS
    def references(blueprint, selected):
        materials = {e[key] for e in selected for key in _MATERIAL_REFERENCE_FIELDS if isinstance(e.get(key), str)}
        assets = {value["textureSet"] for name, value in blueprint.get("materials", {}).items()
                  if name in materials and isinstance(value.get("textureSet"), str)}
        return {"materials": materials, "assets": assets}

    protected = references(original, [entity for i, entity in before.items() if i not in allowed])
    target = references(candidate, [entity for i, entity in after.items() if i in allowed or i in added])
    for bucket in ("materials", "assets"):
        old, new = original.get(bucket, {}), candidate.get(bucket, {})
        for name in old.keys() | new.keys():
            if old.get(name) != new.get(name) and (name in protected[bucket] or name not in target[bucket]):
                errors.append(f"修复修改了失败范围之外的 {bucket}/{name}")
    return errors


def _assemble_with_relations(document, state):
    from app.design.markers import assemble_marker_results, implementation_records
    from app.agent.generation.spatial.stair_openings import cut_stair_openings
    from app.agent.validation.diagnostics import blueprint_fingerprint

    blueprint, missing = assemble_marker_results(document, state)
    records = deepcopy(implementation_records(state))
    original = {e["id"]: e for bucket in ("elements", "components") for e in blueprint["geometry"][bucket]}
    # 先核对模型原片段，编译派生不能掩盖未经校验的改写。
    if any(blueprint_fingerprint([original[i] for i in r["entity_ids"]]) != r.get("entity_fingerprint")
           for r in records.values() if r.get("status") == "implemented"):
        return blueprint, missing, records
    changed = cut_stair_openings(blueprint)
    actual = {e["id"]: e for bucket in ("elements", "components") for e in blueprint["geometry"][bucket]}
    replacements = {i: [i] if i in actual else [] for i in changed}
    for entity_id in actual:
        if entity_id in original:
            continue
        floor_id = next(i for i in sorted(changed, key=len, reverse=True) if entity_id.startswith(i + "_opening_"))
        replacements[floor_id].append(entity_id)
    for record in records.values():
        ids = record.get("entity_ids") or []
        floors = [i for i in ids if i in replacements]
        if not floors:
            continue
        record["assembly_changes"] = [{"rule": "compiler.stair_openings", "floor_ids": floors,
            "source_entity_ids": ids, "source_entity_fingerprint": record["entity_fingerprint"]}]
        record["entity_ids"] = [part for i in ids for part in replacements.get(i, [i])]
        record["entity_fingerprint"] = blueprint_fingerprint([actual[i] for i in record["entity_ids"]])
    from app.agent.knowledge.component_names import resolve_component_name
    for marker in (state.get("resolved_design") or {}).get("component_markers", []):
        if (resolve_component_name(marker["type"])["entity_type"] != "railing"
                or (records.get(marker["id"]) or {}).get("status") != "implemented"):
            continue
        parent = records.get(marker.get("host")) or {}
        if parent.get("status") != "implemented":
            continue
        for entity_id in parent["entity_ids"]:
            entity = actual[entity_id]
            if entity.get("type") != "balcony" or entity.get("railingEnabled") is False:
                continue
            parent.setdefault("assembly_changes", []).append({"rule": "compiler.separate_railing",
                "source_entity_ids": list(parent["entity_ids"]), "source_entity_fingerprint": parent["entity_fingerprint"],
                "entity_id": entity_id, "before": entity.get("railingEnabled", True), "after": False,
                "railing_marker_id": marker["id"]})
            entity["railingEnabled"] = False
            parent["entity_fingerprint"] = blueprint_fingerprint([actual[i] for i in parent["entity_ids"]])
    return blueprint, missing, records


async def compile_node(state: GenerationState) -> dict:
    import json
    from app.design.contracts import DesignDocument
    from app.design.resolver import _stable_hash
    from app.agent.validation.candidate import evaluate_candidate
    from app.agent.validation.diagnostics import blueprint_fingerprint
    from app.services.agent_delivery import retain_generation_blueprint

    blueprint = retain_generation_blueprint(state)
    brief = deepcopy(state.get("design_brief") or {})
    report = {"ok": False, "missing_markers": []}
    previous_repair = (state.get("compile_report") or {}).get("repair") or {}
    if previous_repair.get("attempted"):
        report["repair"] = deepcopy(previous_repair)
    errors, evaluation, new_model_calls = [], None, 0
    try:
        document = DesignDocument.model_validate(state["design_document"])
        if previous_repair.get("attempted") and state.get("merged_blueprint"):
            blueprint = deepcopy(state["merged_blueprint"])
        else:
            blueprint, missing, records = _assemble_with_relations(document, state)
            blueprint = retain_generation_blueprint({**state, "final_blueprint": {}, "merged_blueprint": blueprint}, blueprint)
            report["missing_markers"] = missing
            brief = {"realization": document.decisions.massing.model_dump(mode="json"),
                     "implementation": {"design_hash": _stable_hash(document), "records": records}}
        evaluation = evaluate_candidate(blueprint, design_document=state["design_document"],
                                        design_brief=brief, source="compile")
        errors = [str(getattr(error, "output", error)) for error in evaluation["errors"]]
        if report["missing_markers"]:
            errors.append("图纸标记未完成实现流程：" + ", ".join(report["missing_markers"]))
        abandoned = [i for i, r in (brief.get("implementation") or {}).get("records", {}).items()
                     if r.get("status") == "abandoned"]
        if abandoned:
            errors.append("图纸标记实现失败：" + ", ".join(abandoned))
    except Exception as exc:
        errors = [f"编译已有分片失败：{exc}"]
        # 契约或装配异常不能使已生成的原始分片消失。
        blueprint = retain_generation_blueprint(state, blueprint)

    geometry = (blueprint or {}).get("geometry")
    has_entities = isinstance(geometry, dict) and any(
        isinstance(geometry.get(bucket), list) and geometry[bucket] for bucket in ("elements", "components"))
    incomplete = bool(report["missing_markers"]) or any(
        r.get("status") != "implemented" for r in (brief.get("implementation") or {}).get("records", {}).values())
    from app.agent.validation.issues import repair_feedback
    feedback = repair_feedback((evaluation or {}).get("issues", []), blueprint or {},
        markers=(state.get("resolved_design") or {}).get("component_markers", []),
        records=(brief.get("implementation") or {}).get("records"),
        design_hash=(evaluation or {}).get("snapshot", {}).get("design_hash", ""), source="compile")
    report["repair_feedback"] = feedback
    if errors and incomplete and not state.get("terminal_model_error") and not previous_repair.get("attempted"):
        report["repair"] = {"attempted": False, "accepted": False, "stop_reason": "implementation_incomplete",
                            "error": "图纸尚有未实现标记，已保留通过片段与失败稿；集中修复不代替未执行的构件任务。"}
    if (errors and has_entities and not incomplete and not state.get("terminal_model_error")
            and not previous_repair.get("attempted")):
        if feedback["requires_design_revision"] or not feedback["entity_ids"]:
            report["repair"] = {"attempted": False, "accepted": False,
                "stop_reason": "design_revision_required" if feedback["requires_design_revision"] else "unlocalized_issues",
                "error": "需要修订设计或补齐错误归属，保留当前蓝图及失败证据。"}
    if (errors and has_entities and not incomplete and not state.get("terminal_model_error")
            and not previous_repair.get("attempted") and feedback["entity_ids"] and not feedback["requires_design_revision"]):
        from app.agent.prompts import build_patch_system_prompt
        from app.agent.runtime import get_reasoning_callback
        from app.llm.client import create_llm
        from app.llm.invocation import invoke_llm
        from app.services.agent_service import (
            _extract_patch_artifact, _validate_scene_patch_operations, _apply_patch_to_blueprint,
        )
        from app.agent.validation.issues import compare_issue_sets

        repair = {"attempted": True, "accepted": False, "original_blueprint": deepcopy(blueprint),
                  "original_errors": list(errors), "model_calls": 0, "feedback": feedback}
        report["repair"] = repair
        try:
            from config import config
            callback = get_reasoning_callback()
            if callback:
                await callback("compile:progress", "编译发现错误，正在集中修复一次；已有蓝图会保留。\n")
            llm = create_llm(model_cfg=config.chat.model_copy(update={"max_retries": 0}),
                             enable_thinking=False, streaming=False)
            from app.agent.generation.capability import load_engine_schema
            from app.agent.plan.implementation import _output_protocol
            schema = load_engine_schema()
            if schema is None:
                raise ValueError("WILD Schema 不可用，保留修复前蓝图")
            markers = {e["id"]: {"type": e["type"]} for bucket in ("elements", "components")
                       for e in geometry.get(bucket, [])}
            protocol = _output_protocol(schema, markers, "", {})
            messages = [
                {"role": "system", "content": build_patch_system_prompt(protocol)},
                {"role": "user", "content": (
                    "修复本次编译错误，只返回 ScenePatch。仅修改错误相关片段，保留已有实体 ID 和正确几何；"
                    "不能通过删除实体、改变建筑形制或忽略图纸尺寸消除错误。缺失构件仅按本次图纸补充。"
                    "repair_feedback.entity_ids 是允许修改的实体范围；其余实体及其共享材质、资产只读。"
                    "新增实体使用 repair_feedback.marker_ids 中对应标记ID作为前缀，纳入该标记复验。"
                    "数值先计算，返回完整 JSON。只有这一次修复机会，不重新生成整栋建筑。\n"
                    + json.dumps({"errors": errors, "repair_feedback": feedback, "blueprint": blueprint,
                                  "design_document": state.get("design_document"),
                                  "failed_implementations": {marker: row
                                      for diag in (state.get("component_diagnostics") or {}).values()
                                      for marker, row in (diag.get("failed_implementations") or {}).items()},
                                  "references": list(dict.fromkeys(diag["references"]
                                      for diag in (state.get("component_diagnostics") or {}).values()
                                      if diag.get("references")))}, ensure_ascii=False))},
            ]
            repair["model_calls"] = 1
            new_model_calls = 1
            response = await invoke_llm(llm, messages, max_retries=0)
            patch, source = _extract_patch_artifact(response.content, response.reasoning)
            repair.update(patch=patch, structured_source=source)
            if patch is None:
                raise ValueError("模型未返回可解析的局部修复；保留修复前蓝图")
            operation_errors = _validate_scene_patch_operations(blueprint, patch)
            if operation_errors:
                raise ValueError("；".join(operation_errors))
            candidate = _apply_patch_to_blueprint(blueprint, patch)
            scope_errors = _repair_scope_errors(blueprint, candidate, feedback)
            if scope_errors:
                raise ValueError("；".join(scope_errors))
            original_entities = {e["id"]: e for bucket in ("elements", "components")
                                 for e in geometry.get(bucket, [])}
            actual = {e["id"]: e for bucket in ("elements", "components")
                      for e in candidate["geometry"].get(bucket, [])}
            candidate_brief = deepcopy(brief)
            # 修改后的实体重新接受完整几何与设计关系校验，不能沿用旧指纹冒充通过。
            new_owners = {}
            for entity_id in actual.keys() - original_entities.keys():
                new_owners[entity_id] = max((i for i in feedback["marker_ids"]
                    if entity_id == i or entity_id.startswith(i + "_")), key=len)
            for marker_id, record in (candidate_brief.get("implementation") or {}).get("records", {}).items():
                ids = record.get("entity_ids") or []
                if record.get("status") == "implemented" and ids and all(i in actual for i in ids):
                    added = [i for i, owner in new_owners.items() if owner == marker_id]
                    if added or any(actual[i] != original_entities.get(i) for i in ids):
                        record.setdefault("assembly_changes", []).append({"rule": "compiler.llm_repair",
                            "source_entity_fingerprint": record.get("entity_fingerprint"),
                            "source_entity_ids": list(ids), "operations": deepcopy(patch["operations"])})
                        record["entity_ids"] = [*ids, *added]
                        record["entity_fingerprint"] = blueprint_fingerprint([actual[i] for i in record["entity_ids"]])
            after = evaluate_candidate(candidate, design_document=state.get("design_document"),
                                       design_brief=candidate_brief, source="compile_repair")
            repair["remaining_errors"] = [str(getattr(e, "output", e)) for e in after["errors"]]
            repair["remaining_issues"] = after["issues"]
            progress = compare_issue_sets(evaluation["issues"], after["issues"]) if evaluation else {"accepted": False}
            before_satisfied = set(((evaluation or {}).get("fulfillment") or {}).get("satisfied_ids") or [])
            after_satisfied = set((after.get("fulfillment") or {}).get("satisfied_ids") or [])
            repair["accepted"] = (candidate != blueprint and before_satisfied <= after_satisfied
                                   and (not after["errors"] or progress["accepted"]))
            if repair["accepted"]:
                blueprint, brief, evaluation = candidate, candidate_brief, after
                errors = repair["remaining_errors"]
            else:
                repair["error"] = "修复未减少错误或损失已有设计成果，保留修复前蓝图"
        except Exception as exc:
            repair["error"] = f"集中修复未完成：{exc}"

    records = (brief.get("implementation") or {}).get("records") or {}
    geometry = (blueprint or {}).get("geometry")
    geometry = geometry if isinstance(geometry, dict) else {}
    report.update(ok=not errors, errors=errors,
        abandoned_markers=[m for m, r in records.items() if r.get("status") == "abandoned"],
        design_complete=bool(records) and not report["missing_markers"]
                        and all(r.get("status") == "implemented" for r in records.values()),
        elements=len(geometry.get("elements") or []), components=len(geometry.get("components") or []))
    original_error = state.get("error") if state.get("status") == "failed" else None
    error = "\n".join(filter(None, [original_error, *errors, (report.get("repair") or {}).get("error")])) or None
    updates = {"merged_blueprint": blueprint or {}, "design_brief": brief, "validation_snapshot": {},
               "compile_report": report, "status": "failed" if error else "complete", "error": error}
    if state.get("plan"):
        plan = deepcopy(state["plan"])
        plan["llm_calls"] = plan.get("llm_calls", 0) + new_model_calls
        updates["plan"] = plan
    return updates


__all__ = ["compile_node"]
