"""幕墙确定性生成参数：从知识库配方读取，而非在代码里写死。

知识库 `recipes/glass-curtain-wall-assembly.md` 是幕墙组装的单一事实源。本模块
直接解析该文件中「幕墙确定性生成参数」的 JSON 块，让窗格模数、竖梃缝、窗台高等
参数随知识库修改而生效，无需改代码。文件缺失或解析失败时回退到内置默认值，保证
生成链路永不因配方格式问题而崩溃。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
_RECIPE_PATH = (
    _SERVER_ROOT / "storage" / "knowledge_base" / "recipes"
    / "glass-curtain-wall-assembly.md"
)

_DEFAULTS: dict[str, float] = {
    "pane_module": 1.4,
    "mullion_gap": 0.2,
    "min_window_width": 0.75,
    "sill_height": 0.5,
    "sill_ratio": 0.13,
    "top_clearance": 0.25,
}

# 每个参数的合理取值区间，越界值会被夹回边界，避免配方手误破坏生成。
_RANGES: dict[str, tuple[float, float]] = {
    "pane_module": (0.4, 4.0),
    "mullion_gap": (0.05, 1.0),
    "min_window_width": (0.5, 3.0),
    "sill_height": (0.1, 1.5),
    "sill_ratio": (0.02, 0.4),
    "top_clearance": (0.05, 0.8),
}

_JSON_FENCE = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)


@dataclass(frozen=True)
class CurtainWallParameters:
    """方案 A 幕墙的确定性生成参数。"""

    pane_module: float
    mullion_gap: float
    min_window_width: float
    sill_height: float
    sill_ratio: float
    top_clearance: float


def _parse_parameters(text: str) -> dict[str, float]:
    """从配方正文里找到带 ``pane_module`` 键的 JSON 块并解析出数值。"""
    for match in _JSON_FENCE.finditer(text):
        try:
            data = json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or "pane_module" not in data:
            continue
        parsed: dict[str, float] = {}
        for key in _DEFAULTS:
            value = data.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                parsed[key] = float(value)
        return parsed
    return {}


def _clamp(name: str, value: float) -> float:
    low, high = _RANGES[name]
    return round(min(high, max(low, value)), 4)


def _build_parameters(overrides: dict[str, float]) -> CurtainWallParameters:
    values = dict(_DEFAULTS)
    for key, value in overrides.items():
        if key in values:
            values[key] = value
    clamped = {key: _clamp(key, value) for key, value in values.items()}
    return CurtainWallParameters(**clamped)


# 按 mtime 缓存，配方文件更新后下一次读取自动刷新，无需重启服务。
_cache: dict[str, Any] = {"mtime": None, "parameters": None}


def load_curtain_wall_parameters() -> CurtainWallParameters:
    """读取当前配方的确定性幕墙参数（带 mtime 缓存与回退默认值）。"""
    mtime: float | None = None
    try:
        if _RECIPE_PATH.exists():
            mtime = _RECIPE_PATH.stat().st_mtime
    except OSError:
        mtime = None

    if _cache["mtime"] == mtime and _cache["parameters"] is not None:
        return _cache["parameters"]

    overrides: dict[str, float] = {}
    try:
        if _RECIPE_PATH.exists():
            overrides = _parse_parameters(_RECIPE_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        logger.warning(f"[facade-recipe] 读取幕墙配方失败，使用默认参数: {exc}")

    if overrides:
        logger.debug(f"[facade-recipe] 已从知识库加载幕墙参数: {overrides}")
    parameters = _build_parameters(overrides)
    _cache["mtime"] = mtime
    _cache["parameters"] = parameters
    return parameters
