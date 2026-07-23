"""
Agent Service —— Agent 生命周期管理和对话入口

职责：组装 spec_loader + tools + prompt + llm，对外提供统一的 query_structured() 接口。

校验流水线（服务端强制执行，不依赖 LLM 自由调用顺序）：
  Structure → Schema → Reference → Geometry → Fix → Collision → Render

  Step 1   validate_blueprint_structure      顶层结构 + ID 唯一性
  Step 2   validate_element_required_fields  必填字段 + 枚举合法性
  Step 3   validate_reference_integrity      跨构件引用合法性
  Step 4   validate_opening_coords           门窗沿墙距离格式
  Step 4b  validate_opening_fit              门窗是否超出 parentWall 范围（顶点爆炸根源）
  Step 5   validate_wall_junctions           墙体转角端点对齐
  Step 6   validate_stair_alignment          楼梯端点高度对齐
  Step 7   validate_roof_coverage            屋顶覆盖范围
  Step 7b  validate_element_dimensions       各构件尺寸合理性
  Step 8   fix_opening_coords                自动修正门窗 from[0]（如有问题）
           → 修正后重跑 validate_opening_coords + validate_opening_fit
  Step 8b  fix_roof_coverage                 自动修正屋顶 span/depth/position（如有问题）
           → 修正后重跑 validate_roof_coverage
  Step 8c  fix_wall_junctions                自动对齐孤立墙体端点（如有问题）
           → 修正后重跑 validate_wall_junctions
  Step 9   validate_collision                碰撞/穿插/悬空/重叠检测

升级路径（每次只改内部，query_structured() 接口和 ws_agent.py 不动）：
  现在   → FileSpecLoader + create_agent + server-side pipeline
  以后1  → RAGSpecLoader（只改 loader 一行）
  以后2  → LangGraph graph.ainvoke()（只改编排，tools + pipeline 复用）
"""
from dataclasses import dataclass, field
from pathlib import Path
from langchain.agents import create_agent
from loguru import logger
from app.agent.model_client import create_llm
from app.agent.prompts import build_system_prompt
from app.spec.loader import FileSpecLoader
from app.tools.spatial_tools import (
    fix_element_dimensions,
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
    validate_opening_coords,
    validate_opening_fit,
    validate_reference_integrity,
    validate_roof_coverage,
    validate_stair_alignment,
    validate_wall_junctions,
)
from app.utils.blueprint_parser import extract_blueprint_from_text, validate_blueprint_schema

# ---------- 规范文档路径 ----------
_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent  # wild-server/
_KB = _SERVER_ROOT / "storage" / "knowledge_base"

SPEC_PATHS = [
    _KB / "BLUEPRINT-SPEC-MINIMAL.md",
]


@dataclass
class PipelineStepResult:
    """单个流水线步骤的执行结果"""
    step: int
    name: str
    output: str
    has_error: bool     # 输出中包含 ❌ 级别问题
    has_warning: bool   # 输出中包含 ⚠️ 级别问题


@dataclass
class QueryResult:
    """query_structured() 的结构化返回结果

    - text:              完整 LLM 回复文本（始终存在）
    - blueprint:         提取的 Blueprint dict（可能为 None）
    - error:             致命错误描述（无错误时为 None）
    - pipeline_results:  各流水线步骤的执行结果列表
    """
    text: str
    blueprint: dict | None = None
    error: str | None = None
    pipeline_results: list[PipelineStepResult] = field(default_factory=list)


def _run_tool(tool_fn, blueprint: dict) -> str:
    """调用 @tool 装饰的函数（绕过 LangChain 的 .invoke 包装，直接调用底层函数）"""
    # LangChain @tool 把原函数存在 .func 属性上
    fn = getattr(tool_fn, "func", tool_fn)
    return fn(blueprint)


def run_validation_pipeline(blueprint: dict) -> list[PipelineStepResult]:
    """
    按固定顺序执行所有校验 + 自动修正步骤，返回每步结果。

    流水线：
      1  validate_blueprint_structure
      2  validate_element_required_fields
      3  validate_reference_integrity
      4  validate_opening_coords
      4b validate_opening_fit            ← 新增：开口越界检查（顶点爆炸根源）
      5  validate_wall_junctions
      6  validate_stair_alignment
      7  validate_roof_coverage
      7b validate_element_dimensions     ← 新增：构件尺寸合理性
      8  fix_opening_coords              ← 如 Step4/4b 有问题则修正 + recheck
      8b fix_opening_fit                 ← 如 Step4b 有严重越界则修正 + recheck
      8c fix_stair_alignment             ← 如 Step6 有高度不对齐则修正 + recheck
      8d fix_element_dimensions          ← 如 Step7b 有尺寸异常则修正 + recheck
      8e fix_roof_coverage               ← 如 Step7 有问题则修正 + recheck
      8f fix_wall_junctions              ← 如 Step5 有问题则修正 + recheck
      9  validate_collision
    """
    results: list[PipelineStepResult] = []

    def run_step(step: int, name: str, tool_fn, bp: dict) -> PipelineStepResult:
        output = _run_tool(tool_fn, bp)
        has_error   = "❌" in output
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
        r = PipelineStepResult(step=step, name=name,
                               output=f"⏭️  跳过（{reason}）",
                               has_error=False, has_warning=False)
        results.append(r)
        return r

    # ── Step 1: 顶层结构 ──────────────────────────────────────────────
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

    # ── Step 2: 必填字段 ──────────────────────────────────────────────
    r2 = run_step(2, "validate_element_required_fields", validate_element_required_fields, blueprint)

    # ── Step 3: 引用完整性 ────────────────────────────────────────────
    run_step(3, "validate_reference_integrity", validate_reference_integrity, blueprint)

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

    # ── Step 4: 门窗坐标 ─────────────────────────────────────────────
    r4 = run_step(4, "validate_opening_coords", validate_opening_coords, blueprint)

    # ── Step 4b: 开口越界检查 ─────────────────────────────────────────
    r4b = run_step("4b", "validate_opening_fit", validate_opening_fit, blueprint)

    # ── Step 5: 墙体连接 ─────────────────────────────────────────────
    r5 = run_step(5, "validate_wall_junctions", validate_wall_junctions, blueprint)

    # ── Step 6: 楼梯对齐 ─────────────────────────────────────────────
    r6 = run_step(6, "validate_stair_alignment", validate_stair_alignment, blueprint)

    # ── Step 7: 屋顶覆盖 ─────────────────────────────────────────────
    r7 = run_step(7, "validate_roof_coverage", validate_roof_coverage, blueprint)

    # ── Step 7b: 构件尺寸合理性 ──────────────────────────────────────
    r7b = run_step("7b", "validate_element_dimensions", validate_element_dimensions, blueprint)

    # ── Step 8: 自动修正门窗坐标 ─────────────────────────────────────
    if r4.has_warning or r4.has_error or r4b.has_error or r4b.has_warning:
        fix_out = _run_tool(fix_opening_coords, blueprint)
        results.append(PipelineStepResult(
            step=8, name="fix_opening_coords", output=fix_out,
            has_error="❌" in fix_out, has_warning="⚠️" in fix_out,
        ))
        logger.info("[Pipeline Step 8] fix_opening_coords 已执行")
        # recheck
        for chk_fn, chk_name in [
            (validate_opening_coords, "validate_opening_coords [recheck]"),
            (validate_opening_fit,    "validate_opening_fit [recheck]"),
        ]:
            out = _run_tool(chk_fn, blueprint)
            results.append(PipelineStepResult(
                step=8, name=chk_name, output=out,
                has_error="❌" in out, has_warning="⚠️" in out,
            ))
    else:
        skip_step(8, "fix_opening_coords", "Step 4/4b 门窗坐标无问题")

    # ── Step 8b: 自动修正开口越界 ──────────────────────────────────
    if r4b.has_error:  # 只有严重越界（❌）才修正，警告（⚠️）不修正
        fix_out = _run_tool(fix_opening_fit, blueprint)
        results.append(PipelineStepResult(
            step="8b", name="fix_opening_fit", output=fix_out,
            has_error="❌" in fix_out, has_warning="⚠️" in fix_out,
        ))
        logger.info("[Pipeline Step 8b] fix_opening_fit 已执行")
        recheck_out = _run_tool(validate_opening_fit, blueprint)
        results.append(PipelineStepResult(
            step="8b", name="validate_opening_fit [recheck]", output=recheck_out,
            has_error="❌" in recheck_out, has_warning="⚠️" in recheck_out,
        ))
    else:
        skip_step("8b", "fix_opening_fit", "Step 4b 开口越界无严重问题")

    # ── Step 8c: 自动修正楼梯对齐 ──────────────────────────────────
    if r6.has_warning or r6.has_error:
        fix_out = _run_tool(fix_stair_alignment, blueprint)
        results.append(PipelineStepResult(
            step="8c", name="fix_stair_alignment", output=fix_out,
            has_error="❌" in fix_out, has_warning="⚠️" in fix_out,
        ))
        logger.info("[Pipeline Step 8c] fix_stair_alignment 已执行")
        recheck_out = _run_tool(validate_stair_alignment, blueprint)
        results.append(PipelineStepResult(
            step="8c", name="validate_stair_alignment [recheck]", output=recheck_out,
            has_error="❌" in recheck_out, has_warning="⚠️" in recheck_out,
        ))
    else:
        skip_step("8c", "fix_stair_alignment", "Step 6 楼梯对齐无问题")

    # ── Step 8d: 自动修正构件尺寸 ──────────────────────────────────
    if r7b.has_error:  # 只有尺寸严重异常（❌）才修正，警告（⚠️）不修正
        fix_out = _run_tool(fix_element_dimensions, blueprint)
        results.append(PipelineStepResult(
            step="8d", name="fix_element_dimensions", output=fix_out,
            has_error="❌" in fix_out, has_warning="⚠️" in fix_out,
        ))
        logger.info("[Pipeline Step 8d] fix_element_dimensions 已执行")
        recheck_out = _run_tool(validate_element_dimensions, blueprint)
        results.append(PipelineStepResult(
            step="8d", name="validate_element_dimensions [recheck]", output=recheck_out,
            has_error="❌" in recheck_out, has_warning="⚠️" in recheck_out,
        ))
    else:
        skip_step("8d", "fix_element_dimensions", "Step 7b 构件尺寸无严重异常")

    # ── Step 8e: 自动修正屋顶覆盖 ────────────────────────────────────
    if r7.has_error or r7.has_warning:
        fix_out = _run_tool(fix_roof_coverage, blueprint)
        results.append(PipelineStepResult(
            step="8e", name="fix_roof_coverage", output=fix_out,
            has_error="❌" in fix_out, has_warning="⚠️" in fix_out,
        ))
        logger.info("[Pipeline Step 8e] fix_roof_coverage 已执行")
        recheck_out = _run_tool(validate_roof_coverage, blueprint)
        results.append(PipelineStepResult(
            step="8e", name="validate_roof_coverage [recheck]", output=recheck_out,
            has_error="❌" in recheck_out, has_warning="⚠️" in recheck_out,
        ))
    else:
        skip_step("8e", "fix_roof_coverage", "Step 7 屋顶覆盖无问题")

    # ── Step 8f: 自动对齐墙体端点 ────────────────────────────────────
    if r5.has_warning or r5.has_error:
        fix_out = _run_tool(fix_wall_junctions, blueprint)
        results.append(PipelineStepResult(
            step="8f", name="fix_wall_junctions", output=fix_out,
            has_error="❌" in fix_out, has_warning="⚠️" in fix_out,
        ))
        logger.info("[Pipeline Step 8f] fix_wall_junctions 已执行")
        recheck_out = _run_tool(validate_wall_junctions, blueprint)
        results.append(PipelineStepResult(
            step="8f", name="validate_wall_junctions [recheck]", output=recheck_out,
            has_error="❌" in recheck_out, has_warning="⚠️" in recheck_out,
        ))
    else:
        skip_step("8f", "fix_wall_junctions", "Step 5 墙体端点无问题")

    # ── Step 9: 碰撞检测 ─────────────────────────────────────────────
    run_step(9, "validate_collision", validate_collision, blueprint)

    return results


class AgentService:
    """Agent 服务

    生命周期：
    - 构造时：加载规范文档 + 创建 LLM + 注册 tools + 组装 System Prompt
    - query_structured()：LLM 生成 Blueprint → 服务端流水线校验 → 返回结果
    - 后续升级：spec 换 RAG / 编排换 LangGraph，外部接口不变
    """

    def __init__(self):
        # ===== 1. 加载规范文档 =====
        self.spec_loader = FileSpecLoader([str(p) for p in SPEC_PATHS])
        spec_text = self.spec_loader.load()
        logger.info(
            f"SpecLoader: 已加载 {len(self.spec_loader.list_sources())} 个文档, "
            f"总计 {len(spec_text):,} 字符"
        )

        # ===== 2. 创建 LLM =====
        self.llm = create_llm()
        logger.info("LLM 已创建")

        # ===== 3. 组装 System Prompt =====
        system_prompt = build_system_prompt(spec_text)
        logger.info(f"System Prompt: 总计 {len(system_prompt):,} 字符")

        # ===== 4. 注册 Tools（LLM 可选调用，流水线由服务端兜底）=====
        tools = [
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
            fix_element_dimensions,
            fix_opening_coords,
            fix_opening_fit,
            fix_roof_coverage,
            fix_stair_alignment,
            fix_wall_junctions,
            validate_collision,
        ]
        logger.info(f"已注册 {len(tools)} 个工具: {[t.name for t in tools]}")

        # ===== 5. 创建 Agent =====
        self.agent = create_agent(
            model=self.llm,
            tools=tools,
            system_prompt=system_prompt,
        )
        logger.info("AgentService 初始化完成")

    async def query_structured(self, message: str) -> QueryResult:
        """
        执行一次完整的生成 + 校验流程：

        1. LLM 生成 Blueprint JSON（agent.ainvoke）
        2. 从回复提取 ```json 代码块
        3. 服务端固定流水线校验（Structure → ... → Collision）
        4. 返回 QueryResult（含 blueprint、pipeline_results、error）
        """
        # ── Phase 1: LLM 生成 ────────────────────────────────────────
        result = await self.agent.ainvoke({
            "messages": [{"role": "user", "content": message}]
        })
        reply = result["messages"][-1].content
        logger.info(f"Agent 回复: {reply[:120]}...")

        # ── Phase 2: 提取 Blueprint ──────────────────────────────────
        blueprint = extract_blueprint_from_text(reply)
        if blueprint is None:
            return QueryResult(
                text=reply,
                error="未能在回复中找到有效的 Blueprint JSON 代码块",
            )

        # 轻量结构预检（不依赖流水线，快速失败）
        pre_issues = validate_blueprint_schema(blueprint)
        if pre_issues:
            return QueryResult(
                text=reply,
                blueprint=blueprint,
                error=f"Blueprint 结构预检未通过: {'; '.join(pre_issues)}",
            )

        # ── Phase 3: 服务端校验流水线 ────────────────────────────────
        logger.info("开始执行校验流水线...")
        pipeline_results = run_validation_pipeline(blueprint)

        # 汇总是否有 ❌ 级别错误（⚠️ 警告不阻断，依然返回 blueprint）
        fatal_steps = [r for r in pipeline_results if r.has_error]
        error_summary = None
        if fatal_steps:
            error_summary = "校验流水线存在错误: " + "; ".join(
                f"Step{r.step}({r.name})" for r in fatal_steps
            )
            logger.warning(error_summary)

        return QueryResult(
            text=reply,
            blueprint=blueprint,
            error=error_summary,
            pipeline_results=pipeline_results,
        )


# 模块级单例
agent_service = AgentService()
