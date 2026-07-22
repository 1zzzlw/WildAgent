"""
Agent Service —— Agent 生命周期管理和对话入口

职责：组装 spec_loader + tools + prompt + llm，对外提供统一的 query() / query_structured() 接口。

升级路径（每次只改内部，query() 接口和 ws_agent.py 不动）：
  现在   → FileSpecLoader + create_agent + tools
  以后1  → RAGSpecLoader（只改 loader 一行）
  以后2  → LangGraph graph.ainvoke()（只改编排，tools 复用）
"""
from dataclasses import dataclass
from pathlib import Path

from langchain.agents import create_agent
from loguru import logger

from app.agent.model_client import create_llm
from app.agent.prompts import build_system_prompt
from app.spec.loader import FileSpecLoader
from app.tools.spatial_tools import (
    fix_opening_coords,
    validate_blueprint_structure,
    validate_element_required_fields,
    validate_opening_coords,
    validate_roof_coverage,
    validate_stair_alignment,
    validate_wall_junctions,
)
from app.utils.blueprint_parser import extract_blueprint_from_text, validate_blueprint_schema

# ---------- 规范文档路径 ----------
# 基于本文件位置解析，不依赖工作目录
_SERVER_ROOT = Path(__file__).resolve().parent.parent  # wild-server/
_KB = _SERVER_ROOT / "storage" / "knowledge_base"

SPEC_PATHS = [
    _KB / "BLUEPRINT-SPEC-MINIMAL.md",
]


@dataclass
class QueryResult:
    """AgentService.query_structured() 的结构化返回结果

    - text: 完整 LLM 回复文本（始终存在）
    - blueprint: 从回复中提取的 Blueprint dict（可能为 None）
    - error: 解析/校验错误描述（无错误时为 None）
    """
    text: str
    blueprint: dict | None = None
    error: str | None = None


class AgentService:
    """Agent 服务

    生命周期：
    - 构造时：加载规范文档 + 创建 LLM + 注册 tools + 组装 System Prompt
    - query()：每次调用复用同一个 agent 实例
    - 后续升级：spec 换 RAG / 编排换 LangGraph，外部接口不变
    """

    def __init__(self):
        # ===== 1. 加载规范文档 =====
        # 以后换 RAG：self.spec_loader = RAGSpecLoader(retriever)
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

        # ===== 4. 注册 Tools =====
        # 以后新增校验 tool：在本模块 import 并加入此列表即可
        tools = [
            validate_blueprint_structure,
            validate_element_required_fields,
            validate_opening_coords,
            validate_wall_junctions,
            validate_roof_coverage,
            validate_stair_alignment,
            fix_opening_coords,
        ]
        logger.info(f"已注册 {len(tools)} 个工具: {[t.name for t in tools]}")

        # ===== 5. 创建 Agent =====
        # 以后换 LangGraph：self.graph = create_graph(...)
        # query() 内部从 self.agent.ainvoke() 改为 self.graph.ainvoke()
        self.agent = create_agent(
            model=self.llm,
            tools=tools,
            system_prompt=system_prompt,
        )
        logger.info("AgentService 初始化完成")

    async def query(self, message: str) -> str:
        """执行一次对话，返回 AI 回复文本（向后兼容）

        接口签名永不改变，ws_agent.py 零感知升级。
        """
        result = await self.agent.ainvoke({
            "messages": [{"role": "user", "content": message}]
        })
        reply = result["messages"][-1].content
        logger.info(f"Agent 回复: {reply[:120]}...")
        return reply

    async def query_structured(self, message: str) -> QueryResult:
        """执行一次对话，返回结构化的 QueryResult（包含提取的 Blueprint）

        1. 调用 LLM（复用已有 agent 实例，无额外开销）
        2. 从回复文本提取 ```json 代码块
        3. 轻量结构校验
        4. 返回 QueryResult(text, blueprint, error)
        """
        result = await self.agent.ainvoke({
            "messages": [{"role": "user", "content": message}]
        })
        reply = result["messages"][-1].content
        logger.info(f"Agent 回复: {reply[:120]}...")

        blueprint = extract_blueprint_from_text(reply)
        if blueprint is None:
            return QueryResult(
                text=reply,
                error="未能在回复中找到有效的 Blueprint JSON 代码块",
            )

        issues = validate_blueprint_schema(blueprint)
        if issues:
            return QueryResult(
                text=reply,
                blueprint=blueprint,
                error=f"Blueprint 结构校验未通过: {'; '.join(issues)}",
            )

        return QueryResult(text=reply, blueprint=blueprint)


# 模块级单例，供 api/ws_agent.py 通过 import 获取
# ws_agent.py 的 import 行为不变：from app.services.agent_service import agent_service
agent_service = AgentService()
