"""
Sessions REST API

GET    /api/sessions                       — 列出所有会话元数据
POST   /api/sessions                       — 创建新会话
GET    /api/sessions/{session_id}          — 获取单个会话详情
PUT    /api/sessions/{session_id}          — 更新会话元数据
DELETE /api/sessions/{session_id}          — 删除会话及其蓝图文件

POST   /api/sessions/{session_id}/messages — 追加消息
GET    /api/sessions/{session_id}/messages — 获取消息历史

存储结构：
  storage/sessions/
    session_1234567890.json   — 会话元数据
    session_9876543210.json
"""
import json
import uuid
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger

from app.utils.blueprint_parser import SCENES_DIR

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

SESSIONS_DIR = SCENES_DIR.parent / "sessions"


def _sessions_dir() -> Path:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return SESSIONS_DIR


def _session_path(session_id: str) -> Path:
    """会话元数据文件路径"""
    # 安全校验：session_id 只允许 session_ 前缀 + 数字/字母/连字符
    if not session_id or "/" in session_id or "\\" in session_id or ".." in session_id:
        raise HTTPException(status_code=400, detail="无效的 session_id")
    return _sessions_dir() / f"{session_id}.json"


def _read_session_meta(session_id: str) -> Optional[dict]:
    """读取会话元数据文件，不存在返回 None"""
    path = _session_path(session_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"[sessions] 读取 {session_id} 失败: {e}")
        return None


def _write_session_meta(session_id: str, data: dict):
    """写入会话元数据文件"""
    path = _session_path(session_id)
    data["session_id"] = session_id
    data["updated_at"] = int(time.time() * 1000)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_blueprint_for_session(session_id: str) -> Optional[dict]:
    """在 scenes 目录中查找该会话对应的蓝图文件信息"""
    SCENES_DIR.mkdir(parents=True, exist_ok=True)
    for wild_file in SCENES_DIR.rglob("*.wild"):
        basename = wild_file.stem  # 如 "session_1234567890_建筑名"
        if basename.startswith(session_id):
            rel = wild_file.relative_to(SCENES_DIR).as_posix()
            try:
                data = json.loads(wild_file.read_text(encoding="utf-8"))
                name = data.get("meta", {}).get("name", basename)
                geometry = data.get("geometry", {})
                elements_count = len(geometry.get("elements", []))
                components_count = len(geometry.get("components", []))
                return {
                    "filename": rel,
                    "name": name,
                    "elements_count": elements_count,
                    "components_count": components_count,
                    "updated_at": int(wild_file.stat().st_mtime * 1000),
                }
            except (json.JSONDecodeError, KeyError, ValueError):
                pass
    return None


def _build_session_info(session_id: str, meta: dict) -> dict:
    """构建前端需要的 SessionInfo 结构"""
    bp = _find_blueprint_for_session(session_id)
    return {
        "session_id": session_id,
        "filename": bp.get("filename") if bp else meta.get("filename"),
        "name": bp.get("name") if bp else meta.get("name", "新建筑"),
        "building_type": meta.get("building_type"),
        "created_at": meta.get("created_at", meta.get("updated_at", 0)),
        "updated_at": meta.get("updated_at", 0),
        "elements_count": bp.get("elements_count", 0) if bp else meta.get("elements_count", 0),
        "components_count": bp.get("components_count", 0) if bp else meta.get("components_count", 0),
        "message_count": len(meta.get("messages", [])),
        "status": "saved" if bp else ("draft" if meta.get("messages") else "draft"),
    }


# ═══════════════════════════════════════════════════════════════════
# 会话 CRUD
# ═══════════════════════════════════════════════════════════════════

@router.get("")
async def list_sessions():
    """列出所有会话（合并 session meta 文件 + scenes 文件扫描）"""
    _sessions_dir()

    sessions: dict[str, dict] = {}

    # 1. 扫描 session meta 文件
    for meta_file in sorted(
        SESSIONS_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        session_id = meta_file.stem
        meta = _read_session_meta(session_id)
        if meta:
            sessions[session_id] = _build_session_info(session_id, meta)

    # 2. 扫描 scenes 文件，补充没有 meta 文件的旧格式会话
    SCENES_DIR.mkdir(parents=True, exist_ok=True)
    for wild_file in sorted(
        SCENES_DIR.rglob("*.wild"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        basename = wild_file.stem
        import re
        match = re.match(r"^(session_\d+)", basename)
        if not match:
            continue
        session_id = match.group(1)
        if session_id in sessions:
            continue  # 已有 meta 文件，跳过

        bp = _find_blueprint_for_session(session_id)
        if bp:
            sessions[session_id] = {
                "session_id": session_id,
                "filename": bp["filename"],
                "name": bp["name"],
                "created_at": bp["updated_at"],
                "updated_at": bp["updated_at"],
                "elements_count": bp["elements_count"],
                "components_count": bp.get("components_count", 0),
                "message_count": 0,
                "status": "saved",
            }

    return JSONResponse(
        content=list(sessions.values()),
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.post("")
async def create_session():
    """创建新会话，返回 session_id"""
    session_id = f"session_{int(time.time() * 1000)}"
    meta = {
        "name": "新建筑",
        "created_at": int(time.time() * 1000),
        "messages": [],
    }
    _write_session_meta(session_id, meta)
    logger.info(f"[sessions] 创建会话: {session_id}")
    return JSONResponse(content={"session_id": session_id})


@router.get("/{session_id}")
async def get_session(session_id: str):
    """获取单个会话详情（含消息历史）"""
    meta = _read_session_meta(session_id)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
    return JSONResponse(content=_build_session_info(session_id, meta))


@router.put("/{session_id}")
async def update_session(session_id: str, request: Request):
    """更新会话元数据（名称、建筑类型等）"""
    meta = _read_session_meta(session_id)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")

    try:
        updates = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="请求体必须是有效的 JSON")

    if "name" in updates:
        meta["name"] = updates["name"]
    if "building_type" in updates:
        meta["building_type"] = updates["building_type"]

    _write_session_meta(session_id, meta)
    return JSONResponse(content={"status": "ok"})


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """删除会话及其关联蓝图文件"""
    # 删除 meta 文件
    meta_path = _session_path(session_id)
    if meta_path.exists():
        meta_path.unlink()

    # 删除关联的蓝图文件
    SCENES_DIR.mkdir(parents=True, exist_ok=True)
    deleted_files = []
    for wild_file in SCENES_DIR.rglob("*.wild"):
        if wild_file.stem.startswith(session_id):
            wild_file.unlink()
            deleted_files.append(wild_file.relative_to(SCENES_DIR).as_posix())
            # 清理空目录
            try:
                wild_file.parent.rmdir()
            except OSError:
                pass

    logger.info(f"[sessions] 删除会话 {session_id}, 蓝图文件: {deleted_files}")
    return JSONResponse(content={
        "status": "deleted",
        "session_id": session_id,
        "blueprint_files": deleted_files,
    })


# ═══════════════════════════════════════════════════════════════════
# 消息管理
# ═══════════════════════════════════════════════════════════════════

MAX_MESSAGES_PER_SESSION = 200


@router.get("/{session_id}/messages")
async def get_messages(session_id: str):
    """获取会话消息历史"""
    meta = _read_session_meta(session_id)
    if meta is None:
        return JSONResponse(content=[])
    return JSONResponse(content=meta.get("messages", []))


@router.post("/{session_id}/messages")
async def add_messages(session_id: str, request: Request):
    """追加消息到会话（批量）"""
    meta = _read_session_meta(session_id)
    if meta is None:
        # 自动创建会话
        meta = {
            "name": "新建筑",
            "created_at": int(time.time() * 1000),
            "messages": [],
        }

    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="请求体必须是有效的 JSON")

    new_messages = body if isinstance(body, list) else [body]
    messages = meta.get("messages", [])
    messages.extend(new_messages)

    # 限制最大消息数
    if len(messages) > MAX_MESSAGES_PER_SESSION:
        messages = messages[-MAX_MESSAGES_PER_SESSION:]

    meta["messages"] = messages
    _write_session_meta(session_id, meta)

    return JSONResponse(content={
        "status": "ok",
        "message_count": len(messages),
    })
