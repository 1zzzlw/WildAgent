"""校验错误到具体蓝图实体的追踪逻辑。"""

from app.agent.validation.issues import (
    group_issues_by_entity,
    validation_issues_from_results,
)


def trace_errors_to_components(
    errors,
    blueprint: dict,
    *,
    validation_issues: list[dict] | None = None,
) -> list[dict]:
    """从校验错误信息中追溯到具体组件，提取结构化失败信息

    策略：
    1. 优先用正则匹配 ❌/⚠️ [component_id] 格式（精确）
    2. Fallback：词边界包含匹配（加边界检查避免 "door" 误匹配 "door_frame"）
    3. 附带组件的完整 current_params，供回调节点使用
    """
    import re

    components = blueprint.get("geometry", {}).get("components", [])
    elements = blueprint.get("geometry", {}).get("elements", [])
    all_entities: dict[str, dict] = {}
    for e in elements + components:
        eid = e.get("id")
        if eid:
            all_entities[eid] = e

    issues = validation_issues or validation_issues_from_results(errors, blueprint)
    grouped_issues = group_issues_by_entity(issues)

    # 新协议优先：保留同一个实体上的全部问题，而不是遇到第一条后丢弃其余错误。
    failed: list[dict] = []
    if grouped_issues:
        for component_id, entity_issues in grouped_issues.items():
            entity = all_entities.get(component_id)
            if entity is None:
                continue
            tools = []
            related_entity_ids = []
            for issue in entity_issues:
                for tool_name in issue.get("suggested_tools", []):
                    if tool_name not in tools:
                        tools.append(tool_name)
                for related_id in issue.get("related_entity_ids", []):
                    if related_id not in related_entity_ids:
                        related_entity_ids.append(related_id)
            failed.append({
                "component_id": component_id,
                "component_type": entity.get("type", "?"),
                "current_params": entity,
                "error_step": ", ".join(dict.fromkeys(
                    str(issue.get("validator", "unknown")) for issue in entity_issues
                )),
                "error_message": "\n".join(
                    str(issue.get("message", "")) for issue in entity_issues
                )[:1200],
                "issues": entity_issues,
                "suggested_tools": tools,
                "related_entity_ids": related_entity_ids,
                "related_entities": [
                    all_entities[related_id]
                    for related_id in related_entity_ids
                    if related_id in all_entities
                ],
            })

    # 设计配额缺失没有现成实体 ID，用稳定的 design:<type> 作为修复目标，
    # 允许 callback 调用 add_entity；其他全局错误继续保持阻断而不猜测。
    for issue in issues:
        repair_target = issue.get("repair_target")
        target_type = issue.get("target_type")
        if not repair_target or not target_type:
            continue
        failed.append({
            "component_id": repair_target,
            "component_type": target_type,
            "current_params": {},
            "error_step": issue.get("validator", "validate_design_brief"),
            "error_message": issue.get("message", ""),
            "issues": [issue],
            "suggested_tools": ["add_entity"],
            "is_design_target": True,
        })

    if failed:
        return failed

    # ── 旧格式 fallback：精确匹配结构化标记 ❌ [id] 或 ⚠️ [id] ──
    marker_pattern = re.compile(r'[❌⚠️]\s*\[(?:component:)?([\w.-]+)\]')

    failed: list[dict] = []
    seen_ids: set[str] = set()

    for error_result in errors:
        output = error_result.output

        for match in marker_pattern.finditer(output):
            comp_id = match.group(1)
            if comp_id in seen_ids:
                continue
            seen_ids.add(comp_id)

            entity = all_entities.get(comp_id)
            if entity is None:
                continue

            failed.append({
                "component_id": comp_id,
                "component_type": entity.get("type", "?"),
                "current_params": entity,
                "error_step": error_result.name,
                "error_message": _extract_error_context(output, comp_id),
            })

    # ── 模式2（fallback）：词边界包含匹配 ──
    if not failed:
        for error_result in errors:
            output = error_result.output
            for comp_id, entity in all_entities.items():
                if comp_id in seen_ids:
                    continue
                if re.search(r'\b' + re.escape(comp_id) + r'\b', output):
                    seen_ids.add(comp_id)
                    failed.append({
                        "component_id": comp_id,
                        "component_type": entity.get("type", "?"),
                        "current_params": entity,
                        "error_step": error_result.name,
                        "error_message": _extract_error_context(output, comp_id),
                    })

    return failed


def _extract_error_context(output: str, comp_id: str) -> str:
    """从校验输出中提取与指定组件 ID 相关的错误行（最多300字符）"""
    lines = output.split("\n")
    relevant = [line.strip() for line in lines if comp_id in line]
    if not relevant:
        return output[:300]
    return "\n".join(relevant)[:300]


def get_all_entity_ids(blueprint: dict) -> list[str]:
    """获取所有组件和元素的 ID"""
    ids = []
    
    components = blueprint.get("geometry", {}).get("components", [])
    for comp in components:
        comp_id = comp.get("id")
        if comp_id:
            ids.append(comp_id)
    
    elements = blueprint.get("geometry", {}).get("elements", [])
    for el in elements:
        el_id = el.get("id")
        if el_id:
            ids.append(el_id)
    
    return ids
