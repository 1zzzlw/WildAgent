"""
Scenes REST API

GET    /api/scenes              — 列出所有已保存的蓝图文件
GET    /api/scenes/{filename}   — 获取已保存的蓝图文件
PUT    /api/scenes/{filename}   — 更新/保存蓝图文件
DELETE /api/scenes/{filename}   — 删除蓝图文件

当前实现以 ``storage/scenes`` 文件夹代替数据库：一个 ``.wild`` 文件对应一个场景，
文件修改时间充当列表接口的更新时间。接口只做轻量结构检查，完整校验发生在 Agent
生成流水线中。
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

    # 最近修改的场景排在最前；glob 限制列表只展示 .wild 文件。
    for file_path in sorted(SCENES_DIR.glob("*.wild"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            # 列表只提取前端卡片所需摘要，不返回完整几何数据。
            name = data.get("meta", {}).get("name", file_path.stem)
            geometry = data.get("geometry", {})
            elements_count = (
                len(geometry.get("elements", []))
                + len(geometry.get("components", []))
            )
            scenes.append({
                "filename": file_path.name,
                "name": name,
                "elements_count": elements_count,
                # 前端使用毫秒时间戳，文件系统提供的是秒。
                "updated_at": int(file_path.stat().st_mtime * 1000),
            })
        except (json.JSONDecodeError, KeyError):
            # 跳过损坏或非 Blueprint 文件
            continue

    # 显式 JSONResponse 保证顶层数组按原样返回。
    return JSONResponse(
        content=scenes,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


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

    # 让响应层流式发送文件，避免先把大型场景整体读入 Python 内存。
    return FileResponse(
        path=str(file_path),
        media_type="application/json",
        filename=filename,
        headers={"Cache-Control": "no-store, max-age=0"},
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
        # FastAPI 在这里异步读取并解析整个 JSON 请求体。
        blueprint = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="请求体必须是有效的 JSON")

    # 这里只保证文件仍像 Blueprint；字段级和空间级校验不在此接口重复执行。
    if not isinstance(blueprint, dict) or "meta" not in blueprint or "geometry" not in blueprint:
        raise HTTPException(status_code=400, detail="JSON 必须是包含 meta 和 geometry 的 Blueprint 对象")

    # 自定义保存函数采用覆盖语义，因此 PUT 同时支持创建和更新。
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

    # 当前没有回收站或数据库软删除，unlink 后只能依赖外部备份恢复。
    file_path.unlink()
    return JSONResponse(content={"status": "deleted", "filename": filename})
