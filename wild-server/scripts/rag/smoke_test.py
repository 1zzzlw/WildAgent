"""Chroma RAG 检索的独立冒烟测试。

它不读取线上持久化索引，也不调用远程 embedding；测试结束后临时索引会被删除。
在 ``wild-server`` 目录运行：

    python -m app.rag.smoke_test
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from app.spec.loader import HashEmbeddingFunction, RAGSpecLoader, collect_markdown_paths


# 所有路径从当前文件反推，避免运行命令所在目录改变知识库位置。
SERVER_ROOT = Path(__file__).resolve().parents[2]
KB = SERVER_ROOT / "storage" / "knowledge_base"
# 最小规范在真实服务中直接注入 Prompt，因此不应重复进入 RAG 候选。
BASE_SPEC_PATHS = [
    KB / "BLUEPRINT-SPEC-MINIMAL.md",
]
RAG_SPEC_PATHS = collect_markdown_paths(KB, exclude=BASE_SPEC_PATHS)


def main() -> None:
    """构建一次临时索引，并验证几类代表性查询能够召回预期关键词。"""
    # TemporaryDirectory 保证 smoke test 不污染 storage/chroma 中的真实索引。
    with TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        loader = RAGSpecLoader(
            base_paths=[str(path) for path in BASE_SPEC_PATHS],
            rag_paths=[str(path) for path in RAG_SPEC_PATHS],
            persist_dir=tmp_dir,
            collection_name="wild_rag_smoke",
            # 本地 hash embedding 让测试无需 API key，验证重点是完整检索链路。
            embedding_function=HashEmbeddingFunction(),
            top_k=4,
            chunk_size=900,
            chunk_overlap=150,
        )

        # 每项只要求命中任意一个关键词，避免分片或排序微调造成脆弱测试。
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
            # load() 同时触发检索和上下文拼接，last_results 暴露本次原始命中。
            context = loader.load(query)
            hits = loader.last_results
            if not hits:
                raise AssertionError(f"RAG query 没有召回结果: {query}")

            matched = [
                term for term in expected_terms
                if term.lower() in context.lower()
            ]
            if not matched:
                # 失败时输出来源与标题，方便判断是扫描、分片还是召回问题。
                sources = [
                    f"{hit.metadata.get('source')} / {hit.metadata.get('heading')}"
                    for hit in hits
                ]
                raise AssertionError(
                    f"RAG query 未命中预期关键词: {query}, hits={sources}"
                )

            print(f"[OK] {query} -> {len(hits)} hits, matched={matched}")


if __name__ == "__main__":
    # 仅直接执行模块时运行；被测试框架导入不会自动构建索引。
    main()
