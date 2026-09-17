"""探针：找出能在 top_k=4 下召回 glass-curtain-wall-assembly.md 的查询写法。

背景：scripts/rag/smoke_test.py 的官方断言要挑选"真实知识库里存在、且在
HashEmbeddingFunction 下可召回"的关键词。幕墙文档在索引里（日志可见），
但旧查询写法召回不到，需要确认哪种问法稳定命中。

用法：
    cd wild-server
    ./.venv/Scripts/python.exe ../.workbuddy/diag/probe_curtain_recall_2026-09-17.py
"""
from __future__ import annotations

import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[2] / "wild-server"
sys.path.insert(0, str(SERVER_ROOT))

from app.spec.loader import (  # noqa: E402
    HashEmbeddingFunction,
    RAGSpecLoader,
    collect_markdown_paths,
)

KB = SERVER_ROOT / "storage" / "knowledge_base"
BASE = [
    KB / "knowledge" / "protocol" / "blueprint-skeleton.md",
    KB / "knowledge" / "protocol" / "generation-redlines.md",
]
RAG = collect_markdown_paths(KB, exclude=BASE)

QUERIES = [
    "玻璃幕墙 竖梃 分格 pane_module",
    "玻璃幕墙确定性生成参数 分格",
    "幕墙 骨架 玻璃 组装 关系",
    "玻璃幕墙参数 分格尺寸 竖梃数",
    "玻璃幕墙 方案 A 墙体宿主 网格窗",
    "幕墙 骨架 七条关系",
]

PERSIST = SERVER_ROOT.parent / ".workbuddy" / "diag" / "_tmp_chroma_probe"


def main() -> None:
    # 固定目录 + 每轮重建，避免 TemporaryDirectory 在 Windows 上被 Chroma 占用导致清理失败。
    import shutil

    shutil.rmtree(PERSIST, ignore_errors=True)
    PERSIST.mkdir(parents=True, exist_ok=True)

    loader = RAGSpecLoader(
        base_paths=[str(p) for p in BASE],
        rag_paths=[str(p) for p in RAG],
        persist_dir=str(PERSIST),
        collection_name="probe_curtain",
        embedding_function=HashEmbeddingFunction(),
        top_k=4,
    )
    for query in QUERIES:
        loader.load(query)
        hits = loader.last_results
        sources = [h.metadata.get("source_file") for h in hits]
        mark = "HIT" if "glass-curtain-wall-assembly.md" in sources else "miss"
        print(f"[{mark}] {query}\n        {sources}")


if __name__ == "__main__":
    main()
