"""候选知识隔离区：把已验证的网络知识写成候选 Markdown。

候选知识进入 storage/knowledge_staging/，不进入正式 knowledge_base/。
正式入库前必须经过：来源声明、能力映射、分片预览、去重，以及人工批准
（scripts/kb/promote_staged.py）。staging 用独立 Chroma namespace 隔离。
"""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path
from typing import Any

from loguru import logger

from app.agent.web.knowledge_claims import KnowledgeClaim

# staging 根目录（相对 wild-server 根）
STAGING_ROOT = Path(__file__).resolve().parents[3] / "storage" / "knowledge_staging" / "web"


def _safe_slug(text: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^\w一-鿿-]+", "-", str(text).strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:max_len] or "candidate"


def claim_to_markdown(
    claim: KnowledgeClaim,
    *,
    request_id: str = "",
    staged_at: str = "",
) -> str:
    """把一条可用声明转成候选知识 Markdown（带完整来源与能力映射记录）。"""
    if not staged_at:
        staged_at = _dt.date.today().isoformat()
    mapping_lines = []
    for degraded in claim.degraded_to:
        mapping_lines.append(f"- {degraded}")
    for supported in claim.mapped_supported:
        mapping_lines.append(f"- `{supported}`（引擎原生支持）")
    if not mapping_lines:
        mapping_lines = ["- （无可用能力映射，声明已被过滤，不应入库）"]

    unmapped_note = ""
    if claim.unmapped_terms:
        unmapped_note = (
            "\n> 未映射术语（已丢弃，不得写入 Blueprint）："
            + "、".join(claim.unmapped_terms[:8])
        )

    return f"""---
entity_name: {_safe_slug(claim.claim)}
topic: composition
status: staged
authority: web_research
source: web/{_safe_slug(claim.claim)}.md
source_url: {claim.source_url}
source_org: {claim.source_org}
staged_at: {staged_at}
request_id: {request_id}
region: {claim.region}
year: {claim.year}
norm_code: {claim.norm_code}
confidence: {claim.confidence}
primary_terms:
  - {claim.topic}
synonyms: []
---

# 网络候选知识：{claim.topic}

> 来源：{claim.source_url or '未知'}（{claim.source_org or '未知机构'}，{claim.year or '年份未知'}）。
> 用途：本地知识覆盖不足时补充的候选知识，仅限本次请求临时使用；入库前需人工审核。

## 事实声明

{claim.claim}

## WILD 能力映射

{chr(10).join(mapping_lines)}
{unmapped_note}

## 适用建筑类型

{", ".join(claim.applicable_building_types) or "通用"}
"""


def write_claim_to_staging(claim: KnowledgeClaim, *, request_id: str = "") -> Path | None:
    """把可用声明写入 staging 目录（按月份分目录）。返回写入路径，失败返回 None。"""
    if not claim.usable:
        logger.info(f"[staging] 声明不可用，跳过写入: {claim.claim[:60]}")
        return None
    month_dir = STAGING_ROOT / _dt.date.today().strftime("%Y-%m")
    month_dir.mkdir(parents=True, exist_ok=True)
    path = month_dir / f"{_safe_slug(claim.claim)}.md"
    content = claim_to_markdown(claim, request_id=request_id)
    # 幂等：同 claim 重复写入覆盖（URL/正文哈希已去重）。
    path.write_text(content, encoding="utf-8")
    logger.info(f"[staging] 候选知识已写入隔离区: {path.relative_to(STAGING_ROOT)}")
    return path


def list_staged_files() -> list[Path]:
    """列出 staging 目录下所有候选 Markdown。"""
    if not STAGING_ROOT.exists():
        return []
    return sorted(STAGING_ROOT.rglob("*.md"))
