"""生成请求的可信上下文与安全预检。"""
from agent.llm.config import config
from agent.utils.access import AccessContext
from agent.utils.access import check_content_safety
from agent.utils.access import redact_pii
from agent.utils.observability.trace import record_final_answer
from agent.utils.observability.trace import record_rag_safety
from integration.generation.events import _send_event
from integration.generation.events import EventSink


def _payload_access_context(payload: dict) -> AccessContext:
    raw = payload.get("_server_access_context")
    if not isinstance(raw, dict):
        return AccessContext()
    try:
        return AccessContext(
            user_id=str(raw.get("user_id") or "anonymous"),
            tenant_id=raw.get("tenant_id") or None,
            department=raw.get("department") or None,
            clearance_level=max(0, int(raw.get("clearance_level") or 0)),
            scopes=tuple(raw.get("scopes") or ("public",)),
            authenticated=raw.get("authenticated") is True,
        )
    except (TypeError, ValueError):
        return AccessContext()


def _prepare_server_request(data: dict, access: AccessContext) -> dict:
    """覆盖所有前端自报身份字段，并在进入持久化任务前完成 PII 脱敏。"""

    prepared = dict(data)
    # 覆盖访问身份
    prepared["_server_access_context"] = access.public_dict()
    message = str(prepared.get("message") or "")
    if config.rag.security.pii_redaction_enabled:
        message, pii_categories = redact_pii(message)
    else:
        pii_categories = []
    prepared["message"] = message
    recent_messages = []
    raw_recent = prepared.get("recent_messages")
    if isinstance(raw_recent, list):
        for item in raw_recent[-4:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").lower()
            if role not in {"user", "assistant"}:
                continue
            content = str(item.get("content") or "").strip()[:500]
            if config.rag.security.pii_redaction_enabled:
                content, _ = redact_pii(content)
            if content:
                recent_messages.append({"role": role, "content": content})
    prepared["recent_messages"] = recent_messages
    prepared["workflow_state"] = (
        "scene_ready" if isinstance(prepared.get("blueprint"), dict) else "empty_scene"
    )
    safety = (
        check_content_safety(message)
        if config.rag.security.content_safety_enabled
        else {"allowed": True, "category": None, "matched_rule": None, "message": ""}
    )
    safety["pii_categories"] = pii_categories
    prepared["_server_safety"] = safety
    return prepared


async def _emit_safety_refusal_if_needed(sink, payload: dict) -> bool:
    safety = payload.get("_server_safety")
    if not isinstance(safety, dict):
        message = str(payload.get("message") or "")
        safety = check_content_safety(message)
        safety["pii_categories"] = []
    record_rag_safety(safety)
    if safety.get("allowed") is not False:
        return False
    refusal = str(safety.get("message") or "该请求无法继续处理。")
    record_final_answer(refusal)
    await _send_event(sink, {
        "type": "agent_reply",
        "request_id": payload.get("request_id"),
        "session_id": payload.get("session_id"),
        "content": refusal,
        "safety_category": safety.get("category"),
        "cited_chunk_ids": [],
    })
    return True
