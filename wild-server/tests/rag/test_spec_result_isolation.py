"""并发检索不能用另一条请求的最近命中重建来源。"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

from app.agent.plan.knowledge_tool import search_knowledge_result
from app.rag.trace import rag_trace_scope
from app.spec.loader import FileSpecLoader, RAGSpecLoader, RetrievedSpecChunk


def test_parallel_component_queries_keep_their_own_text_and_chunk_ids(monkeypatch):
    from app.services import agent_service as service_module
    loader = object.__new__(RAGSpecLoader)
    loader._max_context_chars = 18000
    loader._apply_retrieval_gate = lambda hits, **kwargs: hits
    ready = Barrier(2)

    def retrieve_many(queries, per_query):
        family = queries[0].metadata_filter["entity_type"]
        hit = RetrievedSpecChunk('```json\n{"type":"' + family + '"}\n```',
            {"source": family + ".md", "heading": family, "entity_type": family},
            0.1, family + "_chunk")
        ready.wait(timeout=5)
        return [hit]

    loader.retrieve_many = retrieve_many
    monkeypatch.setattr(service_module, "agent_service", SimpleNamespace(spec_loader=loader))

    def query(family):
        with rag_trace_scope("request_" + family, persist=False) as trace:
            result = search_knowledge_result("JSON 示例", kind=family)
        return result, trace

    with ThreadPoolExecutor(max_workers=2) as executor:
        door, window = list(executor.map(query, ("door", "window")))
    for family, (result, trace) in zip(("door", "window"), (door, window)):
        other = "window" if family == "door" else "door"
        assert family + ".md" in result["text"] and other + ".md" not in result["text"]
        assert result["chunk_ids"] == [family + "_chunk"]
        assert result["has_shape_reference"]
        assert trace.contexts[-1]["injected_chunk_ids"] == [family + "_chunk"]
    assert not hasattr(loader, "last_results")


def test_result_hits_only_include_whole_chunks_actually_injected():
    loader = object.__new__(RAGSpecLoader)
    small = RetrievedSpecChunk("window", {"source": "window.md"}, 0.1, "small")
    large = RetrievedSpecChunk("x" * 1000, {"source": "large.md"}, 0.1, "large")
    loader._max_context_chars = len(loader._format_retrieved([small])) + 100
    result = loader._compose_result("BASE", [small, large])
    assert result.hits == (small,)
    assert result.chunk_ids == ("small",)
    assert "window" in result.text and large.document not in result.text


def test_file_loader_result_preserves_string_api_and_has_no_vector_hits(tmp_path):
    source = tmp_path / "protocol.md"
    source.write_text("WILD fields", encoding="utf-8")
    loader = FileSpecLoader([str(source)])
    assert loader.load_result().text == loader.load()
    assert loader.load_many_result(["window"]).text == loader.load_many(["window"])
    assert loader.load_many_result(["window"], include_base=False).text == ""
    assert loader.load_many_result(["window"]).hits == ()
