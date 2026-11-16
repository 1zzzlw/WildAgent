"""操作审计与额度扣减；与业务写入共用事务，重放不会重复扣减。"""

from __future__ import annotations

from hashlib import sha256
import json
from uuid import uuid4

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection

from app.domain.usage import DEFAULT_DAILY_LIMITS, USAGE_LABELS, next_reset_at
from app.infrastructure.persistence.database import database
from app.infrastructure.persistence.repositories.conversations import now_ms
from app.infrastructure.persistence.repositories.errors import AccountUnavailable
from app.infrastructure.persistence.repositories.errors import OperationConflict
from app.infrastructure.persistence.repositories.errors import QuotaExceeded
from app.infrastructure.persistence.schema import audit_logs, users


def public_usage(account: dict) -> dict:
    unlimited = account.get("identity") == 2
    now = now_ms()
    reset_at = account.get("usage_reset_at", 0)
    expired = reset_at <= now
    if expired:
        reset_at = next_reset_at(now)
    result = {}
    for kind, default_limit in DEFAULT_DAILY_LIMITS.items():
        limit = account.get(kind + "_daily_limit", default_limit)
        remaining = limit if expired else account.get(kind + "_remaining", 0)
        result[kind] = {
            "remaining": None if unlimited else remaining,
            "used": account.get(kind + "_used", 0),
            "daily_limit": None if unlimited else limit,
            "resets_at": reset_at,
        }
    return result


def refresh_daily_quota(connection: Connection, account: dict) -> dict:
    """在业务事务内补齐当天余额；并发请求只有第一个能执行重置。"""
    now = now_ms()
    if account["usage_reset_at"] > now:
        return account
    connection.execute(
        update(users)
        .where(users.c.id == account["id"], users.c.usage_reset_at <= now)
        .values(
            operations_remaining=users.c.operations_daily_limit,
            ai_remaining=users.c.ai_daily_limit,
            usage_reset_at=next_reset_at(now),
        )
    )
    columns = [
        users.c.operations_remaining,
        users.c.ai_remaining,
        users.c.operations_daily_limit,
        users.c.ai_daily_limit,
        users.c.usage_reset_at,
    ]
    current = (
        connection.execute(select(*columns).where(users.c.id == account["id"]))
        .mappings()
        .one()
    )
    return {**account, **current}


def lock_account(connection: Connection, user_id: str) -> dict:
    row = (
        connection.execute(select(users).where(users.c.id == user_id).with_for_update())
        .mappings()
        .first()
    )
    if row is None or row["status"] != "active":
        raise AccountUnavailable("账号已被停用，请重新登录或联系管理员")
    return refresh_daily_quota(connection, dict(row))


def event_id(actor_id: str, key: str) -> str:
    return sha256((actor_id + ":" + key).encode()).hexdigest()


def append_audit(
    connection: Connection,
    actor: dict,
    action: str,
    *,
    resource: str = "",
    details: dict | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    key: str | None = None,
) -> bool:
    identity = event_id(actor["id"], key or uuid4().hex)
    if connection.execute(
        select(audit_logs.c.id).where(audit_logs.c.id == identity)
    ).first():
        return False
    connection.execute(
        insert(audit_logs).values(
            id=identity,
            actor_id=actor["id"],
            actor_name=actor["username"],
            action=action,
            resource=resource[:255],
            session_id=session_id,
            request_id=request_id,
            details=details or {},
            created_at=now_ms(),
        )
    )
    return True


def charge_usage(connection: Connection, actor: dict, kind: str) -> None:
    actor = refresh_daily_quota(connection, actor)
    remaining = users.c[kind + "_remaining"]
    used = users.c[kind + "_used"]
    values = {kind + "_used": used + 1}
    statement = update(users).where(
        users.c.id == actor["id"], users.c.status == "active"
    )
    if actor["identity"] != 2:
        statement = statement.where(remaining > 0)
        values[kind + "_remaining"] = remaining - 1
    if not connection.execute(statement.values(**values)).rowcount:
        raise QuotaExceeded(
            f"今日{USAGE_LABELS[kind]}次数已用完，明日零点（北京时间）恢复，可联系管理员调整"
        )


def fingerprint(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return sha256(raw.encode()).hexdigest()


def record_activity(user_id: str, action: str, **kwargs) -> None:
    with database.engine.begin() as connection:
        # 已完成操作的结果仍需记录，即使管理员刚刚停用了此账号。
        row = (
            connection.execute(
                select(users).where(users.c.id == user_id).with_for_update()
            )
            .mappings()
            .first()
        )
        if row is None:
            return
        actor = dict(row)
        append_audit(connection, actor, action, **kwargs)


def charge_ai_request(user_id: str, request_id: str, session_id: str) -> dict:
    """所有 AI 请求共用每日额度；重试、恢复以及跨天重放都只计一次。"""
    with database.engine.begin() as connection:
        actor = lock_account(connection, user_id)
        key = event_id(user_id, "ai.usage:" + request_id)
        previous = (
            connection.execute(select(audit_logs).where(audit_logs.c.id == key))
            .mappings()
            .first()
        )
        if previous:
            if previous["session_id"] != session_id:
                raise OperationConflict("任务的会话与已记录的额度消费不一致")
            return public_usage(actor)
        charge_usage(connection, actor, "ai")
        append_audit(
            connection,
            actor,
            "ai.usage",
            session_id=session_id,
            request_id=request_id,
            key="ai.usage:" + request_id,
            details={"kind": "ai", "cost": 1},
        )
        fresh = (
            connection.execute(select(users).where(users.c.id == user_id))
            .mappings()
            .one()
        )
        return public_usage(dict(fresh))
