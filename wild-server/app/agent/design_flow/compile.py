"""统一装配；完整校验问题回到原任务，尝试耗尽后清理失败构件。"""
from copy import deepcopy

from app.agent.state import GenerationState


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


def _affected_markers(state, marker_ids):
    from app.design.markers import implementation_records
    records = implementation_records(state)
    affected = set(marker_ids)
    markers = (state.get("resolved_design") or {}).get("component_markers") or []
    while True:
        previous = set(affected)
        removed = {i for m in affected for i in (records.get(m) or {}).get("entity_ids", [])}
        for marker in markers:
            if set(marker.get("depends_on") or []) & affected:
                affected.add(marker["id"])
        for marker_id, record in records.items():
            ids = set(record.get("entity_ids") or [])
            for entities in (state.get("component_fragments") or {}).values():
                if any(e["id"] in ids and any(v in removed for k, v in e.items()
                       if k.startswith("parent") and isinstance(v, str)) for e in entities):
                    affected.add(marker_id)
        if previous == affected:
            break
    return affected


def _discard(state, marker_ids, reason):
    from app.design.markers import implementation_records
    records = implementation_records(state)
    affected = _affected_markers(state, marker_ids)
    updates = {"component_fragments": deepcopy(state.get("component_fragments") or {}),
               "component_diagnostics": deepcopy(state.get("component_diagnostics") or {})}
    removed = {i for m in affected for i in (records.get(m) or {}).get("entity_ids", [])}
    for task_id, diag in updates["component_diagnostics"].items():
        for marker_id, record in (diag.get("implementations") or {}).items():
            if marker_id in affected:
                record.update(status="abandoned", entity_ids=[], reason=reason,
                              dependency_failure=marker_id not in marker_ids)
        for bucket in ("elements", "components"):
            diag[bucket] = [i for i in diag.get(bucket, []) if i not in removed]
        updates["component_fragments"][task_id] = [e for e in updates["component_fragments"].get(task_id, []) if e["id"] not in removed]
    return updates


async def compile_node(state: GenerationState) -> dict:
    from app.design.contracts import DesignDocument
    from app.design.resolver import _stable_hash
    from app.design.markers import implementation_records
    from app.agent.plan.contracts import PlanDocument
    from app.agent.validation.candidate import evaluate_candidate

    plan = PlanDocument.model_validate(state["plan"])
    document = DesignDocument.model_validate(state["design_document"])
    blueprint, missing, compiled_records = _assemble_with_relations(document, state)
    if missing:
        return {"status": "failed", "error": "图纸标记未完成实现流程：" + ", ".join(missing)}
    records = implementation_records(state)
    brief = {"realization": document.decisions.massing.model_dump(mode="json"),
             "implementation": {"design_hash": _stable_hash(document), "records": compiled_records}}
    evaluation = evaluate_candidate(blueprint, design_document=document.model_dump(mode="json"),
                                    design_brief=brief, source="compile")
    if evaluation["errors"]:
        message = "; ".join(str(getattr(e, "output", e)) for e in evaluation["errors"])
        entity_ids = {issue.get("component_id") or issue.get("entity_id") for issue in evaluation["issues"]}
        entity_ids.discard(None)
        failed = {m for m, r in records.items() if r.get("status") == "implemented"
                  and (set(r.get("entity_ids") or []) & entity_ids
                       or (not entity_ids and any(i in message for i in r.get("entity_ids", []))))}
        from app.agent.knowledge.component_names import resolve_component_name
        missing_types = {issue["target_type"] for issue in evaluation["issues"] if issue.get("target_type")}
        failed.update(m["id"] for m in state["resolved_design"]["component_markers"]
                      if resolve_component_name(m["type"])["entity_type"] in missing_types and m["id"] in records)
        if len(failed) > 1:
            failed.discard("building_body")
        if not failed:
            failed = {"building_body"}
        updates = {"component_fragments": deepcopy(state.get("component_fragments") or {}),
                   "component_diagnostics": deepcopy(state.get("component_diagnostics") or {})}
        exhausted = {m for m in failed if "assembly_revision" in records[m].get("attempted_stages", [])}
        if exhausted:
            updates = _discard(state, exhausted, message)
        retry_markers = _affected_markers({**state, **updates}, failed - exhausted)
        retry_markers = {m for m in retry_markers if (implementation_records(updates).get(m) or {}).get("status") in {"implemented", "abandoned"}}
        retry = False
        for item in plan.items:
            targets = {m for m in item.target.get("marker_ids", []) if m in retry_markers}
            if not targets:
                continue
            exhausted_targets = {m for m in targets if "assembly_revision" in records[m].get("attempted_stages", [])}
            if exhausted_targets:
                updates = _discard({**state, **updates}, exhausted_targets, "依附对象需要重新实现，当前构件已耗尽尝试：" + message)
                targets -= _affected_markers({**state, **updates}, exhausted_targets)
            if not targets:
                continue
            retry = True
            item.params["assembly_feedback"] = message
            item.params["retry_marker_ids"] = [i for i in item.target["marker_ids"] if i in targets]
            target_entities = {i for m in targets for i in records[m].get("entity_ids", [])}
            item.params["reference_entity_ids"] = sorted({i for issue in evaluation["issues"]
                if (issue.get("component_id") or issue.get("entity_id")) in target_entities
                for i in issue.get("related_entity_ids", [])})
            item.status = "ready"
            item.run.state = "idle"
            # 重做宿主时同时移除依附结果，避免旧引用阻止新宿主通过局部检查。
            old = updates["component_diagnostics"].get(item.id) or {}
            prior = old.get("implementations") or {}
            removed_ids = {i for m in targets for i in prior[m].get("entity_ids", [])}
            old["prior_implementations"] = {m: prior[m] for m in targets}
            old["failed_implementations"] = {m: {"id": m,
                "geometry": {bucket: [deepcopy(e) for e in state["component_fragments"].get(item.id, [])
                    if e["id"] in prior[m].get("entity_ids", []) and e["id"] in old.get(bucket, [])]
                    for bucket in ("elements", "components")},
                "materials": deepcopy(old.get("materials") or {}), "assets": deepcopy(old.get("assets") or {})}
                for m in targets}
            old["implementations"] = {m: r for m, r in prior.items() if m not in targets}
            for bucket in ("elements", "components"):
                old[bucket] = [i for i in old.get(bucket, []) if i not in removed_ids]
            updates["component_diagnostics"][item.id] = old
            updates["component_fragments"][item.id] = [e for e in updates["component_fragments"].get(item.id, []) if e["id"] not in removed_ids]
        if retry:
            return {**updates, "plan": plan.model_dump(mode="json"), "merged_blueprint": {},
                    "compile_report": {"ok": False, "retry_implementation": True, "reason": message}, "error": None}
        if updates["component_diagnostics"]:
            state = {**state, **updates}
            blueprint, missing, compiled_records = _assemble_with_relations(document, state)
            brief["implementation"]["records"] = compiled_records
            evaluation = evaluate_candidate(blueprint, design_document=document.model_dump(mode="json"),
                                            design_brief=brief, source="compile_after_discard")
    records = implementation_records(state)
    actual = {e["id"] for bucket in ("elements", "components") for e in blueprint["geometry"][bucket]}
    for item in plan.items:
        rows = [records[m] for m in item.target.get("marker_ids", [])]
        abandoned = sum(r["status"] == "abandoned" for r in rows)
        item.status = "abandoned" if rows and abandoned == len(rows) else "done"
        item.run.evidence = f"实现流程结束：落实 {len(rows)-abandoned}，舍弃 {abandoned}"
        item.run.artifacts = [i for m in item.target.get("marker_ids", [])
                              for i in compiled_records[m].get("entity_ids", []) if i in actual]
    return {**({k: state[k] for k in ("component_fragments", "component_diagnostics")}),
            "plan": plan.model_dump(mode="json"), "merged_blueprint": blueprint, "design_brief": brief, "validation_snapshot": {},
            "compile_report": {"abandoned_markers": [m for m, r in records.items() if r["status"] == "abandoned"], "missing_markers": missing, "elements": len(blueprint["geometry"]["elements"]),
                               "components": len(blueprint["geometry"]["components"]),
                               "design_complete": not missing and all(r["status"] == "implemented" for r in records.values()),
                               "ok": not missing and not evaluation["errors"]}, "error": None}


__all__ = ["compile_node"]
