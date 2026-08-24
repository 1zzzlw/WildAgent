"""RAG 观测 REST API：目前只接收与 request_id 关联的用户反馈。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent.rag_trace import append_rag_feedback


router = APIRouter(prefix="/api/rag", tags=["rag-observability"])


class RAGFeedbackRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=160)
    request_id: str = Field(min_length=1, max_length=160)
    rating: str
    comment: str = Field(default="", max_length=2000)


@router.post("/feedback")
async def add_rag_feedback(body: RAGFeedbackRequest):
    """rating 只接受 up/down；反馈写入对应 Trace 文件，不另建匿名孤儿记录。"""

    rating = body.rating.strip().lower()
    if rating not in {"up", "down"}:
        raise HTTPException(status_code=400, detail="rating 只能是 up 或 down")
    try:
        path = append_rag_feedback(
            body.session_id,
            body.request_id,
            rating=rating,
            comment=body.comment,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="找不到对应的 RAGTrace")
    return {
        "status": "ok",
        "session_id": body.session_id,
        "request_id": body.request_id,
        "trace_file": str(path),
    }
