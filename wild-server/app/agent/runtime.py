"""不进入 LangGraph State 的单次运行时上下文。

持久化 checkpointer 只能保存可序列化状态；WebSocket 推送回调与"本条目可用的工具集"
属于当前进程/当前条目的资源，通过 ContextVar 传给处理器，用完即丢。

这也是《动态节点设计规划》§2.8 第 ② 层的落点：单次执行需要的输入是**函数参数或
上下文变量**，不是 state 字段——它们既不需要跨节点，也不需要进 checkpoint。
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
from pathlib import Path
import platform
import subprocess
from typing import Any, Awaitable, Callable
from uuid import uuid4

SERVER_INSTANCE_ID = uuid4().hex


def _content_fingerprint(paths: list[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


@lru_cache(maxsize=1)
def runtime_fingerprint() -> dict[str, Any]:
    """首次追踪时固定进程源码快照；不读取 .env、密钥或历史产物。"""
    server = Path(__file__).resolve().parents[2]
    project = server.parent
    sources = list((server / "app").rglob("*.py"))
    sources += [server / name for name in ("config.py", "pyproject.toml", "uv.lock")
                if (server / name).is_file()]
    schemas = [path for path in (project / "wild-core/schema.json",
                               server / "storage/knowledge_base/schema.json") if path.is_file()]
    knowledge = [path for directory in ("knowledge", "rules")
                 for path in (server / "storage/knowledge_base" / directory).rglob("*")
                 if path.is_file() and path.suffix in {".md", ".json"}]
    revision, dirty = None, None
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project, check=True,
                                  capture_output=True, text=True, timeout=2).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=project, check=True,
                                    capture_output=True, text=True, timeout=2).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return {
        "server_instance_id": SERVER_INSTANCE_ID,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "snapshot_kind": "process_first_trace_source_files",
        "git_revision": revision, "git_dirty": dirty,
        "source_sha256": _content_fingerprint(sources, project),
        "prompt_sha256": _content_fingerprint([p for p in sources if "prompts" in p.parts], project),
        "schema_sha256": _content_fingerprint(schemas, project),
        "knowledge_sha256": _content_fingerprint(knowledge, project),
        "source_file_count": len(sources), "knowledge_file_count": len(knowledge),
        "python_version": platform.python_version(),
    }

ReasoningCallback = Callable[[str, str], Awaitable[None]]

_reasoning_callback: ContextVar[ReasoningCallback | None] = ContextVar(
    "wild_reasoning_callback",
    default=None,
)

#: 当前条目可用的工具集（plan.tool_registry.ToolSpec 元组）。
#: 这里刻意用 ``tuple[Any, ...]``：runtime 是底层模块，不该反向依赖 plan。
_item_tools: ContextVar[tuple[Any, ...] | None] = ContextVar(
    "wild_item_tools",
    default=None,
)


def get_reasoning_callback() -> ReasoningCallback | None:
    return _reasoning_callback.get()


def bind_reasoning_callback(callback: ReasoningCallback | None) -> Token:
    return _reasoning_callback.set(callback)


def reset_reasoning_callback(token: Token) -> None:
    _reasoning_callback.reset(token)


def get_item_tools() -> tuple[Any, ...] | None:
    """当前条目可用的工具集；``None`` 表示这条条目不走工具型处理器。"""

    return _item_tools.get()


def bind_item_tools(specs: tuple[Any, ...] | list[Any] | None) -> Token:
    return _item_tools.set(tuple(specs) if specs else None)


def reset_item_tools(token: Token) -> None:
    _item_tools.reset(token)
