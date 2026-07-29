"""Standalone smoke test for Chroma RAG retrieval.

Run from wild-server:
    python -m app.rag.smoke_test
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from app.spec.loader import HashEmbeddingFunction, RAGSpecLoader


SERVER_ROOT = Path(__file__).resolve().parents[2]
KB = SERVER_ROOT / "storage" / "knowledge_base"


def main() -> None:
    with TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        loader = RAGSpecLoader(
            base_paths=[str(KB / "BLUEPRINT-SPEC-MINIMAL.md")],
            rag_paths=[
                str(KB / "BLUEPRINT-SPEC-FULL.md"),
                str(KB / "BUILDING-TYPES-REFERENCE.md"),
            ],
            persist_dir=tmp_dir,
            collection_name="wild_rag_smoke",
            embedding_function=HashEmbeddingFunction(),
            top_k=4,
            chunk_size=900,
            chunk_overlap=150,
        )

        checks = [
            ("生成一个中式四角凉亭", ["凉亭", "Pavilion"]),
            ("opening 坐标 parentWall from[0]", ["opening", "parentWall", "from[0]"]),
            ("屋顶 span depth 覆盖墙体", ["屋顶", "span", "depth"]),
        ]

        for query, expected_terms in checks:
            context = loader.load(query)
            hits = loader.last_results
            if not hits:
                raise AssertionError(f"RAG query 没有召回结果: {query}")

            matched = [
                term for term in expected_terms
                if term.lower() in context.lower()
            ]
            if not matched:
                sources = [
                    f"{hit.metadata.get('source')} / {hit.metadata.get('heading')}"
                    for hit in hits
                ]
                raise AssertionError(
                    f"RAG query 未命中预期关键词: {query}, hits={sources}"
                )

            print(f"[OK] {query} -> {len(hits)} hits, matched={matched}")


if __name__ == "__main__":
    main()
