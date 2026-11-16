"""通用蓝图校验流水线；独立于模型资源和传输协议。"""
from dataclasses import dataclass
from loguru import logger
from app.domain.validation.spatial import fix_element_dimensions
from app.domain.validation.spatial import fix_element_elevations
from app.domain.validation.spatial import fix_material_references
from app.domain.validation.spatial import fix_opening_coords
from app.domain.validation.spatial import fix_opening_fit
from app.domain.validation.spatial import fix_roof_coverage
from app.domain.validation.spatial import fix_stair_alignment
from app.domain.validation.spatial import fix_wall_junctions
from app.domain.validation.spatial import validate_blueprint_structure
from app.domain.validation.spatial import validate_collision
from app.domain.validation.spatial import validate_element_dimensions
from app.domain.validation.spatial import validate_element_required_fields
from app.domain.validation.spatial import validate_model_quality
from app.domain.validation.spatial import validate_opening_coords
from app.domain.validation.spatial import validate_opening_fit
from app.domain.validation.spatial import validate_reference_integrity
from app.domain.validation.spatial import validate_roof_coverage
from app.domain.validation.spatial import validate_roof_top_coverage
from app.domain.validation.spatial import validate_stacked_member_containment
from app.domain.validation.spatial import validate_stair_alignment
from app.domain.validation.spatial import validate_wall_junctions


@dataclass
class PipelineStepResult:
    """单个流水线步骤的执行结果"""
    step: int | str
    name: str
    output: str
    has_error: bool
    has_warning: bool
    issues: list[dict] | None = None


def _run_tool(tool_fn, blueprint: dict) -> str:
    """直接调用校验函数；兼容外层提供的工具包装。"""
    fn = getattr(tool_fn, "func", tool_fn)
    return fn(blueprint)


def _final_errors(results: list[PipelineStepResult]) -> list[PipelineStepResult]:
    """按校验器去重，只保留每组最后一条——修复后的 recheck 覆盖初检错误。"""
    last: dict[str, PipelineStepResult] = {}
    for r in results:
        last[r.name.replace(" [recheck]", "")] = r
    return [r for r in last.values() if r.has_error]


def _severity_from_text(output: str) -> tuple[bool, bool]:
    """从校验器文本标记收敛出结构化严重度。

    文本同时包含 ❌ 与 ⚠️ 时按错误计；判定集中在这里，后续如需把特定
    警告升级为错误只需改这一处，不必逐个触碰校验器输出。
    """
    return ("❌" in output, "⚠️" in output)


def run_validation_pipeline(
    blueprint: dict, *, log_steps: bool = True, auto_fix: bool = True
) -> list[PipelineStepResult]:
    """按固定顺序执行所有校验 + 自动修正步骤，返回每步结果。

    ``log_steps``：交付路径要保持逐步骤日志（线上排查靠它）；编译期复用这条流水线
    产缺陷时（``app/domain/compilation/pipeline_defects.py``）一次生成里
    会调它很多次，逐步骤日志会把真正的编译诊断淹掉，所以那边传 False。
    ``auto_fix=False`` 只运行原校验器，不执行任何 fix；用于编译与候选验收。
    """
    results: list[PipelineStepResult] = []

    def run_step(step: int, name: str, tool_fn, bp: dict) -> PipelineStepResult:
        """执行校验工具，把文本标记转换成统一的步骤状态。"""
        output = _run_tool(tool_fn, bp)
        has_error, has_warning = _severity_from_text(output)
        r = PipelineStepResult(
            step=step,
            name=name,
            output=output,
            has_error=has_error,
            has_warning=has_warning,
        )
        results.append(r)
        if log_steps:
            if has_error:
                severity = "❌ ERROR"
            elif has_warning:
                severity = "⚠️ WARN"
            else:
                severity = "✅ OK"
            logger.info(f"[Pipeline Step {step}] {name}: {severity}")
        return r

    def skip_step(step: int, name: str, reason: str) -> PipelineStepResult:
        """记录因上游条件不满足而未执行的步骤，保持流水线可追踪。"""
        r = PipelineStepResult(
            step=step,
            name=name,
            output=f"⏭️  跳过（{reason}）",
            has_error=False,
            has_warning=False,
        )
        if auto_fix or not name.startswith("fix_"):
            results.append(r)
        return r

    # ── Step 1: 顶层结构 ──
    r1 = run_step(
        1, "validate_blueprint_structure", validate_blueprint_structure, blueprint
    )
    if r1.has_error:
        for s, n in [
            (2, "validate_element_required_fields"),
            (3, "validate_reference_integrity"),
            (4, "validate_opening_coords"),
            ("4b", "validate_opening_fit"),
            (5, "validate_wall_junctions"),
            (6, "validate_stair_alignment"),
            (7, "validate_roof_coverage"),
            ("7b", "validate_element_dimensions"),
            (8, "fix_opening_coords"),
            ("8b", "fix_opening_fit"),
            ("8c", "fix_stair_alignment"),
            ("8d", "fix_element_dimensions"),
            ("8e", "fix_roof_coverage"),
            ("8f", "fix_wall_junctions"),
            (9, "validate_collision"),
        ]:
            skip_step(s, n, "Step 1 结构校验未通过")
        return results

    # ── Step 2: 必填字段 ──
    r2 = run_step(
        2,
        "validate_element_required_fields",
        validate_element_required_fields,
        blueprint,
    )

    # ── Step 3: 引用完整性 ──
    r3 = run_step(
        3, "validate_reference_integrity", validate_reference_integrity, blueprint
    )
    if auto_fix and r3.has_error:
        fix_output = _run_tool(fix_material_references, blueprint)
        fix_error, fix_warning = _severity_from_text(fix_output)
        results.append(
            PipelineStepResult(
                step="3b",
                name="fix_material_references",
                output=fix_output,
                has_error=fix_error,
                has_warning=fix_warning,
            )
        )
        reference_output = _run_tool(validate_reference_integrity, blueprint)
        recheck_error, recheck_warning = _severity_from_text(reference_output)
        results.append(
            PipelineStepResult(
                step="3c",
                name="validate_reference_integrity [recheck]",
                output=reference_output,
                has_error=recheck_error,
                has_warning=recheck_warning,
            )
        )

    if r2.has_error:
        for s, n in [
            (4, "validate_opening_coords"),
            ("4b", "validate_opening_fit"),
            (5, "validate_wall_junctions"),
            (6, "validate_stair_alignment"),
            (7, "validate_roof_coverage"),
            ("7b", "validate_element_dimensions"),
            (8, "fix_opening_coords"),
            ("8b", "fix_opening_fit"),
            ("8c", "fix_stair_alignment"),
            ("8d", "fix_element_dimensions"),
            ("8e", "fix_roof_coverage"),
            ("8f", "fix_wall_junctions"),
            (9, "validate_collision"),
        ]:
            skip_step(s, n, "Step 2 必填字段校验未通过")
        return results

    # ── Step 4: 门窗坐标 ──
    r4 = run_step(4, "validate_opening_coords", validate_opening_coords, blueprint)
    # ── Step 4b: 开口越界 ──
    r4b = run_step("4b", "validate_opening_fit", validate_opening_fit, blueprint)
    # ── Step 5: 墙体连接 ──
    r5 = run_step(5, "validate_wall_junctions", validate_wall_junctions, blueprint)
    # ── Step 6: 楼梯对齐 ──
    r6 = run_step(6, "validate_stair_alignment", validate_stair_alignment, blueprint)
    # ── Step 7: 屋顶覆盖 ──
    r7 = run_step(7, "validate_roof_coverage", validate_roof_coverage, blueprint)
    # ── Step 7b: 构件尺寸 ──
    r7b = run_step(
        "7b", "validate_element_dimensions", validate_element_dimensions, blueprint
    )
    # ── Step 7c: 重复骨架质量门禁 ──
    run_step("7c", "validate_model_quality", validate_model_quality, blueprint)
    # ── Step 7d: 贯通构件逐层收进门禁 ──
    run_step(
        "7d",
        "validate_stacked_member_containment",
        validate_stacked_member_containment,
        blueprint,
    )
    # ── Step 7e: 墙顶 - 屋顶反向覆盖（多体量漏屋顶）──
    # 只报 ⚠️，不参与 8e 的 fix_roof_coverage（修不了"少一块屋顶"，
    # 补屋顶是生成侧的事），也不进 _final_errors，因此不阻断交付。
    run_step("7e", "validate_roof_top_coverage", validate_roof_top_coverage, blueprint)

    # ── Step 8: 自动修正门窗坐标 ──
    if auto_fix and (
        r4.has_warning or r4.has_error or r4b.has_error or r4b.has_warning
    ):
        _run_fix_and_rechecks(
            blueprint,
            results,
            8,
            ("fix_opening_coords", fix_opening_coords),
            [
                ("validate_opening_coords [recheck]", validate_opening_coords),
                ("validate_opening_fit [recheck]", validate_opening_fit),
            ],
        )
    else:
        skip_step(8, "fix_opening_coords", "Step 4/4b 门窗坐标无问题")

    # ── Step 8b: 自动修正开口越界 ──
    if auto_fix and r4b.has_error:
        _run_fix_and_rechecks(
            blueprint,
            results,
            "8b",
            ("fix_opening_fit", fix_opening_fit),
            [("validate_opening_fit [recheck]", validate_opening_fit)],
        )
    else:
        skip_step("8b", "fix_opening_fit", "Step 4b 开口越界无严重问题")

    # ── Step 8c: 自动修正楼梯对齐 ──
    if auto_fix and (r6.has_warning or r6.has_error):
        _run_fix_and_rechecks(
            blueprint,
            results,
            "8c",
            ("fix_stair_alignment", fix_stair_alignment),
            [("validate_stair_alignment [recheck]", validate_stair_alignment)],
        )
    else:
        skip_step("8c", "fix_stair_alignment", "Step 6 楼梯对齐无问题")

    # ── Step 8d: 自动修正构件尺寸 ──
    if auto_fix and r7b.has_error:
        _run_fix_and_rechecks(
            blueprint,
            results,
            "8d",
            ("fix_element_dimensions", fix_element_dimensions),
            [("validate_element_dimensions [recheck]", validate_element_dimensions)],
        )
    else:
        skip_step("8d", "fix_element_dimensions", "Step 7b 构件尺寸无严重异常")

    # ── Step 8e: 自动修正屋顶覆盖 ──
    if auto_fix and (r7.has_error or r7.has_warning):
        _run_fix_and_rechecks(
            blueprint,
            results,
            "8e",
            ("fix_roof_coverage", fix_roof_coverage),
            [("validate_roof_coverage [recheck]", validate_roof_coverage)],
        )
    else:
        skip_step("8e", "fix_roof_coverage", "Step 7 屋顶覆盖无问题")

    # ── Step 8f: 自动对齐墙体端点 ──
    if auto_fix and (r5.has_warning or r5.has_error):
        _run_fix_and_rechecks(
            blueprint,
            results,
            "8f",
            ("fix_wall_junctions", fix_wall_junctions),
            [
                ("validate_wall_junctions [recheck]", validate_wall_junctions),
                ("validate_model_quality [recheck]", validate_model_quality),
            ],
        )
    else:
        skip_step("8f", "fix_wall_junctions", "Step 5 墙体端点无问题")

    # ── Step 9: 碰撞检测 ──
    r9 = run_step(9, "validate_collision", validate_collision, blueprint)

    # ── Step 9b: 自动修正竖向构件高程（悬空/穿入地板）──
    if auto_fix and (r9.has_warning or r9.has_error):
        _run_fix_and_rechecks(
            blueprint,
            results,
            "9b",
            ("fix_element_elevations", fix_element_elevations),
            [("validate_collision [recheck]", validate_collision)],
        )
    else:
        skip_step("9b", "fix_element_elevations", "Step 9 碰撞检测无问题")

    # ── Step 10: 组件专用校验兜底 ──
    # gen→val 已执行一次，这里针对合并、配额裁剪和自动修正后的最终蓝图复检，
    # 防止合法引用但超出父墙范围的组件流到前端编译器。
    _validate_component_placements(blueprint, results, run_step, auto_fix)

    if auto_fix:
        # 后面的修复也可能改变前面已检查的宿主/尺寸，完整复查实际最终产物。
        for result in run_validation_pipeline(
            blueprint, log_steps=log_steps, auto_fix=False
        ):
            if result.name.startswith("validate_"):
                result.name += " [recheck]"
                results.append(result)
    return results


def _run_fix_and_rechecks(blueprint, results, step, fix, checks):
    """执行一个已有修复工具及其复检，保留步骤名称、顺序和状态标记。"""
    fix_name, fix_tool = fix
    for name, tool in [(fix_name, fix_tool), *checks]:
        output = _run_tool(tool, blueprint)
        results.append(
            PipelineStepResult(
                step=step,
                name=name,
                output=output,
                has_error="❌" in output,
                has_warning="⚠️" in output,
            )
        )


def _validate_component_placements(blueprint, results, run_step, auto_fix):
    """按实际构件类型运行专用校验及必要的修复复检。"""
    from app.domain.validation.components import COMPONENT_TOOLS
    from app.domain.validation.components import fix_component
    from app.domain.validation.components import validate_component

    entity_types = {
        str(item.get("type"))
        for item in [
            *blueprint.get("geometry", {}).get("elements", []),
            *blueprint.get("geometry", {}).get("components", []),
        ]
        if isinstance(item, dict) and item.get("type")
    }

    component_types = sorted((entity_types & set(COMPONENT_TOOLS)) - {"roof"})
    for index, component_type in enumerate(component_types, start=1):
        validator_name = f"validate_{component_type}_placement"
        result = run_step(
            f"10.{index}",
            validator_name,
            lambda bp, current=component_type: validate_component(current, bp),
            blueprint,
        )
        if not auto_fix or not result.has_error:
            continue
        fix_output = fix_component(component_type, blueprint)
        fix_error, fix_warning = _severity_from_text(fix_output)
        results.append(
            PipelineStepResult(
                step=f"10.{index}",
                name=f"fix_{component_type}_placement",
                output=fix_output,
                has_error=fix_error,
                has_warning=fix_warning,
            )
        )
        recheck_output = validate_component(component_type, blueprint)
        recheck_error, recheck_warning = _severity_from_text(recheck_output)
        results.append(
            PipelineStepResult(
                step=f"10.{index}",
                name=f"{validator_name} [recheck]",
                output=recheck_output,
                has_error=recheck_error,
                has_warning=recheck_warning,
            )
        )
