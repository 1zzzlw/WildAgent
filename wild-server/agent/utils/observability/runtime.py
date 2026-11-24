"""进程与知识库指纹，用于生成链路的可追溯诊断。"""

from __future__ import annotations
from common.paths import SERVER_ROOT

from datetime import datetime, timezone
from functools import lru_cache
import hashlib
from pathlib import Path
import platform
import subprocess
from typing import Any
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
def _process_fingerprint() -> dict[str, Any]:
    """首次追踪时固定进程源码快照；不读取 .env、密钥或历史产物。"""
    server = SERVER_ROOT
    project = server.parent
    sources = [
        path
        for package in ("app", "agent", "common", "integration")
        for path in (server / package).rglob("*.py")
    ]
    sources += [server / name for name in ("main.py", "config.py", "pyproject.toml", "uv.lock")
                if (server / name).is_file()]
    schemas = [path for path in (project / "wild-core/schema.json",
                               server / "storage/knowledge_base/schema.json") if path.is_file()]
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
        "source_file_count": len(sources),
        "python_version": platform.python_version(),
    }


def runtime_fingerprint() -> dict[str, Any]:
    """源码是进程首轮文件快照；可热更新知识按本次执行重新取摘要。"""
    server = SERVER_ROOT
    root = server / "storage/knowledge_base"
    knowledge = []
    for directory in ("knowledge", "rules"):
        for current_path in (root / directory).rglob("*"):
            if not (current_path.is_file() and current_path.suffix in {".md", ".json"}):
                continue
            knowledge.append(current_path)
    knowledge.extend(path for path in (root / "config.yaml", root / "schema.json") if path.is_file())
    return {**_process_fingerprint(), "knowledge_sha256": _content_fingerprint(knowledge, server.parent),
            "knowledge_file_count": len(knowledge), "knowledge_snapshot_kind": "execution_source_files"}

