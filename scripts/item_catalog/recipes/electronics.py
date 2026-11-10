"""电子设备：电视、显示器套装、音箱、电脑主机。"""

from __future__ import annotations

from ..dsl import PI, box, cyl
from .registry import item


@item("television", "电视", "appliance", tags=("电视", "屏幕", "tv"), footprint=(1.62, 1.07, 0.38), source_item="television")
def build_television() -> list[dict]:
    """屏幕 + 边框 + 中置底座。`position[1]` 从地面起算，屏幕中心在 0.72。"""

    width, height = 1.62, 0.93
    screen_h = height - 0.06
    parts: list[dict] = []
    parts.append(box("panel", (width, screen_h, 0.045), (0, 0.52 + screen_h / 2, 0), "metal"))
    parts.append(box("screen", (width - 0.05, screen_h - 0.05, 0.008), (0, 0.52 + screen_h / 2, 0.026), "screen"))
    parts.append(box("neck", (0.10, 0.30, 0.06), (0, 0.40, 0), "metal"))
    parts.append(box("foot", (0.52, 0.025, 0.26), (0, 0.26, 0.02), "metal"))
    return parts


@item("wall_tv", "壁挂电视", "appliance", tags=("电视", "壁挂", "tv"), footprint=(1.24, 0.72, 0.06))
def build_wall_tv() -> list[dict]:
    """无底座，直接贴墙。"""

    parts: list[dict] = [box("panel", (1.24, 0.72, 0.04), (0, 0.36, 0), "metal")]
    parts.append(box("screen", (1.19, 0.67, 0.006), (0, 0.36, 0.023), "screen"))
    return parts


@item("computer", "电脑", "appliance", tags=("电脑", "显示器", "computer"), footprint=(0.68, 0.48, 0.19), source_item="computer")
def build_computer() -> list[dict]:
    """显示器 + 底座 + 键盘（笔记本式一体摆放）。"""

    parts: list[dict] = [box("display", (0.56, 0.34, 0.02), (0, 0.31, -0.06), "metal")]
    parts.append(box("screen", (0.53, 0.31, 0.004), (0, 0.31, -0.049), "screen"))
    parts.append(box("stand", (0.18, 0.14, 0.03), (0, 0.10, -0.07), "metal"))
    parts.append(box("foot", (0.26, 0.012, 0.16), (0, 0.006, -0.04), "metal"))
    parts.append(box("keyboard", (0.36, 0.015, 0.13), (0, 0.0075, 0.06), "metal"))
    return parts


@item("laptop", "笔记本电脑", "appliance", tags=("笔记本", "电脑", "laptop"), footprint=(0.34, 0.02, 0.24))
def build_laptop() -> list[dict]:
    """底座 + 后仰屏幕（开合 105°）。"""

    parts: list[dict] = [box("base", (0.34, 0.016, 0.24), (0, 0.008, 0), "metal")]
    parts.append(box("keyboard", (0.30, 0.004, 0.14), (0, 0.018, 0.02), "accent"))
    parts.append(box("lid", (0.34, 0.22, 0.008), (0, 0.11, -0.16), "metal", rot=(-0.26, 0, 0)))
    return parts


@item("stereo_speaker", "落地音箱", "appliance", tags=("音箱", "音响", "speaker"), footprint=(0.23, 1.00, 0.34), source_item="stereo-speaker")
def build_speaker() -> list[dict]:
    """箱体 + 两个纸盆 + 脚钉。"""

    parts: list[dict] = [box("cabinet", (0.23, 0.94, 0.34), (0, 0.50, 0), "wood")]
    parts.append(cyl("woofer", 0.075, 0.02, (0, 0.32, 0.171), "metal", segments=24, rot=(PI / 2, 0, 0)))
    parts.append(cyl("tweeter", 0.032, 0.016, (0, 0.63, 0.172), "metal", segments=20, rot=(PI / 2, 0, 0)))
    for index, (sx, sz) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
        parts.append(cyl(f"spike_{index}", 0.012, 0.03, (sx * 0.08, 0.015, sz * 0.13), "metal", segments=8))
    return parts


@item("speaker_bookshelf", "书架音箱", "appliance", tags=("音箱", "桌面", "speaker"), footprint=(0.18, 0.26, 0.20))
def build_speaker_bookshelf() -> list[dict]:
    parts: list[dict] = [box("cabinet", (0.18, 0.26, 0.20), (0, 0.13, 0), "wood")]
    parts.append(cyl("woofer", 0.052, 0.016, (0, 0.10, 0.101), "metal", segments=20, rot=(PI / 2, 0, 0)))
    parts.append(cyl("tweeter", 0.022, 0.012, (0, 0.20, 0.101), "metal", segments=16, rot=(PI / 2, 0, 0)))
    return parts
