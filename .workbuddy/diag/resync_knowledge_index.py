"""重建 RAG 索引，确认刚改的知识库文档被重新向量化。

改了 `storage/knowledge_base/**` 的正文后，**必须等索引同步完成改动才真正生效**
（切块内容变了 → 内容哈希变了 → 该块要重新向量化）。

跑法：
    cd wild-server
    ./.venv/Scripts/python.exe ../.workbuddy/diag/resync_knowledge_index.py
"""
from __future__ import annotations

import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[2] / "wild-server"
sys.path.insert(0, str(SERVER_ROOT))


def main() -> int:
    from app.services.agent_service import AgentService

    service = AgentService()
    loader = service.spec_loader
    print(f"loader: {type(loader).__name__}")
    if not hasattr(loader, "sync_index"):
        print("此 loader 没有 sync_index（可能是降级的基础文件 Loader）")
        return 1

    stats = loader.sync_index()
    print("sync_index ->", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
