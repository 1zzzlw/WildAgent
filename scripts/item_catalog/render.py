"""把引擎导出的三角形渲染成 PNG，用于人工核对形似度。

为什么不用浏览器截图：本机 Chrome 起不了 headless CDP（已实测），
而物品核对需要的是**形体轮廓**（比例、分割、悬空），不是材质与光照。
所以这里用 z-buffer 正交投影 + 单方向光，纯 Python 实现，零依赖。

用法：
    python scripts/item_catalog/render.py                  # 全部物品，3 视角 contact sheet
    python scripts/item_catalog/render.py sofa_three       # 指定物品
产物：系统临时目录 wild-item-catalog/preview_<n>.png
"""

from __future__ import annotations

import math
import struct
import sys
import zlib
from pathlib import Path

MESH_DUMP = Path(__file__).resolve().parent / "_meshes.json"
CELL = 240
BACKGROUND = (26, 26, 28)
LIGHT = (0.42, 0.86, 0.30)

# 三个视角：(名称, 相机方向(从物品指向相机), 是否俯视压扁)
VIEWS = (
    ("front34", (0.62, 0.46, 1.0), 1.0),
    ("side", (1.0, 0.34, 0.10), 1.0),
    ("top", (0.10, 1.0, 0.42), 1.0),
)


def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _norm(v):
    length = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return [v[0] / length, v[1] / length, v[2] / length]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def render_view(item: dict, direction, cell: int = CELL) -> list[list[tuple[int, int, int]]]:
    """返回 cell×cell 的 RGB 像素网格。"""

    meshes = item["meshes"]
    low = item["min"]
    high = item.get("max") or [
        low[0] + item["size"][0],
        low[1] + item["size"][1],
        low[2] + item["size"][2],
    ]
    center = [(low[i] + high[i]) / 2 for i in range(3)]
    span = max(item["size"]) or 1.0

    eye = _norm(direction)
    forward = _norm([-eye[0], -eye[1], -eye[2]])
    right = _norm(_cross([0.0, 1.0, 0.0], forward))
    if abs(_dot(right, right)) < 1e-6:
        right = [1.0, 0.0, 0.0]
    up = _norm(_cross(forward, right))

    scale = (cell * 0.68) / span
    pixels = [[BACKGROUND for _ in range(cell)] for _ in range(cell)]
    depth = [[math.inf] * cell for _ in range(cell)]

    for mesh in meshes:
        positions = mesh["positions"]
        indices = mesh["indices"]
        color = mesh.get("color") or [0.72, 0.72, 0.72]
        for index in range(0, len(indices) - 2, 3):
            corners = []
            for offset in range(3):
                base = indices[index + offset] * 3
                point = [positions[base] - center[0], positions[base + 1] - center[1], positions[base + 2] - center[2]]
                corners.append(
                    (
                        _dot(point, right) * scale + cell / 2,
                        -_dot(point, up) * scale + cell / 2,
                        _dot(point, forward),
                    )
                )
            edge1 = _sub([positions[indices[index + 1] * 3] - positions[indices[index] * 3],
                          positions[indices[index + 1] * 3 + 1] - positions[indices[index] * 3 + 1],
                          positions[indices[index + 1] * 3 + 2] - positions[indices[index] * 3 + 2]], [0, 0, 0])
            edge2 = _sub([positions[indices[index + 2] * 3] - positions[indices[index] * 3],
                          positions[indices[index + 2] * 3 + 1] - positions[indices[index] * 3 + 1],
                          positions[indices[index + 2] * 3 + 2] - positions[indices[index] * 3 + 2]], [0, 0, 0])
            normal = _norm(_cross(edge1, edge2))
            shade = 0.22 + 0.78 * max(0.0, _dot(normal, _norm(LIGHT)))
            # 背面（法线朝屏幕外）压暗，让凹槽与朝向可辨
            if _dot(normal, forward) > 0:
                shade *= 0.82
            rgb = (
                max(0, min(255, int(color[0] ** (1 / 2.2) * 255 * shade))),
                max(0, min(255, int(color[1] ** (1 / 2.2) * 255 * shade))),
                max(0, min(255, int(color[2] ** (1 / 2.2) * 255 * shade))),
            )
            _rasterize(pixels, depth, corners, rgb, cell)
    return pixels


def _rasterize(pixels, depth, corners, rgb, cell):
    (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = corners
    min_x = max(0, int(math.floor(min(x0, x1, x2))))
    max_x = min(cell - 1, int(math.ceil(max(x0, x1, x2))))
    min_y = max(0, int(math.floor(min(y0, y1, y2))))
    max_y = min(cell - 1, int(math.ceil(max(y0, y1, y2))))
    if min_x > max_x or min_y > max_y:
        return
    area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
    if abs(area) < 1e-9:
        return
    inv = 1.0 / area
    for pixel_y in range(min_y, max_y + 1):
        py = pixel_y + 0.5
        for pixel_x in range(min_x, max_x + 1):
            px = pixel_x + 0.5
            w0 = ((x1 - px) * (y2 - py) - (x2 - px) * (y1 - py)) * inv
            w1 = ((x2 - px) * (y0 - py) - (x0 - px) * (y2 - py)) * inv
            w2 = 1.0 - w0 - w1
            if w0 < 0 or w1 < 0 or w2 < 0:
                continue
            z = w0 * z0 + w1 * z1 + w2 * z2
            if z < depth[pixel_y][pixel_x]:
                depth[pixel_y][pixel_x] = z
                pixels[pixel_y][pixel_x] = rgb


def _png(path: Path, width: int, height: int, rows: list[list[tuple[int, int, int]]]) -> None:
    raw = bytearray()
    for row in rows:
        raw.append(0)
        for pixel in row:
            raw.extend(pixel)
    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    data = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(data)


def main() -> None:
    import json

    dump_path = Path(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].endswith(".json") else MESH_DUMP
    wanted = {value for value in sys.argv[1:] if not value.endswith(".json")}
    if not dump_path.exists():
        raise SystemExit(f"找不到 {dump_path}，先跑 node scripts/item-catalog-verify.mjs")
    dump = json.loads(dump_path.read_text(encoding="utf-8"))
    items = [key for key in sorted(dump) if not wanted or key in wanted]
    if not items:
        raise SystemExit("没有匹配的物品")

    rows: list[list[tuple[int, int, int]]] = []
    per_sheet = 6
    sheet = 0
    # 系统临时目录在本机沙箱里只读（实测写 PNG 会 PermissionError），
    # 预览图落到项目内的 .workbuddy（非产出物目录，不参与交付）。
    out_dir = Path(__file__).resolve().parents[2] / ".workbuddy" / "item_catalog"
    out_dir.mkdir(parents=True, exist_ok=True)
    for start in range(0, len(items), per_sheet):
        batch = items[start:start + per_sheet]
        canvas: list[list[tuple[int, int, int]]] = []
        for item_id in batch:
            cells = [render_view(dump[item_id], direction) for _, direction, _ in VIEWS]
            for line in range(CELL):
                row = []
                for cell in cells:
                    row.extend(cell[line])
                canvas.append(row)
            canvas.extend([[BACKGROUND] * (CELL * len(VIEWS)) for _ in range(6)])
        target = out_dir / f"preview_{sheet}.png"
        _png(target, CELL * len(VIEWS), len(canvas), canvas)
        print(f"{target}  ({', '.join(batch)})")
        sheet += 1


if __name__ == "__main__":
    main()
