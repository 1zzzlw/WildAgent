"""受控网络研究与覆盖判断的纯逻辑回归测试，不依赖 LLM/网络/数据库。"""

import pytest

from app.agent.knowledge_topics import all_topic_keys, generation_knowledge_topics
from app.agent.research_evidence_gate import evaluate_knowledge_coverage
from app.agent.nodes.web_research_node import web_research_node
from app.agent.web.knowledge_claims import KnowledgeClaim, map_claim_to_capability
from app.agent.web.search_client import MockSearchClient, _validate_public_url
from app.spec.loader import RetrievedSpecChunk


def _chunk(doc_type: str, topic: str, entity_type: str | None = None) -> RetrievedSpecChunk:
    metadata = {"doc_type": doc_type, "topic": topic}
    if entity_type:
        metadata["entity_type"] = entity_type
    return RetrievedSpecChunk(document="x", metadata=metadata, distance=0.5)


# ── 覆盖判断 ──

def test_coverage_sufficient_when_all_required_hit():
    hits = [
        _chunk("recipe", "assembly", "stair"),
        _chunk("component", "parameters", "wall"),
        _chunk("recipe", "assembly"),
        _chunk("recipe", "fallback"),
    ]
    decision = evaluate_knowledge_coverage("高层玻璃幕墙", "high_rise", hits)
    assert decision.sufficient is True
    assert decision.trigger_web_research is False
    assert decision.missing_topics == []


def test_missing_engine_rules_reports_gap_without_web():
    hits = []
    decision = evaluate_knowledge_coverage("高层玻璃幕墙", "high_rise", hits)
    assert decision.sufficient is False
    assert decision.trigger_web_research is False
    assert "recipe.assembly" in decision.missing_required


def test_missing_local_retrieval_does_not_request_encyclopedia():
    decision = evaluate_knowledge_coverage("高层玻璃幕墙", "high_rise", [])
    assert decision.sufficient is False
    assert decision.trigger_web_research is False
    assert decision.coverage_ratio == 0.0


def test_any_building_type_uses_shared_generation_topics():
    decision = evaluate_knowledge_coverage("生成一个水电站", "unknown_type", [])
    # 未知类型复用能力与组装主题；没有类型卡不触发百科研究。
    assert decision.trigger_web_research is False
    assert "building_type.composition" not in decision.missing_topics


@pytest.mark.asyncio
async def test_terminal_model_error_skips_search_client(monkeypatch):
    calls = []

    def fail_if_created(**kwargs):
        calls.append(kwargs)
        raise AssertionError("terminal model error 后不应创建网络搜索客户端")

    monkeypatch.setattr(
        "app.agent.web.create_search_client",
        fail_if_created,
    )
    result = await web_research_node({
        "status": "failed",
        "terminal_model_error": {"category": "model_not_found"},
        "research_queries": ["高层玻璃幕墙规范"],
    })

    assert calls == []
    assert result["web_research_diag"]["reason"] == "blocked_by_terminal_model_error"


def test_topic_graph_has_no_duplicate_keys():
    keys = all_topic_keys()
    assert len(keys) == len({k for k in keys})


def test_generation_topics_nonempty():
    topics = generation_knowledge_topics()
    assert len(topics) >= 2
    assert any(t.required for t in topics)


# ── 能力映射 ──

def test_capability_mapping_keeps_supported_terms():
    claim = KnowledgeClaim(claim="玻璃幕墙由竖梃和横梃组成，外层用玻璃", topic="curtain_wall")
    mapped = map_claim_to_capability(claim)
    # 幕墙 → wall（基础元素）应映射；mullion 应降级；不能直接变不存在类型。
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
    # 无法映射的术语不能变成 WILD 类型；若完全没有支持映射则不可用。
    assert "quantum" not in map(str.lower, mapped.mapped_supported)


# ── SSRF / URL 防护 ──

@pytest.mark.parametrize("bad_url", [
    "file:///etc/passwd",
    "http://127.0.0.1:8000/admin",
    "http://localhost:3000",
    "http://192.168.1.1/secret",
    "http://10.0.0.5/",
])
def test_ssrf_rejects_local_urls(bad_url: str):
    with pytest.raises(ValueError):
        _validate_public_url(bad_url)


def test_ssrf_allows_public_https():
    url = _validate_public_url("https://example.com/spec")
    assert url.startswith("https://")


# ── Mock 搜索客户端 ──

@pytest.mark.asyncio
async def test_mock_search_returns_results():
    client = MockSearchClient()
    results = await client.search(__import__("app.agent.web.search_client", fromlist=["SearchQuery"]).SearchQuery("test"))
    assert len(results) >= 1
    assert results[0].url.startswith("https://")


@pytest.mark.asyncio
async def test_mock_fetch_page_works():
    client = MockSearchClient()
    content = await client.fetch_page("https://example.com/spec")
    assert "核心筒" in content
