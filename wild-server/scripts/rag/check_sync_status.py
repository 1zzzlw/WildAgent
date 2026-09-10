r"""检查当前 RAG Loader、后台同步和持久化集合状态。

在 ``wild-server`` 目录运行：

    .\.venv\Scripts\python.exe -m scripts.rag.check_sync_status
    .\.venv\Scripts\python.exe -m scripts.rag.check_sync_status --wait-seconds 120

导入 AgentService 只会启动后台同步，不会在主线程等待全量 Embedding。
"""

from __future__ import annotations

import argparse
import sys
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=0,
        help="最多等待后台同步多少秒；0 表示只读取当前状态",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    # 先解析参数，让 --help 不需要初始化 Agent、Chroma 或 Embedding。
    from app.services.agent_service import agent_service
    from app.spec.loader import RAGSpecLoader

    loader = agent_service.spec_loader
    print(f"Spec Loader: {type(loader).__name__}")
    print(f"来源文档数: {len(loader.list_sources())}")

    if not isinstance(loader, RAGSpecLoader):
        print("RAG 未启用或初始化失败，当前使用文件兜底模式。")
        return 2

    deadline = time.time() + max(0.0, args.wait_seconds)
    while args.wait_seconds > 0:
        phase = loader.sync_status.get("phase")
        if phase not in {"pending", "syncing"} or time.time() >= deadline:
            break
        time.sleep(0.5)

    status = loader.sync_status
    stats = loader.last_sync_stats
    print(f"同步阶段: {status.get('phase', 'unknown')}")
    print(f"同步尝试次数: {status.get('attempts', 0)}")
    print(f"本轮发现分片: {stats['total']}")
    print(f"本轮更新分片: {stats['updated']}")
    print(f"本轮删除分片: {stats['deleted']}")
    print(f"仍待同步分片: {status.get('pending_chunks', loader.last_sync_pending)}")
    print(f"最后成功时间: {status.get('last_success_at') or '尚无'}")
    if status.get("last_error"):
        print(f"最后错误: {status['last_error']}")

    try:
        collection = loader._get_collection()
        indexed = collection.get(
            where={"namespace": loader._namespace},
            include=["metadatas"],
        )
        print(f"当前持久化分片: {len(indexed.get('ids') or [])}")
        print(f"当前索引签名: {(collection.metadata or {}).get('index_signature', 'missing')}")
    except Exception as exc:
        print(f"持久化集合不可读: {type(exc).__name__}: {exc}")
        return 2

    return 0 if status.get("phase") == "ok" else 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    try:
        exit_code = main()
    except OSError as exc:
        if getattr(exc, "winerror", None) != 10106:
            raise
        print(
            "无法加载 Windows asyncio/_overlapped（WinError 10106）；"
            "请先使用 migrate_embedding_index status 做纯离线索引审计。",
            file=sys.stderr,
        )
        exit_code = 2
    raise SystemExit(exit_code)
