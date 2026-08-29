"""运行时 ``.env`` 文件的固定路径与安全写入工具。"""

from __future__ import annotations

import errno
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Mapping


SERVER_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ENV_PATH_KEY = "WILD_RUNTIME_ENV_FILE"
RUNTIME_ENV_PERSISTENT_KEY = "WILD_RUNTIME_ENV_PERSISTENT"
RUNTIME_ENV_HOST_PATH_KEY = "WILD_RUNTIME_ENV_HOST_PATH"
_ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_WRITE_LOCK = threading.RLock()


def runtime_env_path() -> Path:
    """返回与当前工作目录无关的运行时配置路径。"""

    configured = str(os.environ.get(RUNTIME_ENV_PATH_KEY) or "").strip()
    path = Path(configured).expanduser() if configured else SERVER_ROOT / ".env"
    if not path.is_absolute():
        path = SERVER_ROOT / path
    return path.resolve(strict=False)


def runtime_env_is_persistent() -> bool:
    """部署层显式声明该路径已映射到持久化存储。"""

    configured = os.environ.get(RUNTIME_ENV_PERSISTENT_KEY)
    if configured is None:
        return not Path("/.dockerenv").exists()
    value = str(configured).strip().lower()
    return value in {"1", "true", "yes", "on"}


def runtime_env_host_path() -> str | None:
    """返回部署层声明的宿主机路径，仅用于向管理员解释保存位置。"""

    value = str(os.environ.get(RUNTIME_ENV_HOST_PATH_KEY) or "").strip()
    return value or None


def _encode_env_value(value: str) -> str:
    if "\x00" in value or "\n" in value or "\r" in value:
        raise ValueError("配置值不能包含换行或 NUL 字符")
    if not value:
        return ""
    if re.fullmatch(r"[A-Za-z0-9_./:@+\-=]+", value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _render_updated_env(existing: str, updates: Mapping[str, str]) -> str:
    normalized = {str(key): str(value) for key, value in updates.items()}
    for key in normalized:
        if not _ENV_KEY_RE.fullmatch(key):
            raise ValueError(f"非法环境变量名称: {key}")

    remaining = dict(normalized)
    rendered: list[str] = []
    for line in existing.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            rendered.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in normalized:
            if key in remaining:
                rendered.append(f"{key}={_encode_env_value(remaining.pop(key))}")
            # 删除同一键的后续重复定义，避免 dotenv 的最后一项覆盖新值。
            continue
        rendered.append(line)
    for key, value in remaining.items():
        rendered.append(f"{key}={_encode_env_value(value)}")
    return "\n".join(rendered).rstrip("\n") + "\n"


def _write_in_place(path: Path, content: str) -> None:
    """单文件 bind mount 不允许 replace 时，退回同 inode 覆盖并 fsync。"""

    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def update_runtime_env(updates: Mapping[str, str], path: Path | None = None) -> Path:
    """一次性更新多个键；普通文件原子替换，Docker 文件挂载安全覆盖。"""

    if not updates:
        raise ValueError("没有可保存的配置")
    target = (path or runtime_env_path()).resolve(strict=False)
    with _WRITE_LOCK:
        target.parent.mkdir(parents=True, exist_ok=True)
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
        content = _render_updated_env(existing, updates)
        temporary_path: Path | None = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{target.name}.",
                suffix=".tmp",
                dir=target.parent,
            )
            temporary_path = Path(temporary_name)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.replace(temporary_path, target)
                temporary_path = None
            except OSError as exc:
                # Linux 将单个宿主文件 bind mount 到容器时，替换挂载点会返回
                # EBUSY/EXDEV。此时必须写回同一个 inode，宿主文件才能同步更新。
                if exc.errno not in {errno.EBUSY, errno.EXDEV, errno.EACCES, errno.EPERM}:
                    raise
                _write_in_place(target, content)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        try:
            target.chmod(0o600)
        except OSError:
            pass
    return target
