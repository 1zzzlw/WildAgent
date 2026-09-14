"""组件节点共享的状态写入、基础校验与工具复检。"""

from loguru import logger

from app.agent.generation.components import ComponentConfig


def component_state_update(
    config: ComponentConfig,
    value,
    diag_key: str,
    diag: dict,
) -> dict:
    """写入通用组件分片和诊断映射。"""
    return {
        diag_key: diag,
        "component_fragments": {config.component_type: value},
        "component_diagnostics": {diag_key: diag},
    }


def validate_fragments(fragments: list[dict], config: ComponentConfig) -> list[dict]:
    """过滤类型不匹配或缺少必填字段的组件分片。"""
    valid = []
    for fragment in fragments:
        if not isinstance(fragment, dict) or fragment.get("type") != config.component_type:
            continue
        missing = [
            field
            for field in config.required_fields
            if is_missing_required_value(fragment, field)
        ]
        if missing:
            logger.warning(
                f"[{config.component_type}] 跳过 {fragment.get('id', '?')}："
                f"缺少必填字段 {missing}"
            )
            continue
        valid.append(fragment)
    return valid


def is_missing_required_value(fragment: dict, field: str) -> bool:
    """允许合法的 ``False`` 和 ``0``，只拒绝真正缺失或空值。"""
    if field not in fragment or fragment[field] is None:
        return True
    value = fragment[field]
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, tuple, set)):
        return not value
    return False


def validation_has_error(result) -> bool:
    """兼容文本工具与结构化校验结果。"""
    if isinstance(result, dict):
        if result.get("has_error") or result.get("status") == "error":
            return True
        if result.get("error_count", 0):
            return True
        errors = result.get("errors")
        if isinstance(errors, (list, tuple, dict, set)) and errors:
            return True
    if getattr(result, "has_error", False):
        return True
    return "❌" in str(result)


def validate_and_fix_with_tools(
    fragments: list[dict],
    component_type: str,
    skeleton_blueprint: dict,
    is_element: bool,
) -> tuple[list[dict], bool, bool]:
    """使用组件专用工具校验、修复并再次校验。"""
    if not fragments:
        return [], False, True

    try:
        from app.tools.component_tools import fix_component, validate_component
    except ImportError:
        logger.warning(f"[{component_type}] 组件工具未找到，跳过校验修复")
        return fragments, False, False

    temp_blueprint = {
        "meta": skeleton_blueprint.get(
            "meta", {"version": "1.1", "type": "building"}
        ),
        "geometry": {
            "elements": skeleton_blueprint.get("geometry", {})
            .get("elements", [])
            .copy(),
            "components": skeleton_blueprint.get("geometry", {})
            .get("components", [])
            .copy(),
        },
        "materials": skeleton_blueprint.get("materials", {}),
    }
    bucket = "elements" if is_element else "components"
    temp_blueprint["geometry"][bucket].extend(fragments)

    validation_result = validate_component(component_type, temp_blueprint)
    if not validation_has_error(validation_result):
        return fragments, False, True

    logger.warning(f"[{component_type}_val] 检测到错误，自动修复中...")
    fix_result = fix_component(component_type, temp_blueprint)
    logger.info(f"[{component_type}_val] 修复结果:\n{fix_result}")

    fixed_fragments = temp_blueprint["geometry"][bucket][-len(fragments):]
    recheck_result = validate_component(component_type, temp_blueprint)
    recheck_passed = not validation_has_error(recheck_result)
    if not recheck_passed:
        logger.warning(f"[{component_type}] 工具修复后复检仍未通过: {recheck_result}")
    return fixed_fragments, True, recheck_passed
