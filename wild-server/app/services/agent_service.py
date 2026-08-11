"""
Agent Service —— Agent 生命周期管理和对话入口

职责：组装 spec_loader + tools + prompt + llm，对外提供统一的 query_structured() 接口。

一份 prompt + 一份入口方法，同时覆盖三种意图：
  - 生成类（从零创建）→ 输出完整 Blueprint JSON
  - 修改类（增量修改）→ 输出 ScenePatch JSON（operations + summary）
  - 对话类（纯聊天）→ 纯文本

AI 在 prompt 内自行判断意图，选择输出格式。场景上下文通过 user message 传入。

校验流水线（服务端强制执行，不依赖 LLM 自由调用顺序）：
  Structure → Schema → Reference → Geometry → Fix → Collision

升级路径（每次只改内部，query_structured() 接口和 ws_agent.py 不动）：
  现在   → FileSpecLoader + create_agent + server-side pipeline
  以后1  → RAGSpecLoader（只改 loader 一行）
  以后2  → LangGraph graph.ainvoke()（只改编排，tools + pipeline 复用）
"""
from dataclasses import dataclass, field
import math
from pathlib import Path
from copy import deepcopy
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from langchain.agents import create_agent
from langchain_core.callbacks import AsyncCallbackHandler
from loguru import logger

from config import config
from app.agent.model_client import create_llm, message_texts as _message_texts
from app.agent.prompts import (
    build_material_optimization_prompt,
    build_patch_recovery_prompt,
    build_system_prompt,
)
from app.spec.loader import (
    FileSpecLoader,
    RAGSpecLoader,
    SpecQuery,
    collect_markdown_paths,
    create_embedding_function,
)
from app.tools.spatial_tools import (
    fix_element_dimensions,
    fix_element_elevations,
    fix_material_references,
    fix_opening_coords,
    fix_opening_fit,
    fix_roof_coverage,
    fix_stair_alignment,
    fix_wall_junctions,
    get_wall_bounding_box,
    validate_blueprint_structure,
    validate_collision,
    validate_element_dimensions,
    validate_element_required_fields,
    validate_model_quality,
    validate_opening_coords,
    validate_opening_fit,
    validate_reference_integrity,
    validate_roof_coverage,
    validate_stair_alignment,
    validate_wall_junctions,
)
from app.utils.blueprint_parser import (
    extract_blueprint_from_text,
    extract_patch_from_text,
    normalize_blueprint_input,
    validate_blueprint_schema,
)

# ---------- 规范文档路径 ----------
_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent  # wild-server/
_KB = _SERVER_ROOT / "storage" / "knowledge_base"

BASE_SPEC_PATHS = [
    _KB / "BLUEPRINT-SPEC-MINIMAL.md",
]

def get_rag_spec_paths() -> list[Path]:
    """扫描知识库 Markdown，并排除已经完整注入的最小规范。"""
    return collect_markdown_paths(_KB, exclude=BASE_SPEC_PATHS)

@dataclass
class PipelineStepResult:
    """单个流水线步骤的执行结果"""
    step: int | str
    name: str
    output: str
    has_error: bool
    has_warning: bool

@dataclass
class QueryResult:
    """query_structured() 的结构化返回结果

    - text:              完整 LLM 回复文本（始终存在）
    - blueprint:         提取的 Blueprint dict（生成类，可能为 None）
    - patch:             提取的 ScenePatch dict（修改类，可能为 None）
    - error:             致命错误描述（无错误时为 None）
    - pipeline_results:  各流水线步骤的执行结果列表
    """
    text: str
    blueprint: dict | None = None
    patch: dict | None = None
    error: str | None = None
    pipeline_results: list[PipelineStepResult] = field(default_factory=list)
    structured_source: str | None = None
    structured_recovery_used: bool = False


def _extract_response_artifacts(
    content: str,
    reasoning: str,
    *,
    prefer_patch: bool = False,
) -> tuple[dict | None, dict | None, str | None]:
    """独立提取 Blueprint/ScenePatch，避免用 Blueprint 结果门控 Patch。"""
    patches: list[tuple[str, dict]] = []
    blueprints: list[tuple[str, dict]] = []
    for source, text in (("content", content), ("reasoning", reasoning)):
        patch = extract_patch_from_text(text) if text else None
        if patch is not None:
            patches.append((source, patch))
        if not text:
            continue
        blueprint = extract_blueprint_from_text(text)
        if blueprint is not None:
            blueprints.append((source, blueprint))
    if prefer_patch and patches:
        source, patch = patches[0]
        return None, patch, source
    if blueprints:
        source, blueprint = blueprints[0]
        return blueprint, None, source
    if patches:
        source, patch = patches[0]
        return None, patch, source
    return None, None, None


class _ReasoningStreamCallback(AsyncCallbackHandler):
    """从模型 token 回调中提取并适度合并真实 ``reasoning_content``。"""

    def __init__(self, emit: Callable[[str], Awaitable[None]]):
        self._emit = emit
        self._buffer = ""

    async def on_llm_new_token(
        self,
        token: str,
        *,
        chunk: Any = None,
        **kwargs: Any,
    ) -> None:
        message = getattr(chunk, "message", None)
        additional_kwargs = getattr(message, "additional_kwargs", {})
        reasoning_delta = additional_kwargs.get("reasoning_content", "")
        if not reasoning_delta:
            return

        self._buffer += reasoning_delta
        if len(self._buffer) >= 24 or self._buffer.endswith(("\n", "。", "！", "？")):
            await self.flush()

    async def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        await self.flush()

    async def flush(self) -> None:
        if not self._buffer:
            return
        delta = self._buffer
        self._buffer = ""
        await self._emit(delta)


def _run_tool(tool_fn, blueprint: dict) -> str:
    """调用 @tool 装饰的函数（绕过 LangChain .invoke 包装）"""
    fn = getattr(tool_fn, "func", tool_fn)
    return fn(blueprint)


def _final_errors(results: list[PipelineStepResult]) -> list[PipelineStepResult]:
    """按校验器去重，只保留每组最后一条——修复后的 recheck 覆盖初检错误。"""
    last: dict[str, PipelineStepResult] = {}
    for r in results:
        last[r.name.replace(" [recheck]", "")] = r
    return [r for r in last.values() if r.has_error]


def run_validation_pipeline(blueprint: dict) -> list[PipelineStepResult]:
    """按固定顺序执行所有校验 + 自动修正步骤，返回每步结果。"""
    results: list[PipelineStepResult] = []

    def run_step(step: int, name: str, tool_fn, bp: dict) -> PipelineStepResult:
        """执行校验工具，把文本标记转换成统一的步骤状态。"""
        output = _run_tool(tool_fn, bp)
        has_error = "❌" in output
        has_warning = "⚠️" in output
        r = PipelineStepResult(step=step, name=name, output=output,
                               has_error=has_error, has_warning=has_warning)
        results.append(r)
        logger.info(
            f"[Pipeline Step {step}] {name}: "
            f"{'❌ ERROR' if has_error else '⚠️ WARN' if has_warning else '✅ OK'}"
        )
        return r

    def skip_step(step: int, name: str, reason: str) -> PipelineStepResult:
        """记录因上游条件不满足而未执行的步骤，保持流水线可追踪。"""
        r = PipelineStepResult(step=step, name=name,
                               output=f"⏭️  跳过（{reason}）",
                               has_error=False, has_warning=False)
        results.append(r)
        return r

    # ── Step 1: 顶层结构 ──
    r1 = run_step(1, "validate_blueprint_structure", validate_blueprint_structure, blueprint)
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
    r2 = run_step(2, "validate_element_required_fields", validate_element_required_fields, blueprint)

    # ── Step 3: 引用完整性 ──
    r3 = run_step(3, "validate_reference_integrity", validate_reference_integrity, blueprint)
    if r3.has_error:
        fix_output = _run_tool(fix_material_references, blueprint)
        results.append(PipelineStepResult(
            step="3b", name="fix_material_references", output=fix_output,
            has_error="❌" in fix_output, has_warning="⚠️" in fix_output,
        ))
        reference_output = _run_tool(validate_reference_integrity, blueprint)
        results.append(PipelineStepResult(
            step="3c", name="validate_reference_integrity [recheck]", output=reference_output,
            has_error="❌" in reference_output, has_warning="⚠️" in reference_output,
        ))

    if r2.has_error:
        for s, n in [
            (4, "validate_opening_coords"), ("4b", "validate_opening_fit"),
            (5, "validate_wall_junctions"), (6, "validate_stair_alignment"),
            (7, "validate_roof_coverage"), ("7b", "validate_element_dimensions"),
            (8, "fix_opening_coords"), ("8b", "fix_opening_fit"),
            ("8c", "fix_stair_alignment"), ("8d", "fix_element_dimensions"),
            ("8e", "fix_roof_coverage"), ("8f", "fix_wall_junctions"),
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
    r7b = run_step("7b", "validate_element_dimensions", validate_element_dimensions, blueprint)
    # ── Step 7c: 重复骨架质量门禁 ──
    run_step("7c", "validate_model_quality", validate_model_quality, blueprint)

    # ── Step 8: 自动修正门窗坐标 ──
    if r4.has_warning or r4.has_error or r4b.has_error or r4b.has_warning:
        fix_out = _run_tool(fix_opening_coords, blueprint)
        results.append(PipelineStepResult(
            step=8, name="fix_opening_coords", output=fix_out,
            has_error="❌" in fix_out, has_warning="⚠️" in fix_out,
        ))
        for chk_fn, chk_name in [
            (validate_opening_coords, "validate_opening_coords [recheck]"),
            (validate_opening_fit, "validate_opening_fit [recheck]"),
        ]:
            out = _run_tool(chk_fn, blueprint)
            results.append(PipelineStepResult(
                step=8, name=chk_name, output=out,
                has_error="❌" in out, has_warning="⚠️" in out,
            ))
    else:
        skip_step(8, "fix_opening_coords", "Step 4/4b 门窗坐标无问题")

    # ── Step 8b: 自动修正开口越界 ──
    if r4b.has_error:
        fix_out = _run_tool(fix_opening_fit, blueprint)
        results.append(PipelineStepResult(
            step="8b", name="fix_opening_fit", output=fix_out,
            has_error="❌" in fix_out, has_warning="⚠️" in fix_out,
        ))
        recheck_out = _run_tool(validate_opening_fit, blueprint)
        results.append(PipelineStepResult(
            step="8b", name="validate_opening_fit [recheck]", output=recheck_out,
            has_error="❌" in recheck_out, has_warning="⚠️" in recheck_out,
        ))
    else:
        skip_step("8b", "fix_opening_fit", "Step 4b 开口越界无严重问题")

    # ── Step 8c: 自动修正楼梯对齐 ──
    if r6.has_warning or r6.has_error:
        fix_out = _run_tool(fix_stair_alignment, blueprint)
        results.append(PipelineStepResult(
            step="8c", name="fix_stair_alignment", output=fix_out,
            has_error="❌" in fix_out, has_warning="⚠️" in fix_out,
        ))
        recheck_out = _run_tool(validate_stair_alignment, blueprint)
        results.append(PipelineStepResult(
            step="8c", name="validate_stair_alignment [recheck]", output=recheck_out,
            has_error="❌" in recheck_out, has_warning="⚠️" in recheck_out,
        ))
    else:
        skip_step("8c", "fix_stair_alignment", "Step 6 楼梯对齐无问题")

    # ── Step 8d: 自动修正构件尺寸 ──
    if r7b.has_error:
        fix_out = _run_tool(fix_element_dimensions, blueprint)
        results.append(PipelineStepResult(
            step="8d", name="fix_element_dimensions", output=fix_out,
            has_error="❌" in fix_out, has_warning="⚠️" in fix_out,
        ))
        recheck_out = _run_tool(validate_element_dimensions, blueprint)
        results.append(PipelineStepResult(
            step="8d", name="validate_element_dimensions [recheck]", output=recheck_out,
            has_error="❌" in recheck_out, has_warning="⚠️" in recheck_out,
        ))
    else:
        skip_step("8d", "fix_element_dimensions", "Step 7b 构件尺寸无严重异常")

    # ── Step 8e: 自动修正屋顶覆盖 ──
    if r7.has_error or r7.has_warning:
        fix_out = _run_tool(fix_roof_coverage, blueprint)
        results.append(PipelineStepResult(
            step="8e", name="fix_roof_coverage", output=fix_out,
            has_error="❌" in fix_out, has_warning="⚠️" in fix_out,
        ))
        recheck_out = _run_tool(validate_roof_coverage, blueprint)
        results.append(PipelineStepResult(
            step="8e", name="validate_roof_coverage [recheck]", output=recheck_out,
            has_error="❌" in recheck_out, has_warning="⚠️" in recheck_out,
        ))
    else:
        skip_step("8e", "fix_roof_coverage", "Step 7 屋顶覆盖无问题")

    # ── Step 8f: 自动对齐墙体端点 ──
    if r5.has_warning or r5.has_error:
        fix_out = _run_tool(fix_wall_junctions, blueprint)
        results.append(PipelineStepResult(
            step="8f", name="fix_wall_junctions", output=fix_out,
            has_error="❌" in fix_out, has_warning="⚠️" in fix_out,
        ))
        recheck_out = _run_tool(validate_wall_junctions, blueprint)
        results.append(PipelineStepResult(
            step="8f", name="validate_wall_junctions [recheck]", output=recheck_out,
            has_error="❌" in recheck_out, has_warning="⚠️" in recheck_out,
        ))
    else:
        skip_step("8f", "fix_wall_junctions", "Step 5 墙体端点无问题")

    # ── Step 9: 碰撞检测 ──
    r9 = run_step(9, "validate_collision", validate_collision, blueprint)

    # ── Step 9b: 自动修正竖向构件高程（悬空/穿入地板）──
    if r9.has_warning or r9.has_error:
        fix_out = _run_tool(fix_element_elevations, blueprint)
        results.append(PipelineStepResult(
            step="9b", name="fix_element_elevations", output=fix_out,
            has_error="❌" in fix_out, has_warning="⚠️" in fix_out,
        ))
        recheck_out = _run_tool(validate_collision, blueprint)
        results.append(PipelineStepResult(
            step="9b", name="validate_collision [recheck]", output=recheck_out,
            has_error="❌" in recheck_out, has_warning="⚠️" in recheck_out,
        ))
    else:
        skip_step("9b", "fix_element_elevations", "Step 9 碰撞检测无问题")

    # ── Step 10: 组件专用校验兜底 ──
    # gen→val 已执行一次，这里针对合并、配额裁剪和自动修正后的最终蓝图复检，
    # 防止合法引用但超出父墙范围的组件流到前端编译器。
    from app.tools.component_tools import COMPONENT_TOOLS, fix_component, validate_component

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
        if not result.has_error:
            continue
        fix_output = fix_component(component_type, blueprint)
        results.append(PipelineStepResult(
            step=f"10.{index}",
            name=f"fix_{component_type}_placement",
            output=fix_output,
            has_error="❌" in fix_output,
            has_warning="⚠️" in fix_output,
        ))
        recheck_output = validate_component(component_type, blueprint)
        results.append(PipelineStepResult(
            step=f"10.{index}",
            name=f"{validator_name} [recheck]",
            output=recheck_output,
            has_error="❌" in recheck_output,
            has_warning="⚠️" in recheck_output,
        ))

    return results


_MATERIAL_REFERENCE_FIELDS = (
    "material", "frameMaterial", "leafMaterial", "glassMaterial",
    "supportMaterial", "railingMaterial", "capMaterial",
    "baseMaterial", "shadeMaterial",
)
_TUNABLE_MATERIAL_FIELDS = (
    "baseColor", "roughness", "metallic", "albedo", "emissive",
    "opacity", "normalScale", "uvScale",
)
_MATERIAL_OPTIMIZATION_SUBJECTS = (
    "材质", "纹理", "贴图", "质感", "PBR", "pbr", "粗糙度",
    "金属度", "法线强度", "纹理比例",
)
_MATERIAL_OPTIMIZATION_ACTIONS = (
    "优化", "提升", "增强", "调整", "改善", "升级", "更真实", "真实一点",
)


def _is_material_optimization_request(message: str) -> bool:
    return (
        any(subject in message for subject in _MATERIAL_OPTIMIZATION_SUBJECTS)
        and any(action in message for action in _MATERIAL_OPTIMIZATION_ACTIONS)
    )


def _normalized_selection(selection: list[str] | None) -> list[str]:
    result: list[str] = []
    for item in selection or []:
        if isinstance(item, str) and item.strip() and item not in result:
            result.append(item)
    return result


def _material_display_fields(material: object) -> dict:
    """只把可调数值和资产引用交给模型，不暴露 Base64 或图片 URL。"""
    if not isinstance(material, dict):
        return {}
    fields = {
        key: material[key]
        for key in (*_TUNABLE_MATERIAL_FIELDS, "textureSet")
        if key in material
    }
    if isinstance(material.get("textures"), dict):
        fields["textureChannels"] = sorted(material["textures"])
    if material.get("embeddedImage"):
        fields["embeddedImage"] = "legacy-present"
    return fields


def _build_scene_summary(
    blueprint: dict,
    selection: list[str] | None = None,
) -> str:
    """从 Blueprint 生成场景摘要文本（注入 user message 供 AI 参考）"""
    geometry = blueprint.get("geometry", {})
    elements = geometry.get("elements", [])
    components = geometry.get("components", [])
    lines = [f"当前场景包含 {len(elements)} 个基础构件和 {len(components)} 个组合构件："]
    for el in elements:
        el_id = el.get("id", "?")
        el_type = el.get("type", "?")
        extras = []
        if el_type == "wall":
            extras.append(f"from={el.get('from', '?')}, to={el.get('to', '?')}")
            extras.append(f"thickness={el.get('thickness', '?')}")
        elif el_type == "column":
            extras.append(f"base={el.get('base', '?')}, height={el.get('height','?')}")
        elif el_type == "roof":
            extras.append(
                f"position={el.get('position', '?')}, "
                f"span={el.get('span','?')}, depth={el.get('depth','?')}"
            )
        elif el_type == "floor":
            extras.append(f"from={el.get('from', '?')}, to={el.get('to', '?')}")
        elif el_type == "opening":
            extras.append(
                f"parentWall={el.get('parentWall','?')}, from={el.get('from','?')}, "
                f"width={el.get('width','?')}, height={el.get('height','?')}"
            )
        else:
            for field_name in ("position", "base", "dimensions", "width", "height", "depth"):
                if field_name in el:
                    extras.append(f"{field_name}={el[field_name]}")
        lines.append(
            f"  - [{el_id}] type={el_type}"
            + (f" ({'; '.join(extras)})" if extras else "")
        )
    for component in components:
        component_id = component.get("id", "?")
        component_type = component.get("type", "?")
        extras = []
        if component_type in {"door", "window"}:
            extras.append(f"parentWall={component.get('parentWall', '?')}")
            extras.append(f"from={component.get('from', '?')}")
            extras.append(
                f"width={component.get('width', '?')}, height={component.get('height', '?')}"
            )
        elif component_type == "railing":
            extras.append(f"pathPoints={len(component.get('path', []))}")
        lines.append(
            f"  - [component:{component_id}] type={component_type}"
            + (f" ({'; '.join(extras)})" if extras else "")
        )
    materials = blueprint.get("materials", {})
    if materials:
        lines.append(f"已有材质: {', '.join(materials.keys())}")
    assets = blueprint.get("assets", {})
    if assets:
        lines.append(f"已有 PBR 资产: {', '.join(assets.keys())}")
    selected_ids = _normalized_selection(selection)
    if selected_ids:
        lines.append(f"当前选中构件: {', '.join(selected_ids)}")
        entities = {
            item.get("id"): item
            for item in [*elements, *components]
            if isinstance(item, dict) and item.get("id")
        }
        for entity_id in selected_ids:
            entity = entities.get(entity_id)
            if entity is None:
                lines.append(f"  - [{entity_id}] 不存在于当前 Blueprint")
                continue
            material_refs = {
                field_name: entity[field_name]
                for field_name in _MATERIAL_REFERENCE_FIELDS
                if isinstance(entity.get(field_name), str) and entity[field_name]
            }
            lines.append(
                f"  - [{entity_id}] 可调材质字段: "
                + (str(material_refs) if material_refs else "无")
            )
            for field_name, material_name in material_refs.items():
                material = materials.get(material_name)
                lines.append(
                    f"    {field_name}={material_name}: "
                    f"{_material_display_fields(material)}"
                )
                texture_set = material.get("textureSet") if isinstance(material, dict) else None
                asset = assets.get(texture_set) if isinstance(texture_set, str) else None
                if isinstance(asset, dict):
                    lines.append(
                        f"      asset={texture_set}, maps={sorted(asset.get('maps', {}))}, "
                        f"license={asset.get('license', '?')}"
                    )
    return "\n".join(lines)


def _is_finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _validate_material_tuning_changes(changes: object, prefix: str) -> list[str]:
    if not isinstance(changes, dict) or not changes:
        return [f"{prefix} 必须是非空对象"]
    issues: list[str] = []
    unknown = sorted(set(changes) - set(_TUNABLE_MATERIAL_FIELDS))
    if unknown:
        issues.append(f"{prefix} 包含不允许的字段: {unknown}")

    for field_name in ("roughness", "metallic", "albedo", "opacity"):
        if field_name in changes and not (
            _is_finite_number(changes[field_name])
            and 0 <= changes[field_name] <= 1
        ):
            issues.append(f"{prefix}.{field_name} 必须是 0–1 有限数字")
    if "normalScale" in changes and not (
        _is_finite_number(changes["normalScale"])
        and 0 <= changes["normalScale"] <= 4
    ):
        issues.append(f"{prefix}.normalScale 必须是 0–4 有限数字")
    for field_name in ("baseColor", "emissive"):
        value = changes.get(field_name)
        if field_name in changes and not (
            isinstance(value, list)
            and len(value) == 3
            and all(_is_finite_number(channel) and 0 <= channel <= 1 for channel in value)
        ):
            issues.append(f"{prefix}.{field_name} 必须是 3 个 0–1 有限数字")
    uv_scale = changes.get("uvScale")
    if "uvScale" in changes and not (
        isinstance(uv_scale, list)
        and len(uv_scale) == 2
        and all(_is_finite_number(value) and 0 < value <= 64 for value in uv_scale)
    ):
        issues.append(f"{prefix}.uvScale 必须是两个 0–64 的正有限数字")
    return issues


def _validate_material_optimization_patch(
    patch: dict,
    selection: list[str],
) -> list[str]:
    """材质优化模式只能作用于选中目标，并且只能使用 tune_material。"""
    selected_ids = set(selection)
    if not selected_ids:
        return ["材质优化前必须先选中一个构件"]
    issues: list[str] = []
    for index, operation in enumerate(patch.get("operations", []), start=1):
        prefix = f"operations[{index}]"
        if not isinstance(operation, dict) or operation.get("op") != "tune_material":
            issues.append(f"{prefix} 材质优化模式只允许 tune_material")
        elif operation.get("id") not in selected_ids:
            issues.append(f"{prefix}.id 必须是当前选中构件")
    return issues


def _enrich_material_tuning_operations(blueprint: dict, patch: dict) -> None:
    """补入由当前 Blueprint 推导的只读前值，供确认界面稳定展示差异。"""
    geometry = blueprint.get("geometry", {})
    entities = {
        item.get("id"): item
        for item in [
            *geometry.get("elements", []),
            *geometry.get("components", []),
        ]
        if isinstance(item, dict) and item.get("id")
    }
    materials = blueprint.get("materials", {})
    for operation in patch.get("operations", []):
        if not isinstance(operation, dict) or operation.get("op") != "tune_material":
            continue
        entity = entities.get(operation.get("id"))
        material_field = operation.get("material_field", "material")
        source_name = entity.get(material_field) if isinstance(entity, dict) else None
        source = materials.get(source_name) if isinstance(materials, dict) else None
        changes = operation.get("changes")
        if isinstance(source_name, str) and isinstance(source, dict) and isinstance(changes, dict):
            operation["source_name"] = source_name
            operation["before"] = {key: source.get(key) for key in changes}


def _validate_scene_patch_operations(blueprint: dict, patch: dict) -> list[str]:
    """在应用前校验操作名、必填参数、目标和新增 ID。"""
    geometry = blueprint.get("geometry", {})
    element_ids = {
        item.get("id") for item in geometry.get("elements", [])
        if isinstance(item, dict) and item.get("id")
    }
    component_ids = {
        item.get("id") for item in geometry.get("components", [])
        if isinstance(item, dict) and item.get("id")
    }
    asset_ids = set(blueprint.get("assets", {}))
    materials = blueprint.get("materials", {})
    material_names = set(materials) if isinstance(materials, dict) else set()
    elements_by_id = {
        item.get("id"): item for item in geometry.get("elements", [])
        if isinstance(item, dict) and item.get("id")
    }
    components_by_id = {
        item.get("id"): item for item in geometry.get("components", [])
        if isinstance(item, dict) and item.get("id")
    }
    errors: list[str] = []

    for index, operation in enumerate(patch.get("operations", []), start=1):
        prefix = f"operations[{index}]"
        if not isinstance(operation, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        op_type = operation.get("op")

        if op_type in {"add_element", "add_component"}:
            field_name = "element" if op_type == "add_element" else "component"
            entity = operation.get(field_name)
            if not isinstance(entity, dict):
                errors.append(f"{prefix}.{field_name} 必须是完整对象")
                continue
            entity_id = entity.get("id")
            if not isinstance(entity_id, str) or not entity_id.strip():
                errors.append(f"{prefix}.{field_name}.id 缺失")
                continue
            if not isinstance(entity.get("type"), str) or not entity["type"].strip():
                errors.append(f"{prefix}.{field_name}.type 缺失")
            if entity_id in element_ids or entity_id in component_ids:
                errors.append(f"{prefix} 新增 ID 已存在: {entity_id}")
                continue
            (element_ids if op_type == "add_element" else component_ids).add(entity_id)
            continue

        if op_type in {
            "update_element", "remove_element",
            "update_component", "remove_component",
        }:
            entity_id = operation.get("id")
            target_ids = element_ids if op_type.endswith("element") else component_ids
            if not isinstance(entity_id, str) or entity_id not in target_ids:
                errors.append(f"{prefix} 目标不存在: {entity_id!r}")
                continue
            if op_type.startswith("update_"):
                changes = operation.get("changes")
                if not isinstance(changes, dict) or not changes:
                    errors.append(f"{prefix}.changes 必须是非空对象")
                elif {"id", "type"} & set(changes):
                    errors.append(f"{prefix}.changes 不允许修改 id/type")
            else:
                target_ids.remove(entity_id)
            continue

        if op_type == "upsert_material":
            if not isinstance(operation.get("name"), str) or not operation["name"].strip():
                errors.append(f"{prefix}.name 缺失")
            material = operation.get("material")
            if not isinstance(material, dict):
                errors.append(f"{prefix}.material 必须是对象")
            elif material.get("textureSet") and material["textureSet"] not in asset_ids:
                errors.append(
                    f"{prefix}.material.textureSet 资产不存在: "
                    f"{material['textureSet']}"
                )
            if isinstance(operation.get("name"), str) and operation["name"].strip():
                material_names.add(operation["name"])
            continue

        if op_type == "tune_material":
            entity_id = operation.get("id")
            entity = elements_by_id.get(entity_id) or components_by_id.get(entity_id)
            if entity is None:
                errors.append(f"{prefix} 目标不存在: {entity_id!r}")
                continue
            material_field = operation.get("material_field", "material")
            if material_field not in _MATERIAL_REFERENCE_FIELDS:
                errors.append(f"{prefix}.material_field 不受支持: {material_field!r}")
                continue
            source_name = entity.get(material_field)
            source_material = (
                materials.get(source_name)
                if isinstance(materials, dict) and isinstance(source_name, str)
                else None
            )
            if not isinstance(source_material, dict):
                errors.append(
                    f"{prefix} 目标字段 {material_field} 没有可克隆的现有材质"
                )
            new_name = operation.get("new_name")
            if not isinstance(new_name, str) or not new_name.strip():
                errors.append(f"{prefix}.new_name 缺失")
            elif new_name in material_names:
                errors.append(f"{prefix}.new_name 已存在: {new_name}")
            else:
                material_names.add(new_name)
            changes = operation.get("changes")
            errors.extend(_validate_material_tuning_changes(
                changes,
                f"{prefix}.changes",
            ))
            if isinstance(source_material, dict) and isinstance(changes, dict):
                if all(source_material.get(key) == value for key, value in changes.items()):
                    errors.append(f"{prefix}.changes 没有产生任何材质参数变化")
                texture_set = source_material.get("textureSet")
                texture_asset = (
                    blueprint.get("assets", {}).get(texture_set)
                    if isinstance(texture_set, str)
                    else None
                )
                has_normal_map = bool(
                    isinstance(source_material.get("textures"), dict)
                    and source_material["textures"].get("normal")
                ) or bool(
                    isinstance(texture_asset, dict)
                    and isinstance(texture_asset.get("maps"), dict)
                    and texture_asset["maps"].get("normal")
                )
                if "normalScale" in changes and not has_normal_map:
                    errors.append(
                        f"{prefix}.changes.normalScale 无法生效：当前材质没有 normal 纹理"
                    )
            continue

        if op_type == "upsert_asset":
            asset_id = operation.get("asset_id")
            asset = operation.get("asset")
            if not isinstance(asset_id, str) or not asset_id.strip():
                errors.append(f"{prefix}.asset_id 缺失")
            elif not isinstance(asset, dict):
                errors.append(f"{prefix}.asset 必须是对象")
            elif asset.get("assetId") != asset_id:
                errors.append(f"{prefix}.asset.assetId 必须与 asset_id 一致")
            else:
                asset_ids.add(asset_id)
            continue

        errors.append(f"{prefix}.op 不受支持: {op_type!r}")

    return errors


def _apply_patch_to_blueprint(blueprint: dict, patch: dict) -> dict:
    """将 ScenePatch 应用到 Blueprint 深拷贝，返回修改后的 Blueprint

    支持基础构件、组合构件、材质和资产清单的增量修改。
    """
    bp = deepcopy(blueprint)
    elements = bp.setdefault("geometry", {}).setdefault("elements", [])
    components = bp["geometry"].setdefault("components", [])

    for op in patch.get("operations", []):
        op_type = op.get("op")
        if op_type == "add_element":
            el = op.get("element")
            if el and isinstance(el, dict):
                elements.append(el)
        elif op_type == "update_element":
            el_id = op.get("id")
            changes = op.get("changes", {})
            for el in elements:
                if el.get("id") == el_id:
                    el.update(changes)
                    break
        elif op_type == "remove_element":
            el_id = op.get("id")
            bp["geometry"]["elements"] = [e for e in elements if e.get("id") != el_id]
            elements = bp["geometry"]["elements"]
        elif op_type == "add_component":
            component = op.get("component")
            if component and isinstance(component, dict):
                components.append(component)
        elif op_type == "update_component":
            component_id = op.get("id")
            changes = op.get("changes", {})
            for component in components:
                if component.get("id") == component_id:
                    component.update(changes)
                    break
        elif op_type == "remove_component":
            component_id = op.get("id")
            bp["geometry"]["components"] = [
                component for component in components
                if component.get("id") != component_id
            ]
            components = bp["geometry"]["components"]
        elif op_type == "upsert_material":
            name = op.get("name")
            material = op.get("material")
            if name and isinstance(material, dict):
                bp.setdefault("materials", {})[name] = material
        elif op_type == "tune_material":
            entity_id = op.get("id")
            material_field = op.get("material_field", "material")
            entity = next(
                (
                    item for item in [*elements, *components]
                    if isinstance(item, dict) and item.get("id") == entity_id
                ),
                None,
            )
            if entity is not None:
                source_name = entity.get(material_field)
                source = bp.get("materials", {}).get(source_name)
                new_name = op.get("new_name")
                changes = op.get("changes")
                if isinstance(source, dict) and new_name and isinstance(changes, dict):
                    tuned = deepcopy(source)
                    tuned.update(changes)
                    bp.setdefault("materials", {})[new_name] = tuned
                    entity[material_field] = new_name
        elif op_type == "upsert_asset":
            asset_id = op.get("asset_id")
            asset = op.get("asset")
            if asset_id and isinstance(asset, dict):
                bp.setdefault("assets", {})[asset_id] = asset

    return bp


class AgentService:
    """Agent 服务

    生命周期：
    - 构造时：加载规范文档 + 创建 LLM + 注册 tools + 组装 System Prompt
    - query_structured()：统一入口，同时处理生成/修改/聊天三种意图

    一份 prompt 覆盖所有场景。场景上下文（如有）通过 user message 注入。
    """

    def __init__(self):
        # ===== 1. 创建规范加载器（优先 RAG，失败则退回文件读取）=====
        self.spec_loader = self._create_spec_loader()
        self._dynamic_prompt = isinstance(self.spec_loader, RAGSpecLoader)
        logger.info(
            f"SpecLoader: {type(self.spec_loader).__name__}, "
            f"sources={len(self.spec_loader.list_sources())}"
        )

        # ===== 2. 创建 LLM =====
        # 非思考模式显式关闭 DashScope 的默认思考；思考模型使用流式响应，
        # 以便通过回调实时取得 reasoning_content。
        self.llm = create_llm(enable_thinking=False)
        self.thinking_llm = create_llm(enable_thinking=True, streaming=True)
        logger.info("LLM 已创建（普通模式 + 流式思考模式）")

        # ===== 3. 注册 Tools（所有意图通用）=====
        self.tools = [
            get_wall_bounding_box,
            validate_blueprint_structure,
            validate_element_required_fields,
            validate_reference_integrity,
            validate_opening_coords,
            validate_opening_fit,
            validate_wall_junctions,
            validate_stair_alignment,
            validate_roof_coverage,
            validate_element_dimensions,
            fix_material_references,
            fix_element_dimensions,
            fix_element_elevations,
            fix_opening_coords,
            fix_opening_fit,
            fix_roof_coverage,
            fix_stair_alignment,
            fix_wall_junctions,
            validate_collision,
        ]
        logger.info(f"已注册 {len(self.tools)} 个工具: {[t.name for t in self.tools]}")

        # ===== 4. 非 RAG 模式创建静态 Agent；RAG 模式每次 query 动态创建 =====
        self.agent = None
        if not self._dynamic_prompt:
            spec_text = self.spec_loader.load()
            self.agent = self._create_agent(spec_text)
            logger.info("AgentService: 使用静态规范上下文")

        logger.info("AgentService 初始化完成")

    def _create_spec_loader(self):
        """按配置创建 RAG Loader，初始化失败时降级为基础文件 Loader。"""
        if config.rag.enabled:
            try:
                persist_dir = Path(config.rag.persist_dir)
                if not persist_dir.is_absolute():
                    persist_dir = _SERVER_ROOT / persist_dir

                embedding_function = create_embedding_function(
                    api_key=config.embedding.api_key,
                    base_url=config.embedding.base_url,
                    model_name=config.embedding.name,
                    allow_hash_fallback=config.rag.allow_hash_fallback,
                )
                rag_spec_paths = get_rag_spec_paths()
                loader = RAGSpecLoader(
                    base_paths=[str(p) for p in BASE_SPEC_PATHS],
                    rag_paths=[str(p) for p in rag_spec_paths],
                    persist_dir=str(persist_dir),
                    collection_name=config.rag.collection_name,
                    embedding_function=embedding_function,
                    top_k=config.rag.top_k,
                    chunk_size=config.rag.chunk_size,
                    chunk_overlap=config.rag.chunk_overlap,
                    max_context_chars=config.rag.max_context_chars,
                )
                logger.info(
                    f"RAGSpecLoader: 已启用 Chroma, persist_dir={persist_dir}, "
                    f"collection={config.rag.collection_name}"
                )
                sync_stats = loader.last_sync_stats
                logger.info(
                    "RAG 索引同步: "
                    f"total={sync_stats['total']}, "
                    f"updated={sync_stats['updated']}, "
                    f"deleted={sync_stats['deleted']}"
                )
                if isinstance(embedding_function, object) and embedding_function.__class__.__name__ == "HashEmbeddingFunction":
                    logger.warning("RAGSpecLoader: 当前使用 hash fallback embedding，仅适合本地 smoke test")
                return loader
            except Exception as exc:
                logger.warning(
                    "⚠️  RAG 向量索引不可用，已降级为全量文件注入模式（FileSpecLoader）。"
                )
                logger.warning(f"  原因: {type(exc).__name__}: {exc}")
                logger.warning(
                    "  请检查: EMBEDDING__NAME / EMBEDDING__API_KEY / EMBEDDING__BASE_URL"
                    " 配置是否正确，以及 embedding 服务是否可达。"
                )
                logger.error(f"RAGSpecLoader 初始化失败，退回 FileSpecLoader: {type(exc).__name__}: {exc}", exc_info=True)

        return FileSpecLoader([str(p) for p in BASE_SPEC_PATHS])

    def _create_agent(self, spec_text: str, thinking_mode: bool = False):
        """用当前 LLM、工具集和本次规范上下文创建无会话状态的 Agent。"""
        system_prompt = build_system_prompt(spec_text)
        logger.info(f"System Prompt: 总计 {len(system_prompt):,} 字符")
        return create_agent(
            model=self.thinking_llm if thinking_mode else self.llm,
            tools=self.tools,
            system_prompt=system_prompt,
        )

    def _agent_for_query(
        self,
        rag_query: str | list[str],
        thinking_mode: bool = False,
    ):
        """为一次查询准备 Agent；RAG 模式会先动态组装本次 System Prompt。"""
        if not self._dynamic_prompt:
            if not thinking_mode:
                return self.agent
            return self._create_agent(self.spec_loader.load(), thinking_mode=True)

        if isinstance(rag_query, list) and isinstance(self.spec_loader, RAGSpecLoader):
            filtered_queries = self._build_filtered_rag_queries(rag_query)
            spec_text = self.spec_loader.load_many(filtered_queries, per_query=1)
            query_log = " | ".join(rag_query)
        else:
            query_text = rag_query[0] if isinstance(rag_query, list) else rag_query
            spec_text = self.spec_loader.load(query=query_text)
            query_log = query_text
        if isinstance(self.spec_loader, RAGSpecLoader):
            hits = [
                f"{hit.metadata.get('source', '?')} / {hit.metadata.get('heading', '?')}"
                for hit in self.spec_loader.last_results
            ]
            logger.info(f"RAG 检索 query={query_log[:300]!r}, hits={hits}")
        return self._create_agent(spec_text, thinking_mode=thinking_mode)

    def _build_filtered_rag_queries(self, queries: list[str]) -> list[SpecQuery]:
        """为建筑生成的八类检索意图附加业务 metadata 过滤条件。"""
        if len(queries) != 8:
            return [SpecQuery(text=query) for query in queries]

        filters = [
            {"doc_type": "building_type"},
            {"doc_type": "recipe"},
            {"doc_type": "component", "entity_type": "structural_component"},
            {"doc_type": "component", "entity_type": "wall"},
            {"doc_type": "component", "entity_type": "window"},
            {"doc_type": "component", "entity_type": "door"},
            {"doc_type": "component", "entity_type": "railing"},
            {"doc_type": "component", "entity_type": "roof"},
        ]
        return [
            SpecQuery(text=query, metadata_filter=metadata_filter)
            for query, metadata_filter in zip(queries, filters)
        ]

    def _build_rag_query(self, message: str, current_blueprint: dict | None) -> str:
        """把用户文本与场景线索拼成单个向量检索查询。"""
        parts = [message]
        generation_keywords = (
            "生成", "建造", "创建", "建一个", "做一个",
            "画一个", "搭一个", "来一个", "设计一个",
        )
        if not current_blueprint and any(keyword in message for keyword in generation_keywords):
            parts.append(
                "同时检索：对象的默认变体、最少可行版本、默认材质、配色、"
                "PBR 参数；建筑还需检索外墙、楼板、屋顶、门窗和玻璃透明度"
            )
        if current_blueprint:
            meta = current_blueprint.get("meta", {})
            elements = current_blueprint.get("geometry", {}).get("elements", [])
            types = sorted({str(el.get("type")) for el in elements if el.get("type")})
            if meta.get("name"):
                parts.append(f"场景名称: {meta.get('name')}")
            if types:
                parts.append(f"当前构件类型: {', '.join(types)}")
        return "\n".join(parts)

    def _build_rag_queries(
        self,
        message: str,
        current_blueprint: dict | None,
    ) -> list[str]:
        """为建筑生成拆分主体和组件检索意图，保证关键组件文档进入上下文。"""
        primary_query = self._build_rag_query(message, current_blueprint)
        if current_blueprint:
            return [primary_query]

        generation_keywords = (
            "生成", "建造", "创建", "建一个", "做一个",
            "画一个", "搭一个", "来一个", "设计一个",
        )
        building_keywords = (
            "别墅", "住宅", "房", "建筑", "小屋", "木屋", "亭",
            "楼", "酒店", "宿舍", "办公", "学校", "商场", "医院",
            "车站", "工厂", "仓库", "庭院", "四合院", "塔", "庙",
            "宫殿", "教堂",
        )
        is_building_generation = (
            any(keyword in message for keyword in generation_keywords)
            and any(keyword in message for keyword in building_keywords)
        )
        if not is_building_generation:
            return [primary_query]

        return [
            primary_query,
            f"{message}\n构件-建筑类型速查矩阵：opening、door、window、roof、stair、railing 的推荐组合",
            f"{message}\n结构构件规则：柱梁楼板桁架、column、beam、floor、truss 的参数与组合",
            f"{message}\n墙体构件参数与围护规则：wall、thickness、height、material、opening 承载关系",
            f"{message}\n窗构件分类与组装规则：window、opening、mullion、fixed、casement、sliding、窗型选择",
            f"{message}\n门构件分类与组装规则：door、opening、panel、glass、门型选择",
            f"{message}\n栏杆构件参数与路径规则：railing、path、postSpacing、railLevels、楼梯与阳台栏杆",
            f"{message}\n屋顶屋檐构件规则：roof、cornice、canopy、flat、gable、hip、屋顶选型",
        ]

    async def _recover_scene_patch(
        self,
        message: str,
        current_blueprint: dict,
        previous_reply: str,
        selection: list[str] | None = None,
        material_optimization: bool = False,
    ) -> tuple[dict | None, str, str | None]:
        """用一次非思考调用把错误格式恢复为单一 ScenePatch。"""
        recovery_prompt = build_patch_recovery_prompt(
            message,
            _build_scene_summary(current_blueprint, selection),
            previous_reply,
        )
        if material_optimization:
            recovery_prompt += build_material_optimization_prompt(selection or [])
        response = await self.llm.ainvoke([
            {
                "role": "system",
                "content": "你是 ScenePatch 格式恢复器，只返回请求指定的 JSON。",
            },
            {"role": "user", "content": recovery_prompt},
        ])
        content, reasoning = _message_texts(response)
        for source, text in (
            ("recovery_content", content),
            ("recovery_reasoning", reasoning),
        ):
            patch = extract_patch_from_text(text)
            if patch is not None:
                return patch, content or reasoning, source
        return None, content or reasoning, None

    async def query_structured(
        self,
        message: str,
        current_blueprint: dict | None = None,
        *,
        selection: list[str] | None = None,
        thinking_mode: bool = False,
        on_reasoning_delta: Callable[[str], Awaitable[None]] | None = None,
        expected_output: Literal["auto", "patch"] = "auto",
    ) -> QueryResult:
        """统一入口：一次调用覆盖生成/修改/聊天三种意图。

        1. 如有 current_blueprint，将场景摘要注入 user message
        2. LLM 自行判断意图，输出 Blueprint 或 ScenePatch 或纯文本
        3. 从回复提取 JSON → 校验流水线 → 返回 QueryResult
        """
        selected_ids = _normalized_selection(selection)
        material_optimization = bool(
            current_blueprint and _is_material_optimization_request(message)
        )
        if material_optimization and not selected_ids:
            return QueryResult(
                text="请先在场景中选中需要优化材质的构件，再重新发送请求。",
                error="材质优化前必须先选中一个构件",
            )
        if material_optimization:
            expected_output = "patch"

        # ── 场景上下文（如有）注入 user message ──────────────────
        user_message = message
        if current_blueprint:
            elements = current_blueprint.get("geometry", {}).get("elements", [])
            if elements:
                scene_summary = _build_scene_summary(current_blueprint, selected_ids)
                user_message = (
                    f"# 当前场景（你可以修改它）\n\n{scene_summary}\n\n"
                    f"# 用户请求\n\n{message}"
                )
                logger.info(f"[query] 注入场景上下文, 构件数={len(elements)}")
        if expected_output == "patch":
            user_message += (
                "\n\n# 本次输出协议（强制）\n\n"
                "上游已经判定这是增量修改。只输出一个 ScenePatch JSON 对象，"
                "必须包含非空 operations 数组和 summary；不要输出完整 Blueprint。"
            )
        if material_optimization:
            user_message += build_material_optimization_prompt(selected_ids)

        # ── LLM 调用（Agent + 工具）──────────────────────────────
        rag_queries = self._build_rag_queries(message, current_blueprint)
        agent = self._agent_for_query(rag_queries, thinking_mode=thinking_mode)
        reasoning_callback = None
        invoke_config = None
        if thinking_mode and on_reasoning_delta is not None:
            reasoning_callback = _ReasoningStreamCallback(on_reasoning_delta)
            invoke_config = {"callbacks": [reasoning_callback]}

        try:
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": user_message}]},
                config=invoke_config,
            )
        finally:
            if reasoning_callback is not None:
                await reasoning_callback.flush()
        final_message = result["messages"][-1]
        reply, reasoning = _message_texts(final_message)
        logger.info(
            f"Agent 回复: content={len(reply)}字符, reasoning={len(reasoning)}字符, "
            f"preview={(reply or reasoning)[:200]}..."
        )

        # Blueprint 与 ScenePatch 必须独立提取。旧逻辑先要求 Blueprint 提取成功，
        # 导致合法 ScenePatch 永远无法进入 patch 分支。
        blueprint_data, patch_data, structured_source = _extract_response_artifacts(
            reply,
            reasoning,
            prefer_patch=expected_output == "patch" or current_blueprint is not None,
        )
        recovery_used = False
        if expected_output == "patch" and patch_data is None and current_blueprint:
            logger.warning("[query] 首次回复未提取到 ScenePatch，执行一次定向格式恢复")
            try:
                recovered_patch, recovered_text, recovery_source = (
                    await self._recover_scene_patch(
                        message,
                        current_blueprint,
                        reply or reasoning,
                        selected_ids,
                        material_optimization,
                    )
                )
                recovery_used = True
                if recovered_patch is not None:
                    patch_data = recovered_patch
                    structured_source = recovery_source
                    if recovered_text:
                        reply = recovered_text
            except Exception as exc:
                logger.warning(f"[query] ScenePatch 定向格式恢复失败: {exc}")

        if patch_data is not None:
            if not current_blueprint:
                return QueryResult(
                    text=reply,
                    error="ScenePatch 缺少可应用的当前 Blueprint",
                    structured_source=structured_source,
                    structured_recovery_used=recovery_used,
                )

            operation_issues = _validate_scene_patch_operations(
                current_blueprint,
                patch_data,
            )
            if material_optimization:
                operation_issues.extend(_validate_material_optimization_patch(
                    patch_data,
                    selected_ids,
                ))
            if operation_issues:
                return QueryResult(
                    text=reply,
                    patch=patch_data,
                    error="ScenePatch 操作预检未通过: " + "; ".join(operation_issues),
                    structured_source=structured_source,
                    structured_recovery_used=recovery_used,
                )

            _enrich_material_tuning_operations(current_blueprint, patch_data)

            modified_bp = _apply_patch_to_blueprint(current_blueprint, patch_data)
            if modified_bp == current_blueprint:
                return QueryResult(
                    text=reply,
                    patch=patch_data,
                    error="ScenePatch 未产生任何实际修改",
                    structured_source=structured_source,
                    structured_recovery_used=recovery_used,
                )
            modified_bp = normalize_blueprint_input(modified_bp)
            pre_issues = validate_blueprint_schema(modified_bp)
            if pre_issues:
                return QueryResult(
                    text=reply,
                    patch=patch_data,
                    error=(
                        "Patch 应用后的 Blueprint 结构预检未通过: "
                        + "; ".join(pre_issues)
                    ),
                    structured_source=structured_source,
                    structured_recovery_used=recovery_used,
                )
            pipeline_results = run_validation_pipeline(modified_bp)
            fatal_steps = _final_errors(pipeline_results)
            error_summary = None
            if fatal_steps:
                error_summary = "校验流水线存在错误: " + "; ".join(
                    f"Step{r.step}({r.name})" for r in fatal_steps
                )
            return QueryResult(
                text=reply,
                patch=patch_data,
                error=error_summary,
                pipeline_results=pipeline_results,
                structured_source=structured_source,
                structured_recovery_used=recovery_used,
            )

        if blueprint_data is not None:
            if expected_output == "patch":
                return QueryResult(
                    text=reply,
                    error="增量修改节点返回了完整 Blueprint，而不是 ScenePatch",
                    structured_source=structured_source,
                    structured_recovery_used=recovery_used,
                )
            blueprint_data = normalize_blueprint_input(blueprint_data)
            pre_issues = validate_blueprint_schema(blueprint_data)
            if pre_issues:
                return QueryResult(
                    text=reply,
                    error=f"Blueprint 结构预检未通过: {'; '.join(pre_issues)}",
                    structured_source=structured_source,
                )
            pipeline_results = run_validation_pipeline(blueprint_data)
            fatal_steps = _final_errors(pipeline_results)
            error_summary = None
            if fatal_steps:
                error_summary = "校验流水线存在错误: " + "; ".join(
                    f"Step{r.step}({r.name})" for r in fatal_steps
                )
            return QueryResult(
                text=reply,
                blueprint=blueprint_data,
                error=error_summary,
                pipeline_results=pipeline_results,
                structured_source=structured_source,
            )

        if expected_output == "patch":
            return QueryResult(
                text=reply,
                error="模型两次回复均未返回可解析的 ScenePatch",
                structured_recovery_used=recovery_used,
            )

        # ── 纯文本（对话类）─────────────────────────────────────
        return QueryResult(text=reply)


# 模块级单例：导入 ws_agent 时完成配置、知识库索引和模型客户端初始化。
agent_service = AgentService()
