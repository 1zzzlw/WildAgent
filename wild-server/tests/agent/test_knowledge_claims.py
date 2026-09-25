"""外部知识的离线入库：声明 → 能力映射 → staging。

在线研究节点已随旧计划层删除，但"离线补课"这条链路还在（`scripts/kb/promote_staged.py`
人工审核后并入知识库），所以能力映射的安全性仍然要有用例看住：
**外部资料里的术语不能变成 WILD 不存在的构件类型**，映射不上就只能降级或丢弃。
"""

from __future__ import annotations

from app.agent.knowledge.web import KnowledgeClaim, map_claim_to_capability
from app.agent.knowledge.web.staging import claim_to_markdown


def test_capability_mapping_keeps_supported_terms():
    claim = KnowledgeClaim(claim="玻璃幕墙由竖梃和横梃组成，外层用玻璃", topic="curtain_wall")
    mapped = map_claim_to_capability(claim)

    # 幕墙 → wall（基础元素）应映射；竖梃/横梃应降级；不能直接变不存在类型。
    assert mapped.usable is True
    assert "wall" in mapped.mapped_supported
    assert any(("竖梃" in d) or ("横梃" in d) for d in mapped.degraded_to)


def test_capability_mapping_degradation_for_mullion():
    claim = KnowledgeClaim(claim="幕墙龙骨使用 mullion 连接玻璃面板", topic="curtain_wall")
    mapped = map_claim_to_capability(claim)

    assert mapped.usable is True
    assert any("mullion" in d for d in mapped.degraded_to)


def test_capability_mapping_drops_unmappable():
    claim = KnowledgeClaim(claim="这种新型构造叫量子光子墙，没有对应构件", topic="novel")
    mapped = map_claim_to_capability(claim)

    # 无法映射的术语不能变成 WILD 类型
    assert "quantum" not in map(str.lower, mapped.mapped_supported)


def test_staged_markdown_carries_provenance_and_capability_note():
    claim = KnowledgeClaim(
        claim="幕墙由竖梃和横梃组成",
        topic="curtain_wall",
        source_url="https://example.com/spec",
        norm_code="GB50016-2014",
    )

    markdown = claim_to_markdown(claim, request_id="req_stage")

    assert "幕墙由竖梃和横梃组成" in markdown
    assert "https://example.com/spec" in markdown
    assert "GB50016-2014" in markdown
    # 能力映射（含降级）必须写进正文：人工审核时才能判断"这条知识能不能用"
    assert "curtain_wall" in markdown
