"""RAG 的服务端身份、权限过滤、PII 脱敏与基础内容安全。"""

from __future__ import annotations

import hmac
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Any, Iterator, Mapping


_current_access_context: ContextVar["AccessContext | None"] = ContextVar(
    "current_rag_access_context",
    default=None,
)


@dataclass(frozen=True)
class AccessContext:
    """只能由服务端连接边界创建的 RAG 访问上下文。"""

    user_id: str = "anonymous"
    tenant_id: str | None = None
    department: str | None = None
    clearance_level: int = 0
    scopes: tuple[str, ...] = ("public",)
    authenticated: bool = False

    def public_dict(self) -> dict[str, Any]:
        """用于 Trace 的非密钥字段；不保存认证共享密钥。"""

        return asdict(self)


def access_context_from_headers(
    headers: Mapping[str, str],
    trusted_header_secret: str,
) -> AccessContext:
    """验证反向代理共享密钥后读取身份头；失败时只能访问 public。"""

    supplied_secret = str(headers.get("x-wild-auth-secret") or "")
    trusted = bool(trusted_header_secret) and hmac.compare_digest(
        supplied_secret,
        trusted_header_secret,
    )
    if not trusted:
        return AccessContext()

    raw_scopes = str(headers.get("x-wild-rag-scopes") or "public")
    scopes = tuple(dict.fromkeys(
        item.strip().lower()
        for item in raw_scopes.split(",")
        if item.strip()
    )) or ("public",)
    if "public" not in scopes:
        scopes = ("public", *scopes)
    try:
        clearance_level = max(0, int(headers.get("x-wild-clearance-level") or 0))
    except (TypeError, ValueError):
        clearance_level = 0
    return AccessContext(
        user_id=str(headers.get("x-wild-user-id") or "anonymous")[:128],
        tenant_id=str(headers.get("x-wild-tenant-id") or "")[:128] or None,
        department=str(headers.get("x-wild-department") or "")[:128] or None,
        clearance_level=clearance_level,
        scopes=scopes,
        authenticated=True,
    )


@contextmanager
def access_context_scope(context: AccessContext) -> Iterator[AccessContext]:
    token = _current_access_context.set(context)
    try:
        yield context
    finally:
        _current_access_context.reset(token)


def get_access_context() -> AccessContext:
    return _current_access_context.get() or AccessContext()


_RESERVED_FILTER_KEYS = {
    "access_scope",
    "tenant_id",
    "department",
    "clearance_level",
}


def split_business_and_access_filters(
    metadata_filter: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """移除调用方伪造的权限字段，并生成服务端强制访问条件。"""

    original = metadata_filter or {}
    business_filter = {
        key: value for key, value in original.items() if key not in _RESERVED_FILTER_KEYS
    }
    ignored = sorted(key for key in original if key in _RESERVED_FILTER_KEYS)
    access = get_access_context()

    allowed_branches: list[dict[str, Any]] = [{"access_scope": "public"}]
    if access.authenticated and access.tenant_id and "tenant" in access.scopes:
        allowed_branches.append({
            "$and": [
                {"access_scope": "tenant"},
                {"tenant_id": access.tenant_id},
                {"clearance_level": {"$lte": access.clearance_level}},
            ]
        })
    if (
        access.authenticated
        and access.tenant_id
        and access.department
        and "department" in access.scopes
    ):
        allowed_branches.append({
            "$and": [
                {"access_scope": "department"},
                {"tenant_id": access.tenant_id},
                {"department": access.department},
                {"clearance_level": {"$lte": access.clearance_level}},
            ]
        })
    # Chroma 要求 $or 至少有两个分支。匿名请求只有 public 一个分支时，
    # 直接使用普通等值条件；登录用户存在多个可见范围时再使用 $or。
    access_filter = (
        allowed_branches[0]
        if len(allowed_branches) == 1
        else {"$or": allowed_branches}
    )
    return business_filter, [access_filter], ignored


_PII_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[手机号]"),
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "[身份证号]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[邮箱]"),
    (re.compile(r"(?<!\d)(?:\d[ -]?){7,12}(?!\d)"), "[电话号码]"),
)


def redact_pii(text: str) -> tuple[str, list[str]]:
    """对常见中文联系方式和证件号做确定性替换。"""

    redacted = str(text or "")
    categories: list[str] = []
    for pattern, replacement in _PII_PATTERNS:
        redacted, count = pattern.subn(replacement, redacted)
        if count:
            categories.append(replacement.strip("[]"))
    return redacted, categories


_SAFETY_RULES: dict[str, tuple[str, ...]] = {
    "sexual_minors": ("未成年人色情", "儿童色情", "幼女成人视频"),
    "violent_instruction": ("制作炸弹教程", "自制爆炸物步骤", "如何制造枪支"),
    "credential_theft": ("窃取密码教程", "盗取银行卡密码", "绕过登录并窃取"),
}


def check_content_safety(text: str) -> dict[str, Any]:
    """高置信规则兜底；不把一般政治或建筑讨论误判为安全违规。"""

    normalized = re.sub(r"\s+", "", str(text or "")).casefold()
    for category, terms in _SAFETY_RULES.items():
        matched = next((term for term in terms if term.casefold() in normalized), None)
        if matched:
            return {
                "allowed": False,
                "category": category,
                "matched_rule": matched,
                "message": "该请求触发内容安全规则，无法继续处理。",
            }
    return {"allowed": True, "category": None, "matched_rule": None, "message": ""}
