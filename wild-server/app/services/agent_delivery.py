"""Blueprint 生成结果的统一校验门禁、保存和摘要出口。"""

from dataclasses import dataclass
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
    """生成结果有效，但服务端文件保存失败。"""


# 交付门禁的警告阈值：超过该值的 Blueprint 判定为“满屏警告”，即使没有 ❌
# 错误也拒绝交付，要求先进入回调修复；少量警告（正常生成的常见水平）不受影响。
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
    #: 🔴 P4 设计履约报告（`app.design.fulfillment.fulfillment_summary` 的形状）。
    #: 与 :attr:`validation` **分开**：validation 决定"能不能保存"，fulfillment 决定
    #: "用户要的东西兑现了没有"。旧调用方不传时为 ``None``，回复文案保持原样。
    fulfillment: dict | None = None

    @property
    def reply(self) -> str:
        base = (
            f"已生成 {self.name or '建筑'}（{self.elements_count} 元素 + "
            f"{self.components_count} 组件，校验 {self.validation.passed}✓ "
            f"{self.validation.warnings}⚠），已保存为 `{self.filename}`。"
        )
        if not self.fulfillment or not self.fulfillment.get("total"):
            return base
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

    errors = error_count if error_count is not None else sum(
        1 for result in final_results if _field(result, "has_error", False)
    )
    warnings = warning_count if warning_count is not None else sum(
        1
        for result in final_results
        if _field(result, "has_warning", False)
        and not _field(result, "has_error", False)
    )
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


def prepare_blueprint_delivery(
    blueprint: dict,
    session_id: str,
    validation_results: list[object],
    *,
    status: str,
    error_count: int | None = None,
    warning_count: int | None = None,
    fulfillment: dict | None = None,
) -> BlueprintDelivery:
    """只有完整通过最终校验的 Blueprint 才会写入场景目录。

    🔴 ``fulfillment``（P4 设计履约）**不参与门禁**：``open`` 的设计要求仍然交付，
    只在回复里如实展示缺口。把它并进 ``summary.errors`` 会让"合法但不完整"变成
    "不许保存"，与 P4 的交付政策相反。
    """
    summary = summarize_validation(
        validation_results,
        error_count=error_count,
        warning_count=warning_count,
    )
    if status != "complete" or summary.errors > 0:
        raise GenerationRejectedError(
            f"校验结果：{summary.passed}✓ {summary.warnings}⚠ {summary.errors}✗"
        )
    if summary.warnings > WARNING_GATE_MAX:
        raise GenerationRejectedError(
            f"校验警告过多（{summary.warnings} > {WARNING_GATE_MAX}），"
            f"生成结果仍有未解决的几何问题，已阻止保存和加载。"
        )

    meta_name = blueprint.get("meta", {}).get("name", "") or ""
    display_name = compact_blueprint_title(meta_name)
    slug = _safe_name_slug(display_name)
    filename = f"{session_id}_{slug}.wild" if slug else f"{session_id}.wild"
    rel_path = f"{_dt.date.today():%Y-%m-%d}/{filename}"

    try:
        save_blueprint_file_as(blueprint, SCENES_DIR, rel_path)
    except Exception as exc:
        raise ArtifactSaveError(str(exc)) from exc

    geometry = blueprint.get("geometry", {})
    return BlueprintDelivery(
        filename=rel_path,
        file_url=f"/api/scenes/{rel_path}",
        name=display_name,
        elements_count=len(geometry.get("elements", [])),
        components_count=len(geometry.get("components", [])),
        validation=summary,
        fulfillment=fulfillment,
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
) -> BlueprintDelivery:
    """生成结果的单一幂等提交单元。

    - ``session_id`` 决定确定性文件名，``request_id`` 是幂等键：同一会话重复提交
      覆盖同一文件而非产生副本，因此断线重放或部分失败后的重试是安全的。
    - 顺序契约：先原子落盘 .wild（``prepare_blueprint_delivery`` 内部保证），再让
      调用方发布 ``blueprint_generated`` / ``agent_reply`` 终端事件；落盘失败抛
      ``ArtifactSaveError``，调用方不得继续发成功事件。
    - 校验门禁不变：``status != "complete"`` 或存在错误时抛 ``GenerationRejectedError``；
      ``fulfillment`` 只进回复文案，不进门禁（P4）。
    """
    logger.info(f"[{request_id}] 提交生成结果: session={session_id}")
    return prepare_blueprint_delivery(
        blueprint,
        session_id,
        validation_results,
        status=status,
        error_count=error_count,
        warning_count=warning_count,
        fulfillment=fulfillment,
    )
