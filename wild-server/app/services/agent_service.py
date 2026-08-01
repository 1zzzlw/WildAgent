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
from pathlib import Path
from copy import deepcopy
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents import create_agent
from langchain_core.callbacks import AsyncCallbackHandler
from loguru import logger

from config import config
from app.agent.model_client import create_llm
from app.agent.prompts import build_system_prompt
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
from app.utils.blueprint_parser import (
    extract_blueprint_from_text,
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
    run_step(3, "validate_reference_integrity", validate_reference_integrity, blueprint)

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

    return results


def _build_scene_summary(blueprint: dict) -> str:
    """从 Blueprint 生成场景摘要文本（注入 user message 供 AI 参考）"""
    elements = blueprint.get("geometry", {}).get("elements", [])
    lines = [f"当前场景包含 {len(elements)} 个构件："]
    for el in elements:
        el_id = el.get("id", "?")
        el_type = el.get("type", "?")
        extras = []
        if el_type == "wall":
            frm = el.get("from", [])
            to = el.get("to", [])
            extras.append(f"from={frm[:2] if len(frm)>=2 else frm}, to={to[:2] if len(to)>=2 else to}")
        elif el_type == "column":
            base = el.get("base", [])
            extras.append(f"base={base[:2] if len(base)>=2 else base}, height={el.get('height','?')}")
        elif el_type == "roof":
            extras.append(f"span={el.get('span','?')}, depth={el.get('depth','?')}")
        elif el_type == "floor":
            frm = el.get("from", [])
            to = el.get("to", [])
            extras.append(f"from={frm[:2] if len(frm)>=2 else frm}, to={to[:2] if len(to)>=2 else to}")
        elif el_type == "opening":
            extras.append(f"parentWall={el.get('parentWall','?')}, from={el.get('from','?')}")
        lines.append(
            f"  - [{el_id}] type={el_type}"
            + (f" ({'; '.join(extras)})" if extras else "")
        )
    materials = blueprint.get("materials", {})
    if materials:
        lines.append(f"已有材质: {', '.join(materials.keys())}")
    return "\n".join(lines)


def _apply_patch_to_blueprint(blueprint: dict, patch: dict) -> dict:
    """将 ScenePatch 应用到 Blueprint 深拷贝，返回修改后的 Blueprint

    支持: add_element / update_element / remove_element / upsert_material
    """
    bp = deepcopy(blueprint)
    elements = bp.setdefault("geometry", {}).setdefault("elements", [])

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
        elif op_type == "upsert_material":
            name = op.get("name")
            material = op.get("material")
            if name and isinstance(material, dict):
                bp.setdefault("materials", {})[name] = material

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
                logger.error(f"RAGSpecLoader 初始化失败，退回 FileSpecLoader: {type(exc).__name__}: {exc}")

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
        """为建筑生成的七类检索意图附加业务 metadata 过滤条件。"""
        if len(queries) != 7:
            return [SpecQuery(text=query) for query in queries]

        filters = [
            {"doc_type": "building_type"},
            {"doc_type": "recipe"},
            {"doc_type": "component", "entity_type": "structural_component"},
            {"doc_type": "component", "entity_type": "wall"},
            {"doc_type": "component", "entity_type": "window"},
            {"doc_type": "component", "entity_type": "door"},
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
            f"{message}\n屋顶屋檐构件规则：roof、cornice、canopy、flat、gable、hip、屋顶选型",
        ]

    async def query_structured(
        self,
        message: str,
        current_blueprint: dict | None = None,
        *,
        thinking_mode: bool = False,
        on_reasoning_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> QueryResult:
        """统一入口：一次调用覆盖生成/修改/聊天三种意图。

        1. 如有 current_blueprint，将场景摘要注入 user message
        2. LLM 自行判断意图，输出 Blueprint 或 ScenePatch 或纯文本
        3. 从回复提取 JSON → 校验流水线 → 返回 QueryResult
        """
        # ── 场景上下文（如有）注入 user message ──────────────────
        user_message = message
        if current_blueprint:
            elements = current_blueprint.get("geometry", {}).get("elements", [])
            if elements:
                scene_summary = _build_scene_summary(current_blueprint)
                user_message = (
                    f"# 当前场景（你可以修改它）\n\n{scene_summary}\n\n"
                    f"# 用户请求\n\n{message}"
                )
                logger.info(f"[query] 注入场景上下文, 构件数={len(elements)}")

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
        reply = result["messages"][-1].content
        logger.info(f"Agent 回复: {reply[:200]}...")

        # ── 提取 JSON 并判断类型 ──────────────────────────────
        json_data = extract_blueprint_from_text(reply)
        if json_data is not None:
            # 判断是 Blueprint 还是 ScenePatch
            # Blueprint 有 "meta" 字段，ScenePatch 有 "operations" 字段
            if "meta" in json_data:
                # ── 生成类：完整 Blueprint ──────────────────────
                json_data = normalize_blueprint_input(json_data)
                pre_issues = validate_blueprint_schema(json_data)
                if pre_issues:
                    return QueryResult(
                        text=reply,
                        error=f"Blueprint 结构预检未通过: {'; '.join(pre_issues)}",
                    )

                # 重新检验和修复将大模型生成的结果
                pipeline_results = run_validation_pipeline(json_data)

                fatal_steps = _final_errors(pipeline_results)
                
                error_summary = None
                if fatal_steps:
                    error_summary = "校验流水线存在错误: " + "; ".join(
                        f"Step{r.step}({r.name})" for r in fatal_steps
                    )

                return QueryResult(
                    text=reply,
                    blueprint=json_data,
                    error=error_summary,
                    pipeline_results=pipeline_results,
                )

            elif "operations" in json_data and current_blueprint:
                # ── 修改类：ScenePatch ──────────────────────────
                patch = json_data
                modified_bp = _apply_patch_to_blueprint(current_blueprint, patch)
                modified_bp = normalize_blueprint_input(modified_bp)
                pre_issues = validate_blueprint_schema(modified_bp)
                if pre_issues:
                    return QueryResult(
                        text=reply,
                        patch=patch,
                        error=(
                            "Patch 应用后的 Blueprint 结构预检未通过: "
                            + "; ".join(pre_issues)
                        ),
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
                    patch=patch,
                    error=error_summary,
                    pipeline_results=pipeline_results,
                )

            else:
                # JSON 不匹配任何已知格式
                return QueryResult(
                    text=reply,
                    error="回复中的 JSON 不包含 'meta'（非 Blueprint）也不包含 'operations'（非 ScenePatch）",
                )

        # ── 纯文本（对话类）─────────────────────────────────────
        return QueryResult(text=reply)


# 模块级单例：导入 ws_agent 时完成配置、知识库索引和模型客户端初始化。
agent_service = AgentService()
