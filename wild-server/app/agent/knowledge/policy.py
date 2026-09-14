"""生成知识的用途边界；不依赖模型、向量库或建筑类型硬编码。"""
from __future__ import annotations

import re


KNOWLEDGE_REVISION = "rules-v3"
GENERATION_ROLES = ("protocol", "capability", "relation")

KNOWLEDGE_GUIDANCE = """知识使用约定：
- protocol/capability/relation 说明当前 WILD 能力与已选择构件的正确关系。
- 建筑类型与风格语义由模型理解；知识库不提供建筑百科或类型模板。
- 用户明确需求与已批准方案决定层数、轮廓、尺寸、材质和构件选择；参考知识不能静默改写这些决定。
- 未指定的设计变量由本次方案推导，不套用案例尺寸、固定配色、默认退台或固定构件套餐。
- 数值示例只解释局部字段；可渲染、几何校验通过不代表结构或专业规范合规。
"""


def term_is_requested(text: str, term: str) -> bool:
    """匹配显式术语，并排除紧邻的简单否定；复杂意图仍由规划节点处理。"""
    if not term.strip():
        return False
    for match in re.finditer(re.escape(term.strip()), text, re.IGNORECASE):
        prefix = text[max(0, match.start() - 12):match.start()]
        if not re.search(r"(?:不要|不采用|不使用|不需要|排除|避免|非|without\s+|not\s+)\s*$", prefix, re.I):
            return True
    return False


def knowledge_hit_applies(query: str, metadata: dict) -> bool:
    """专用系统规则只有在请求或已批准方案点名时才进入上下文。"""
    if not metadata.get("applies_to"):
        return True
    terms = metadata.get("applies_to") or metadata.get("primary_terms") or ""
    if isinstance(terms, str):
        terms = [term.strip() for term in terms.split(",")]
    return any(term_is_requested(query, str(term)) for term in terms)


def plan_knowledge_query(message: str, plan: dict | None) -> str:
    """后续节点检索本次方案的已选系统，不把整份坐标蓝图重复用于语义检索。"""
    if not isinstance(plan, dict):
        return message
    roof = plan.get("roof") or {}
    grid = plan.get("structural_grid") or {}
    circulation = plan.get("circulation") or {}
    terms = [str(plan.get("concept") or ""), str(roof.get("type") or ""),
             str(grid.get("system") or ""), str(circulation.get("vertical_strategy") or "")]
    if plan.get("curtain_wall") is True:
        terms.append("curtain_wall 玻璃幕墙")
    terms.extend(str(item) for item in plan.get("required_components", []))
    terms.extend(str(item) for item in plan.get("detail_packages", []))
    return message + "\n已选方案系统：" + "、".join(term for term in terms if term)


def chat_knowledge_query_specs(message: str) -> list[tuple[str, dict[str, str]]]:
    """返回知识问答的三类受控检索意图，不依赖 Loader 以便离线测试。"""
    return [
        (
            f"{message} ScenePatch Blueprint 坐标 字段 引用",
            {"doc_type": "blueprint_spec", "knowledge_role": "protocol"},
        ),
        (
            f"{message} 当前构件字段 参数 能力边界",
            {"doc_type": "component", "knowledge_role": "capability"},
        ),
        (
            f"{message} 宿主 组装 连接 校验关系",
            {"doc_type": "recipe", "knowledge_role": "relation"},
        ),
    ]
