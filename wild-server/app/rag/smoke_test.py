"""Standalone smoke test for Chroma RAG retrieval.

Run from wild-server:
    python -m app.rag.smoke_test
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from app.spec.loader import HashEmbeddingFunction, RAGSpecLoader, collect_markdown_paths


SERVER_ROOT = Path(__file__).resolve().parents[2]
KB = SERVER_ROOT / "storage" / "knowledge_base"
BASE_SPEC_PATHS = [
    KB / "BLUEPRINT-SPEC-MINIMAL.md",
]
RAG_SPEC_PATHS = collect_markdown_paths(KB, exclude=BASE_SPEC_PATHS)


def main() -> None:
    with TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        loader = RAGSpecLoader(
            base_paths=[str(path) for path in BASE_SPEC_PATHS],
            rag_paths=[str(path) for path in RAG_SPEC_PATHS],
            persist_dir=tmp_dir,
            collection_name="wild_rag_smoke",
            embedding_function=HashEmbeddingFunction(),
            top_k=4,
            chunk_size=900,
            chunk_overlap=150,
        )

        checks = [
            ("生成一个中式四角凉亭", ["凉亭", "Pavilion"]),
            (
                "生成一个别墅 默认材质 配色 外墙 屋顶 门窗 玻璃透明度",
                ["wall_plaster", "默认配色", "opacity"],
            ),
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
