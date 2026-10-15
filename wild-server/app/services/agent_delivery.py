"""Blueprint 生成结果的统一保存和校验报告出口。"""

from dataclasses import dataclass
from copy import deepcopy
import datetime as _dt
import re as _re

from loguru import logger

from app.utils.blueprint_parser import (
    SCENES_DIR,
    compact_blueprint_title,
    save_blueprint_file_as,
)


class GenerationRejectedError(RuntimeError):
    """生成结果没有满足可保存条件。"""


class ArtifactSaveError(RuntimeError):
    """服务端文件保存失败。"""


# 超过此值仍记为校验错误，但不阻止保存已有结果。
WARNING_GATE_MAX = 20


@dataclass(frozen=True)
class ValidationSummary:
    total: int
    passed: int
    warnings: int
    errors: int


@dataclass(frozen=True)
class BlueprintDelivery:
    filename: str
    file_url: str
    name: str
    elements_count: int
    components_count: int
    validation: ValidationSummary
    fulfillment: dict | None = None
    validation_passed: bool = True
    validation_errors: tuple[str, ...] = ()

    @property
    def reply(self) -> str:
        base = (
            f"已生成 {self.name or '建筑'}（{self.elements_count} 元素 + "
            f"{self.components_count} 组件，校验 {self.validation.passed}✓ "
            f"{self.validation.warnings}⚠ {self.validation.errors}✗），已保存为 `{self.filename}`。"
        )
        if not self.validation_passed:
            base += "校验未通过，已保留现有结果供查看和修改。"
        if self.validation_errors:
            base += "\n\n校验错误：\n" + "\n".join(f"- {error}" for error in self.validation_errors)
        if not self.fulfillment or not self.fulfillment.get("total"):
            return base
        implementation = self.fulfillment.get("implementation_summary") or {}
        if implementation.get("abandoned"):
            base += (f"图纸落实 {implementation['implemented']} 项、舍弃 {implementation['abandoned']} 项，"
                     "设计尚未完整实现。")
        # 缺口逐条列出（最多 3 条），让用户看到"哪一条没做到"，而不是只看到一个比例。
        outstanding = [
            gap for gap in self.fulfillment.get("gaps") or []
            if gap.get("status") == "open"
        ]
        detail = ""
        if outstanding:
            preview = "；".join(
                f"{gap['target']}（期望 {gap['expected']!r}，实际 {gap['actual']!r}）"
                for gap in outstanding[:3]
            )
            more = f" 等 {len(outstanding)} 条" if len(outstanding) > 3 else ""
            detail = f"未兑现：{preview}{more}。"
        from app.design.fulfillment import fulfillment_line
        return base + fulfillment_line(self.fulfillment) + "。" + detail


def _field(result: object, name: str, default=None):
    if isinstance(result, dict):
        return result.get(name, default)
    return getattr(result, name, default)


def summarize_validation(
    validation_results: list[object],
    *,
    error_count: int | None = None,
    warning_count: int | None = None,
) -> ValidationSummary:
    """按校验器保留最后一次结果，让 recheck 覆盖初检。"""
    final_results = final_validation_results(validation_results)

    measured_errors = sum(
        1 for result in final_results if _field(result, "has_error", False)
    )
    measured_warnings = sum(
        1
        for result in final_results
        if _field(result, "has_warning", False)
        and not _field(result, "has_error", False)
    )
    errors = max(measured_errors, error_count or 0)
    warnings = max(measured_warnings, warning_count or 0)
    total = len(final_results)
    return ValidationSummary(
        total=total,
        passed=max(0, total - errors - warnings),
        warnings=warnings,
        errors=errors,
    )


def final_validation_results(validation_results: list[object]) -> list[object]:
    """返回每个校验器最后一次结果，供 UI 与保存门禁共同使用。"""
    latest: dict[str, object] = {}
    for index, result in enumerate(validation_results):
        name = str(_field(result, "name", f"step_{index}"))
        latest[name.replace(" [recheck]", "")] = result
    return list(latest.values())


def _safe_name_slug(name: str, max_len: int = 40) -> str:
    value = _re.sub(r"[^\w\u4e00-\u9fff]", "_", name, flags=_re.UNICODE)
    return _re.sub(r"_+", "_", value).strip("_")[:max_len]


def retain_generation_blueprint(state: dict, fallback: dict | None = None) -> dict | None:
    """从已有产物或分片恢复可编辑草稿，不因校验结果丢弃数据。"""
    candidates = [state.get("final_blueprint"), state.get("merged_blueprint")]
    fragments = state.get("component_fragments") or {}
    diagnostics = state.get("component_diagnostics") or {}
    failed_rows = [row for diag in diagnostics.values()
                   for row in (diag.get("failed_implementations") or {}).values()
                   if isinstance(row, dict) and isinstance(row.get("geometry"), dict)]
    if failed_rows or (isinstance(fragments, dict) and any(isinstance(parts, list) and parts for parts in fragments.values())):
        draft = deepcopy(state.get("skeleton_blueprint") or {"meta": {}, "geometry": {}})
        geometry = draft.setdefault("geometry", {})
        for bucket in ("elements", "components"):
            geometry[bucket] = list(geometry.get(bucket) or [])
        for task_id, parts in fragments.items():
            diag = diagnostics.get(task_id) or {}
            component_ids = set(diag.get("components") or [])
            for entity in parts if isinstance(parts, list) else []:
                bucket = "components" if isinstance(entity, dict) and entity.get("id") in component_ids else "elements"
                geometry[bucket].append(deepcopy(entity))
            for resource in ("materials", "assets"):
                for name, definition in (diag.get(resource) or {}).items():
                    draft.setdefault(resource, {}).setdefault(name, deepcopy(definition))
        for row in failed_rows:
            for bucket in ("elements", "components"):
                parts = row["geometry"].get(bucket)
                if isinstance(parts, list):
                    geometry[bucket].extend(deepcopy(parts))
            for resource in ("materials", "assets"):
                definitions = row.get(resource)
                if isinstance(definitions, dict):
                    for name, definition in definitions.items():
                        draft.setdefault(resource, {}).setdefault(name, deepcopy(definition))
        candidates.append(draft)
    candidates.extend([fallback, state.get("skeleton_blueprint"), state.get("current_blueprint")])
    available = [value for value in candidates if isinstance(value, dict) and value]
    for blueprint in available:
        geometry = blueprint.get("geometry")
        if isinstance(geometry, dict) and any(isinstance(geometry.get(key), list) and geometry[key]
                                              for key in ("elements", "components")):
            return deepcopy(blueprint)
    return deepcopy(available[0]) if available else None


def prepare_blueprint_delivery(
    blueprint: dict,
    session_id: str,
    validation_results: list[object],
    *,
    status: str,
    error_count: int | None = None,
    warning_count: int | None = None,
    fulfillment: dict | None = None,
    validation_snapshot: dict | None = None,
) -> BlueprintDelivery:
    """保存已有实体；校验失败或证据不一致均保留为错误报告。"""
    if not isinstance(blueprint, dict):
        raise GenerationRejectedError("没有可保存的蓝图对象")
    meta = blueprint.get("meta")
    meta = meta if isinstance(meta, dict) else {}
    summary = summarize_validation(
        validation_results,
        error_count=error_count,
        warning_count=warning_count,
    )
    if validation_snapshot is not None:
        from app.agent.validation.diagnostics import VALIDATOR_VERSION, blueprint_fingerprint
        from app.agent.validation.diagnostics import step_result_to_dict
        evidence_results = [step_result_to_dict(result) for result in validation_results]
        if (validation_snapshot.get("blueprint_fingerprint") != blueprint_fingerprint(blueprint)
                or validation_snapshot.get("validator_version") != VALIDATOR_VERSION
                or validation_snapshot.get("results") != evidence_results
                or validation_snapshot.get("error_count", 0) != summary.errors
                or (validation_snapshot.get("design_hash") and (
                    meta.get("designHash") != validation_snapshot["design_hash"]
                    or meta.get("designRevision") != validation_snapshot["design_revision"]))
                or (fulfillment and fulfillment.get("blueprint_fingerprint") != blueprint_fingerprint(blueprint))):
            validation_results = [*validation_results, {
                "step": "delivery", "name": "validate_delivery_evidence",
                "output": "校验证据与当前交付内容不一致，请重新进行完整校验",
                "has_error": True, "has_warning": False,
            }]
            summary = summarize_validation(validation_results, error_count=summary.errors + 1,
                                           warning_count=summary.warnings)

    meta_name = str(meta.get("name") or "")
    display_name = compact_blueprint_title(meta_name)
    slug = _safe_name_slug(display_name)
    filename = f"{session_id}_{slug}.wild" if slug else f"{session_id}.wild"
    rel_path = f"{_dt.date.today():%Y-%m-%d}/{filename}"

    try:
        save_blueprint_file_as(blueprint, SCENES_DIR, rel_path)
    except Exception as exc:
        raise ArtifactSaveError(str(exc)) from exc

    geometry = blueprint.get("geometry")
    geometry = geometry if isinstance(geometry, dict) else {}
    return BlueprintDelivery(
        filename=rel_path,
        file_url=f"/api/scenes/{rel_path}",
        name=display_name,
        elements_count=len(geometry["elements"]) if isinstance(geometry.get("elements"), list) else 0,
        components_count=len(geometry["components"]) if isinstance(geometry.get("components"), list) else 0,
        validation=summary,
        fulfillment=fulfillment,
        validation_passed=(status == "complete" and summary.errors == 0 and summary.warnings <= WARNING_GATE_MAX
                           and (validation_snapshot is None or validation_snapshot.get("status") == "complete")),
        validation_errors=tuple(
            f"{_field(result, 'name', 'unknown')}: {_field(result, 'output', '')}"
            for result in final_validation_results(validation_results) if _field(result, "has_error", False)
        ),
    )


def commit_generation_result(
    session_id: str,
    request_id: str,
    blueprint: dict,
    validation_results: list[object],
    *,
    status: str,
    error_count: int | None = None,
    warning_count: int | None = None,
    fulfillment: dict | None = None,
    validation_snapshot: dict | None = None,
) -> BlueprintDelivery:
    """生成结果的单一幂等提交单元。

    - ``session_id`` 决定确定性文件名，``request_id`` 是幂等键：同一会话重复提交
      覆盖同一文件而非产生副本，因此断线重放或部分失败后的重试是安全的。
    - 顺序契约：先原子落盘 .wild（``prepare_blueprint_delivery`` 内部保证），再让
      调用方发布 ``blueprint_generated`` / ``agent_reply`` 终端事件；落盘失败抛
      ``ArtifactSaveError``，调用方不得继续发成功事件。
    - 校验未通过也保存已有实体，失败状态和错误报告随产物返回。
    """
    logger.info(f"[{request_id}] 提交生成结果: session={session_id}")
    if validation_snapshot is None:
        validation_results = [*validation_results, {
            "step": "delivery", "name": "validate_delivery_evidence",
            "output": "生成结果缺少完整校验快照，已有实体仍保留供查看",
            "has_error": True, "has_warning": False,
        }]
        status = "failed"
        error_count = (error_count or 0) + 1
    return prepare_blueprint_delivery(
        blueprint,
        session_id,
        validation_results,
        status=status,
        error_count=error_count,
        warning_count=warning_count,
        fulfillment=fulfillment,
        validation_snapshot=validation_snapshot,
    )
