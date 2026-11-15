"""仅用于显式文件导出；在线蓝图持久化由 MySQL 仓储负责。"""
import datetime
import json
import os as _os
import re
from pathlib import Path

def _safe_name_slug(name: str, max_len: int = 40) -> str:
    """将 meta.name 转换为安全的文件名片段。

    保留中文、字母、数字和下划线，其余字符替换为 _，并截断到 max_len。
    """
    slug = re.sub(r"[^\w\u4e00-\u9fff]", "_", name, flags=re.UNICODE)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:max_len] if slug else "unnamed"

def save_blueprint_file(blueprint: dict, directory: Path) -> str:
    """保存 Blueprint 到磁盘（日期子目录 + 时间戳命名）

    文件路径格式: <directory>/YYYY-MM-DD/HHMMSS_<meta.name>.wild
    内容: 格式化 JSON (indent=2, ensure_ascii=False)

    Args:
        blueprint: Blueprint dict
        directory: 根保存目录，日期子目录自动创建

    Returns:
        保存文件的绝对路径字符串
    """
    now = datetime.datetime.now()
    date_dir = directory / now.strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)

    name_slug = _safe_name_slug(blueprint.get("meta", {}).get("name", ""))
    filename = now.strftime("%H%M%S") + (f"_{name_slug}" if name_slug else "") + ".wild"
    file_path = date_dir / filename
    file_path.write_text(
        json.dumps(blueprint, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return str(file_path.resolve())

def save_blueprint_file_as(blueprint: dict, directory: Path, rel_path: str) -> str:
    """保存 Blueprint 到磁盘（自定义相对路径）

    rel_path 可以是：
      - 旧格式 "session_xxx.wild"（直接放在 directory 下）
      - 新格式 "2026-08-02/session_xxx_名称.wild"（日期子目录）

    相同路径会被覆盖，实现同一会话的持续更新。

    Args:
        blueprint: Blueprint dict
        directory: 根目录（路径边界校验由 API 层负责）
        rel_path: 相对于 directory 的路径

    Returns:
        保存文件的绝对路径字符串
    """
    file_path = directory / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    # 先写同目录临时文件再原子替换，避免进程在写中途退出留下半写坏的 .wild。
    temp_path = file_path.with_name(f"{file_path.name}.tmp-{_os.getpid()}")
    temp_path.write_text(
        json.dumps(blueprint, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _os.replace(temp_path, file_path)
    return str(file_path.resolve())
