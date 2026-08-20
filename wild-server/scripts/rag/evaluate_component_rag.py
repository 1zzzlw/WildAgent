"""运行组合构件固定 RAG 评测集。

在 wild-server 目录执行：

    .venv\\Scripts\\python.exe scripts\\evaluate_component_rag.py

评测使用临时 Chroma 集合和本地 HashEmbeddingFunction，不读取 API Key，
也不修改 ``storage/chroma``。它验证的是项目真实分片、metadata 过滤、索引和
检索链路；线上 embedding 的语义排序仍需单独做环境评测。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.spec.loader import HashEmbeddingFunction, RAGSpecLoader, collect_markdown_paths


KNOWLEDGE_BASE = SERVER_ROOT / "storage" / "knowledge_base"
BASE_SPEC_PATHS = [KNOWLEDGE_BASE / "BLUEPRINT-SPEC-MINIMAL.md"]
DEFAULT_CASES = SERVER_ROOT / "evals" / "component_rag_cases.json"


def main() -> None:
    payload = json.loads(DEFAULT_CASES.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise AssertionError("component_rag_cases.json 必须包含非空 cases 数组")

    rag_paths = collect_markdown_paths(KNOWLEDGE_BASE, exclude=BASE_SPEC_PATHS)
    with TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        loader = RAGSpecLoader(
            base_paths=[str(path) for path in BASE_SPEC_PATHS],
            rag_paths=[str(path) for path in rag_paths],
            persist_dir=temp_dir,
            collection_name="wild_component_rag_eval",
            embedding_function=HashEmbeddingFunction(),
            top_k=6,
            chunk_size=900,
            chunk_overlap=150,
        )

        failures: list[str] = []
        for case in cases:
            failures.extend(evaluate_case(loader, case))

        if failures:
            raise AssertionError("\n".join(failures))
        print(f"Component RAG evaluation passed: {len(cases)} cases, {loader.last_sync_stats['total']} chunks.")


def evaluate_case(loader: RAGSpecLoader, case: dict[str, Any]) -> list[str]:
    case_id = str(case.get("id") or "unknown")
    query = str(case.get("query") or "").strip()
    metadata_filter = case.get("metadataFilter")
    if not query or not isinstance(metadata_filter, dict):
        return [f"[{case_id}] 缺少 query 或 metadataFilter"]

    hits = loader.retrieve(query, metadata_filter=metadata_filter)
    if not hits:
        return [f"[{case_id}] 没有召回结果"]

    sources = [str(hit.metadata.get("source") or "") for hit in hits]
    documents = "\n".join(hit.document for hit in hits).lower()
    expected_sources = [str(source) for source in case.get("expectedSources", [])]
    required_terms = [str(term) for term in case.get("requiredTerms", [])]
    failures: list[str] = []

    if expected_sources and not any(
        source.endswith(expected) for source in sources for expected in expected_sources
    ):
        failures.append(f"[{case_id}] 来源不匹配: hits={sources}")

    missing_terms = [term for term in required_terms if term.lower() not in documents]
    if missing_terms:
        failures.append(
            f"[{case_id}] 缺少关键词 {missing_terms}: hits={sources}"
        )

    forbidden = [
        source
        for source, hit in zip(sources, hits)
        if hit.metadata.get("status") == "proposed"
        or hit.metadata.get("authority") == "inferred"
    ]
    if forbidden:
        failures.append(f"[{case_id}] 正式检索混入 proposed/inferred: {forbidden}")

    if not failures:
        print(f"[OK] {case_id}: {sources[:3]}")
    return failures


if __name__ == "__main__":
    main()
