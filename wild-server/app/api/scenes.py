"""
Scenes REST API

GET  /api/scenes/{filename}  — 获取已保存的蓝图文件
"""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.utils.blueprint_parser import SCENES_DIR

router = APIRouter(prefix="/api/scenes", tags=["scenes"])


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
