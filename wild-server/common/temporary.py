"""为 Windows 原生库提供可写的进程临时目录，在打开数据库前调用。"""

import os
from pathlib import Path
import sys
import tempfile
import threading
from uuid import uuid4

from loguru import logger

from common.paths import STORAGE_ROOT


_lock = threading.Lock()


def _can_write(directory: Path) -> bool:
    # NamedTemporaryFile 在部分 Windows 权限异常下会反复重试；这里只探测一次。
    probe = directory / f".wild-temp-probe-{uuid4().hex}"
    created = False
    try:
        try:
            with probe.open("xb") as handle:
                created = True
                handle.write(b"WildAgent temporary directory probe")
        finally:
            if created:
                probe.unlink()
    except OSError:
        return False
    return True


def ensure_writable_temp_directory() -> Path | None:
    """保留正常的临时目录；Windows 目录不可写时回退到后端 storage/tmp。"""
    if sys.platform != "win32":
        return None
    with _lock:
        configured = os.environ.get("TMP") or os.environ.get("TEMP")
        current = Path(configured) if configured else Path(tempfile.gettempdir())
        if _can_write(current):
            return current
        fallback = (STORAGE_ROOT / "tmp").resolve()
        fallback.mkdir(parents=True, exist_ok=True)
        if not _can_write(fallback):
            raise RuntimeError(f"系统临时目录 {current} 和备用目录 {fallback} 均不可写")
        # SQLite/Chroma 的原生代码读取环境变量，Python tempfile 还持有独立缓存。
        os.environ["TEMP"] = str(fallback)
        os.environ["TMP"] = str(fallback)
        tempfile.tempdir = str(fallback)
        logger.warning("系统临时目录不可写：{}；已切换到 {}", current, fallback)
        return fallback
