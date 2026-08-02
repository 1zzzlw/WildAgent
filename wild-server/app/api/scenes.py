"""
Scenes REST API

GET    /api/scenes                      — 列出所有已保存的蓝图文件（递归扫描日期子目录）
GET    /api/scenes/{date}/{filename}    — 获取蓝图（新格式，日期子目录）
GET    /api/scenes/{filename}           — 获取蓝图（旧格式兼容）
PUT    /api/scenes/{date}/{filename}    — 保存蓝图（新格式）
PUT    /api/scenes/{filename}           — 保存蓝图（旧格式兼容）
DELETE /api/scenes/{date}/{filename}    — 删除蓝图（新格式）
DELETE /api/scenes/{filename}           — 删除蓝图（旧格式兼容）

存储结构：
  storage/scenes/
    2026-08-02/
      session_1234567890_带家居的别墅.wild
      session_9876543210_简约住宅.wild
    2026-08-01/
      session_0000000000_旧建筑.wild

文件名规则：
  {session_id}_{meta.name 安全化}.wild
  session_id 与文件名之间用 _ 分隔，解析时取第一段作为 session_id。
"""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from app.utils.blueprint_parser import SCENES_DIR, save_blueprint_file_as

router = APIRouter(prefix="/api/scenes", tags=["scenes"])

# 日期目录名格式，只允许 YYYY-MM-DD
_DATE_DIR_RE = __import__("re").compile(r"^\d{4}-\d{2}-\d{2}$")


def _resolve_file_path(rel_path: str) -> Path:
    """将相对路径解析为绝对路径，并校验未越出 SCENES_DIR。"""
    file_path = (SCENES_DIR / rel_path).resolve()
    if not str(file_path).startswith(str(SCENES_DIR.resolve())):
        raise HTTPException(status_code=403, detail="禁止访问该路径")
    return file_path


def _scene_summary(file_path: Path) -> dict | None:
    """从 .wild 文件提取列表卡片摘要，解析失败返回 None。"""
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        name = data.get("meta", {}).get("name", file_path.stem)
        geometry = data.get("geometry", {})
        elements_count = (
            len(geometry.get("elements", []))
            + len(geometry.get("components", []))
        )
        # filename 字段返回带日期目录的相对路径，前端用它拼接 GET/PUT/DELETE URL。
        rel = file_path.relative_to(SCENES_DIR).as_posix()
        return {
            "filename": rel,
            "name": name,
            "elements_count": elements_count,
            "updated_at": int(file_path.stat().st_mtime * 1000),
        }
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


@router.get("")
async def list_scenes():
    """列出所有已保存的蓝图文件（递归扫描日期子目录 + 根目录旧文件）"""
    SCENES_DIR.mkdir(parents=True, exist_ok=True)

    # 递归找出所有 .wild 文件，按修改时间倒序排列
    all_files = sorted(
        SCENES_DIR.rglob("*.wild"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    scenes = []
    for file_path in all_files:
        summary = _scene_summary(file_path)
        if summary:
            scenes.append(summary)

    return JSONResponse(
        content=scenes,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


# ── 新格式：/api/scenes/{date}/{filename} ──

@router.get("/{date}/{filename}")
async def get_scene_dated(date: str, filename: str):
    """获取日期子目录中的蓝图文件"""
    if not _DATE_DIR_RE.match(date):
        raise HTTPException(status_code=400, detail="日期目录格式必须为 YYYY-MM-DD")
    file_path = _resolve_file_path(f"{date}/{filename}")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {date}/{filename}")
    return FileResponse(
        path=str(file_path),
        media_type="application/json",
        filename=filename,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.put("/{date}/{filename}")
async def update_scene_dated(date: str, filename: str, request: Request):
    """保存蓝图到日期子目录"""
    if not _DATE_DIR_RE.match(date):
        raise HTTPException(status_code=400, detail="日期目录格式必须为 YYYY-MM-DD")
    if not filename.endswith(".wild"):
        raise HTTPException(status_code=400, detail="文件名必须以 .wild 结尾")

    # 提前做路径边界校验，防止 date/filename 组合穿越
    _resolve_file_path(f"{date}/{filename}")

    try:
        blueprint = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="请求体必须是有效的 JSON")

    if not isinstance(blueprint, dict) or "meta" not in blueprint or "geometry" not in blueprint:
        raise HTTPException(status_code=400, detail="JSON 必须是包含 meta 和 geometry 的 Blueprint 对象")

    saved_path = save_blueprint_file_as(blueprint, SCENES_DIR, f"{date}/{filename}")
    return JSONResponse(content={"status": "ok", "path": saved_path})


@router.delete("/{date}/{filename}")
async def delete_scene_dated(date: str, filename: str):
    """删除日期子目录中的蓝图文件"""
    if not _DATE_DIR_RE.match(date):
        raise HTTPException(status_code=400, detail="日期目录格式必须为 YYYY-MM-DD")
    if not filename.endswith(".wild"):
        raise HTTPException(status_code=400, detail="只能删除 .wild 文件")

    file_path = _resolve_file_path(f"{date}/{filename}")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {date}/{filename}")

    file_path.unlink()
    # 目录变为空时自动清理，保持存储整洁
    try:
        file_path.parent.rmdir()
    except OSError:
        pass  # 目录非空或已不存在，忽略
    return JSONResponse(content={"status": "deleted", "filename": f"{date}/{filename}"})


# ── 旧格式兼容：/api/scenes/{filename} ──

@router.get("/{filename}")
async def get_scene(filename: str):
    """获取根目录中的蓝图文件（旧格式兼容）"""
    file_path = _resolve_file_path(filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {filename}")
    return FileResponse(
        path=str(file_path),
        media_type="application/json",
        filename=filename,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.put("/{filename}")
async def update_scene(filename: str, request: Request):
    """保存蓝图到根目录（旧格式兼容）"""
    _resolve_file_path(filename)
    if not filename.endswith(".wild"):
        raise HTTPException(status_code=400, detail="文件名必须以 .wild 结尾")

    try:
        blueprint = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="请求体必须是有效的 JSON")

    if not isinstance(blueprint, dict) or "meta" not in blueprint or "geometry" not in blueprint:
        raise HTTPException(status_code=400, detail="JSON 必须是包含 meta 和 geometry 的 Blueprint 对象")

    saved_path = save_blueprint_file_as(blueprint, SCENES_DIR, filename)
    return JSONResponse(content={"status": "ok", "path": saved_path})


@router.delete("/{filename}")
async def delete_scene(filename: str):
    """删除根目录蓝图文件（旧格式兼容）"""
    file_path = _resolve_file_path(filename)
    if not filename.endswith(".wild"):
        raise HTTPException(status_code=400, detail="只能删除 .wild 文件")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {filename}")
    file_path.unlink()
    return JSONResponse(content={"status": "deleted", "filename": filename})
