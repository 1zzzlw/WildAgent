"""校验报告及其汇总规则，供验收和交付共同使用。"""
from dataclasses import dataclass


WARNING_GATE_MAX = 20


@dataclass(frozen=True)
class ValidationSummary:
    total: int
    passed: int
    warnings: int
    errors: int


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
