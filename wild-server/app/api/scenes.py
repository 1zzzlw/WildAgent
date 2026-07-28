"""
Scenes REST API

GET    /api/scenes              — 列出所有已保存的蓝图文件
GET    /api/scenes/{filename}   — 获取已保存的蓝图文件
PUT    /api/scenes/{filename}   — 更新/保存蓝图文件
DELETE /api/scenes/{filename}   — 删除蓝图文件
"""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from app.utils.blueprint_parser import SCENES_DIR, save_blueprint_file_as

router = APIRouter(prefix="/api/scenes", tags=["scenes"])


@router.get("")
async def list_scenes():
    """列出所有已保存的蓝图文件

    Returns:
        [{ "filename": "session_xxx.wild", "name": "建筑名称", "elements_count": 5 }, ...]
    """
    scenes = []
    SCENES_DIR.mkdir(parents=True, exist_ok=True)

    for file_path in sorted(SCENES_DIR.glob("*.wild"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            name = data.get("meta", {}).get("name", file_path.stem)
            elements_count = len(data.get("geometry", {}).get("elements", []))
            scenes.append({
                "filename": file_path.name,
                "name": name,
                "elements_count": elements_count,
                "updated_at": int(file_path.stat().st_mtime * 1000),
            })
        except (json.JSONDecodeError, KeyError):
            # 跳过损坏或非 Blueprint 文件
            continue

    return JSONResponse(content=scenes)


@router.get("/{filename}")
async def get_scene(filename: str):
    """获取已保存的蓝图文件内容（JSON）"""
    file_path = SCENES_DIR / filename

    # 安全检查：防止路径穿越
    resolved = file_path.resolve()
    if not str(resolved).startswith(str(SCENES_DIR.resolve())):
        raise HTTPException(status_code=403, detail="禁止访问该路径")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {filename}")

    return FileResponse(
        path=str(file_path),
        media_type="application/json",
        filename=filename,
    )


@router.put("/{filename}")
async def update_scene(filename: str, request: Request):
    """更新/保存蓝图文件

    接收 JSON body（完整 Blueprint），覆盖写入 storage/scenes/{filename}。
    如果文件已存在则覆盖，不存在则新建。
    """
    file_path = SCENES_DIR / filename

    # 安全检查：防止路径穿越
    resolved = file_path.resolve()
    if not str(resolved).startswith(str(SCENES_DIR.resolve())):
        raise HTTPException(status_code=403, detail="禁止访问该路径")

    # 只允许 .wild 扩展名
    if not filename.endswith(".wild"):
        raise HTTPException(status_code=400, detail="文件名必须以 .wild 结尾")

    try:
        blueprint = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="请求体必须是有效的 JSON")

    # 基本结构校验
    if not isinstance(blueprint, dict) or "meta" not in blueprint or "geometry" not in blueprint:
        raise HTTPException(status_code=400, detail="JSON 必须是包含 meta 和 geometry 的 Blueprint 对象")

    saved_path = save_blueprint_file_as(blueprint, SCENES_DIR, filename)
    return JSONResponse(content={"status": "ok", "path": saved_path})


@router.delete("/{filename}")
async def delete_scene(filename: str):
    """删除蓝图文件

    TODO: 接入数据库后，改为软删除（标记 deleted_at）而非物理删除文件。
          同时清理关联的会话记录、消息历史等。
    """
    file_path = SCENES_DIR / filename

    # 安全检查：防止路径穿越
    resolved = file_path.resolve()
    if not str(resolved).startswith(str(SCENES_DIR.resolve())):
        raise HTTPException(status_code=403, detail="禁止访问该路径")

    if not filename.endswith(".wild"):
        raise HTTPException(status_code=400, detail="只能删除 .wild 文件")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {filename}")

    file_path.unlink()
    return JSONResponse(content={"status": "deleted", "filename": filename})
