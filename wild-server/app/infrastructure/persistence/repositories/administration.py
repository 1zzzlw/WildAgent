"""管理查询与账号变更；结果不包含密码散列。"""

from sqlalchemy import case, func, or_, select, update

from app.infrastructure.persistence.database import database
from app.infrastructure.persistence.repositories.activity import (
    append_audit,
    lock_account,
    refresh_daily_quota,
)
from app.infrastructure.persistence.repositories.conversations import now_ms
from app.infrastructure.persistence.repositories.errors import (
    AccessDenied,
    OperationConflict,
)
from app.infrastructure.persistence.schema import audit_logs, blueprints, users

ACCOUNT_COLUMNS = [column for column in users.c if column.name != "password_hash"]
BLUEPRINT_COLUMNS = [
    column for column in blueprints.c if column.name != "blueprint_json"
]
AUDIT_LIST_COLUMNS = [column for column in audit_logs.c if column.name != "details"]


def _page(connection, statement, count_statement, page: int, page_size: int) -> dict:
    items = connection.execute(
        statement.offset((page - 1) * page_size).limit(page_size)
    ).mappings()
    return {
        "items": [dict(item) for item in items],
        "total": connection.scalar(count_statement),
        "page": page,
        "page_size": page_size,
    }


def list_accounts(query: str, status: str | None, page: int, page_size: int) -> dict:
    filters = [users.c.status != "deleted"]
    if query:
        filters.append(
            or_(
                users.c.username.contains(query, autoescape=True),
                users.c.email.contains(query, autoescape=True),
            )
        )
    if status:
        filters.append(users.c.status == status)
    with database.engine.connect() as connection:
        return _page(
            connection,
            select(*ACCOUNT_COLUMNS)
            .where(*filters)
            .order_by(users.c.created_at.desc(), users.c.id),
            select(func.count()).select_from(users).where(*filters),
            page,
            page_size,
        )


def list_activity(
    user_id: str | None,
    action: str | None,
    query: str,
    since: int | None,
    until: int | None,
    page: int,
    page_size: int,
    *,
    include_details: bool = True,
) -> dict:
    filters = []
    if user_id:
        filters.append(audit_logs.c.actor_id == user_id)
    if action:
        filters.append(audit_logs.c.action == action)
    if query:
        filters.append(
            or_(
                audit_logs.c.actor_name.contains(query, autoescape=True),
                audit_logs.c.resource.contains(query, autoescape=True),
                audit_logs.c.action.contains(query, autoescape=True),
            )
        )
    if since is not None:
        filters.append(audit_logs.c.created_at >= since)
    if until is not None:
        filters.append(audit_logs.c.created_at <= until)
    with database.engine.connect() as connection:
        # 先只排序 ID，避免大体积 AI 回复/变更 JSON 占满 MySQL filesort 缓冲区。
        result = _page(
            connection,
            select(audit_logs.c.id)
            .where(*filters)
            .order_by(audit_logs.c.created_at.desc(), audit_logs.c.id),
            select(func.count()).select_from(audit_logs).where(*filters),
            page,
            page_size,
        )
        ids = [item["id"] for item in result["items"]]
        if ids:
            if include_details:
                statement = select(audit_logs)
            else:
                preview_fields = []
                for field in ("label", "message", "content", "summary"):
                    value = audit_logs.c.details[field].as_string()
                    preview_fields.append(func.nullif(value, ""))
                preview = func.substr(func.coalesce(*preview_fields, ""), 1, 180)
                statement = select(*AUDIT_LIST_COLUMNS, preview.label("preview"))
            rows = connection.execute(
                statement.where(audit_logs.c.id.in_(ids))
            ).mappings()
            by_id = {row["id"]: dict(row) for row in rows}
            result["items"] = [by_id[identity] for identity in ids if identity in by_id]
        return result


def get_activity(log_id: str) -> dict | None:
    with database.engine.connect() as connection:
        row = connection.execute(
            select(audit_logs).where(audit_logs.c.id == log_id)
        ).mappings().first()
        return dict(row) if row is not None else None


def list_blueprints(query: str, locked: bool | None, page: int, page_size: int) -> dict:
    filters = []
    if query:
        filters.append(
            or_(
                blueprints.c.name.contains(query, autoescape=True),
                blueprints.c.filename.contains(query, autoescape=True),
                users.c.username.contains(query, autoescape=True),
            )
        )
    if locked is not None:
        filters.append(blueprints.c.locked == locked)
    source = blueprints.outerjoin(users, blueprints.c.owner_id == users.c.id)
    with database.engine.connect() as connection:
        # 列表只读取摘要，避免完整蓝图 JSON 占满 MySQL 排序缓冲区。
        return _page(
            connection,
            select(*BLUEPRINT_COLUMNS, users.c.username.label("owner_name"))
            .select_from(source)
            .where(*filters)
            .order_by(blueprints.c.updated_at.desc(), blueprints.c.filename),
            select(func.count()).select_from(source).where(*filters),
            page,
            page_size,
        )


def statistics() -> dict:
    now = now_ms()
    active = users.c.status == "active"
    blocked = users.c.status == "blocked"
    deleted = users.c.status == "deleted"
    administrator = active & (users.c.identity == 2)
    recent_registration = ~deleted & (users.c.created_at >= now - 7 * 86400000)
    with database.engine.connect() as connection:
        counts = connection.execute(
            select(
                func.count(case((active, 1))).label("active_users"),
                func.count(case((blocked, 1))).label("blocked_users"),
                func.count(case((deleted, 1))).label("deleted_users"),
                func.count(case((administrator, 1))).label("administrators"),
                func.count(case((recent_registration, 1))).label("new_users_7d"),
            )
        ).mappings().one()
        blueprint_counts = connection.execute(
            select(
                func.count().label("blueprints"),
                func.count(case((blueprints.c.locked.is_(True), 1))).label("locked_blueprints"),
            ).select_from(blueprints)
        ).mappings().one()
        return {
            **counts,
            **blueprint_counts,
            "users": counts["active_users"] + counts["blocked_users"],
            "active_users_24h": connection.scalar(
                select(func.count(func.distinct(audit_logs.c.actor_id)))
                .select_from(
                    audit_logs.join(users, audit_logs.c.actor_id == users.c.id)
                )
                .where(
                    audit_logs.c.created_at >= now - 86400000,
                    ~deleted,
                )
            ),
            "operations": connection.scalar(
                select(func.count()).select_from(audit_logs)
            ),
        }


def change_account(actor_id: str, user_id: str, values: dict) -> dict:
    with database.engine.begin() as connection:
        # 统一按 ID 加锁管理员集合，串行检查最后一个有效管理员。
        admins = (
            connection.execute(
                select(users.c.id)
                .where(users.c.identity == 2, users.c.status == "active")
                .order_by(users.c.id)
                .with_for_update()
            )
            .scalars()
            .all()
        )
        actor = lock_account(connection, actor_id)
        if actor["identity"] != 2:
            raise AccessDenied("此操作需要管理员权限")
        row = (
            connection.execute(
                select(*ACCOUNT_COLUMNS).where(users.c.id == user_id).with_for_update()
            )
            .mappings()
            .first()
        )
        if not row or row["status"] == "deleted":
            raise LookupError("用户不存在")
        current = refresh_daily_quota(connection, dict(row))
        values = dict(values)
        for kind in ("operations", "ai"):
            limit_key = kind + "_daily_limit"
            remaining_key = kind + "_remaining"
            if limit_key in values and remaining_key not in values:
                used_today = max(0, current[limit_key] - current[remaining_key])
                values[remaining_key] = max(0, values[limit_key] - used_today)
        disabling = (
            values.get("status", current["status"]) != "active"
            or values.get("identity", current["identity"]) != 2
        )
        if actor_id == user_id and disabling:
            raise OperationConflict("不能停用、删除或降级当前登录的管理员")
        if user_id in admins and disabling and len(admins) <= 1:
            raise OperationConflict("至少需要保留一个有效管理员")
        connection.execute(update(users).where(users.c.id == user_id).values(**values))
        append_audit(
            connection,
            actor,
            "user.delete" if values.get("status") == "deleted" else "user.update",
            resource=user_id,
            details={
                "username": current["username"],
                "before": {key: current[key] for key in values},
                "after": values,
            },
        )
        return dict(
            connection.execute(select(*ACCOUNT_COLUMNS).where(users.c.id == user_id))
            .mappings()
            .one()
        )
