"""外部知识检索阶段的提示词。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent.knowledge.web import WebResult


def build_claim_extraction_prompt(
    results: list[WebResult],
    missing_topics: list[str],
) -> str:
    """把网页正文包装为结构化知识声明提取任务。"""
    payloads = [
        f"### {result.title}\nURL: {result.url}\n来源: {result.source}"
        f"\n正文:\n{result.content[:2500]}"
        for result in results[:4]
    ]
    web_text = "\n\n".join(payloads)
    return f"""你是建筑知识整理助手。把下面网页资料整理成结构化知识声明，供本次建筑生成参考。

# 任务
- 每条声明必须是对建筑构成、构件组合、规范数值或降级建议的事实断言。
- 不要输出设计过程、营销话术或无法落地的抽象描述。
- 目标建筑类型：{", ".join(missing_topics) or "通用"}。

# 输出协议
只输出 JSON 数组，每个元素:
{{"claim": "事实断言", "topic": "主题", "applicable_building_types": ["建筑类型"],
  "region": "地区或留空", "year": "年份或留空", "norm_code": "规范号或留空",
  "source_url": "来源URL", "source_org": "来源机构", "confidence": "high|medium|low"}}

# 网页资料
{web_text}
"""
