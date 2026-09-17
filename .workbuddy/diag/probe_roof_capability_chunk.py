"""打印"屋顶构件能力"查询实际命中的分片正文，确认知识库矛盾已消除。

跑法：
    cd wild-server
    ./.venv/Scripts/python.exe ../.workbuddy/diag/probe_roof_capability_chunk.py
"""
from __future__ import annotations

import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[2] / "wild-server"
sys.path.insert(0, str(SERVER_ROOT))

from app.spec.loader import MarkdownChunker  # noqa: E402

KB = SERVER_ROOT / "storage" / "knowledge_base"
CFG = KB / "config.yaml"
TARGET = KB / "knowledge" / "components" / "capability-boundaries.md"


def main() -> int:
    chunker = MarkdownChunker(metadata_config_path=CFG)
    chunks = chunker.split_file(
        TARGET, namespace="probe", doc_scope="generation",
    )
    print(f"{TARGET.name}: {len(chunks)} 块\n")

    for chunk in chunks:
        heading = chunk.metadata.get("heading") or ""
        if "3.5" not in heading and "屋顶" not in heading:
            continue
        print("=" * 78)
        print("heading     :", heading)
        print("doc_type    :", chunk.metadata.get("doc_type"))
        print("knowledge_role:", chunk.metadata.get("knowledge_role"))
        print("entity_type :", chunk.metadata.get("entity_type"))
        print("-" * 78)
        print(chunk.document)
        print()

    # 矛盾关键词复查
    text = TARGET.read_text(encoding="utf-8")
    print("=" * 78)
    for needle in ("❌ 复杂组合屋顶", "❌ 用一个 `roof` 元素", "多体量分段屋顶"):
        print(f"{'仍存在 ✗' if needle in text else '已消除 ✓'}  {needle!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
