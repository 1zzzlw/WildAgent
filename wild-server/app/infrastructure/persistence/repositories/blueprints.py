from __future__ import annotations

from pathlib import PurePosixPath
import re

from sqlalchemy import delete, insert, select, update

from app.infrastructure.persistence.database import database
from app.infrastructure.persistence.schema import blueprints
from app.infrastructure.persistence.repositories.conversations import ensure_session
from app.infrastructure.persistence.repositories.conversations import now_ms
from app.infrastructure.persistence.repositories.conversations import visible_to
from app.infrastructure.persistence.repositories.errors import AccessDenied
from app.infrastructure.persistence.repositories.errors import OperationConflict
from app.infrastructure.persistence.repositories.activity import append_audit, charge_usage, event_id, fingerprint, lock_account
from app.infrastructure.persistence.repositories.blueprint_changes import content_fingerprint, describe_changes
from app.infrastructure.persistence.repositories.locks import assert_row_unlocked, assert_session_unlocked
from app.infrastructure.persistence.schema import audit_logs
from app.infrastructure.persistence.repositories.ai_edits import is_verified_ai_edit

SUMMARY_COLUMNS = [blueprints.c[key] for key in (
    "filename", "session_id", "name", "elements_count", "components_count", "locked", "locked_at", "created_at", "updated_at")]


def validate_filename(filename: str) -> str:
    if (len(filename) > 255 or "\\" in filename or ".." in filename or "\x00" in filename
            or not re.fullmatch(r"(?:\d{4}-\d{2}-\d{2}/)?[^/]+\.wild", filename)):
        raise ValueError("无效的蓝图名称，格式应为 文件名.wild 或 YYYY-MM-DD/文件名.wild")
    return filename


def session_for_filename(filename: str) -> str | None:
    match = re.match(r"^(session_[^_]+)(?:_|\.)", PurePosixPath(filename).name)
    return match.group(1) if match else None


class BlueprintRepository:
    def get(self, filename: str) -> dict | None:
        validate_filename(filename)
        with database.engine.connect() as conn:
            row = conn.execute(select(blueprints).where(blueprints.c.filename == filename)).mappings().first()
            return dict(row) if row else None

    def list(self, user_id: str | None) -> list[dict]:
        with database.engine.connect() as conn:
            rows = conn.execute(select(*SUMMARY_COLUMNS).where(visible_to(blueprints.c.owner_id, user_id))
                                .order_by(blueprints.c.updated_at.desc())).mappings()
            return [self.summary(dict(row)) for row in rows]

    @staticmethod
    def summary(row: dict) -> dict:
        return {column.key: row[column.key] for column in SUMMARY_COLUMNS}

    def for_session(self, session_id: str) -> dict | None:
        with database.engine.connect() as conn:
            row = conn.execute(select(*SUMMARY_COLUMNS).where(blueprints.c.session_id == session_id)
                               .order_by(blueprints.c.updated_at.desc()).limit(1)).mappings().first()
            return self.summary(dict(row)) if row else None

    def for_sessions(self, session_ids: list[str]) -> dict[str, dict]:
        if not session_ids:
            return {}
        with database.engine.connect() as conn:
            rows = conn.execute(select(*SUMMARY_COLUMNS)
                .where(blueprints.c.session_id.in_(session_ids)).order_by(blueprints.c.updated_at.desc())).mappings()
            result = {}
            for row in rows:
                result.setdefault(row["session_id"], self.summary(dict(row)))
            return result

    def save(self, filename: str, blueprint: dict, *, session_id: str | None = None,
             owner_id: str | None = None, timestamp: int | None = None,
             actor_id: str | None = None, operation_id: str | None = None,
             label: str = "保存蓝图", base_revision: int | None = None) -> str:
        validate_filename(filename)
        session_id = session_id or session_for_filename(filename)
        now = timestamp if timestamp is not None else now_ms()
        geometry = blueprint.get("geometry") or {}
        value = dict(name=str((blueprint.get("meta") or {}).get("name") or PurePosixPath(filename).stem)[:255],
                     elements_count=len(geometry.get("elements") or []),
                     components_count=len(geometry.get("components") or []),
                     blueprint_json=blueprint, updated_at=now)
        with database.engine.begin() as conn:
            actor = lock_account(conn, actor_id) if actor_id else None
            if session_id:
                owner_id = ensure_session(conn, session_id, owner_id)["owner_id"]
                assert_session_unlocked(conn, session_id)
            current = conn.execute(select(blueprints).where(
                blueprints.c.filename == filename).with_for_update()).mappings().first()
            current = dict(current) if current else None
            assert_row_unlocked(current)
            if actor:
                if not self._authorize_save(conn, actor, filename, blueprint, current, session_id,
                                            operation_id, label, base_revision):
                    return filename
            if current:
                if owner_id is not None and current["owner_id"] not in {None, owner_id}:
                    raise AccessDenied("资料不存在")
                conn.execute(update(blueprints).where(blueprints.c.filename == filename).values(**value))
            else:
                conn.execute(insert(blueprints).values(filename=filename, session_id=session_id,
                             owner_id=owner_id, created_at=now, **value))
        return filename

    @staticmethod
    def _authorize_save(conn, actor, filename, blueprint, current, session_id,
                        operation_id, label, base_revision):
        if current and actor["identity"] != 2 and current["owner_id"] not in {None, actor["id"]}:
            raise AccessDenied("资料不存在")
        payload_hash = fingerprint(blueprint)
        if operation_id:
            previous = conn.execute(select(audit_logs).where(
                audit_logs.c.id == event_id(actor["id"], "blueprint.edit:" + operation_id))).mappings().first()
            if previous:
                if previous["resource"] != filename or previous["details"].get("fingerprint") != payload_hash:
                    raise OperationConflict("操作标识已用于其他内容，请刷新蓝图后重试")
                return False
        before = current["blueprint_json"] if current else {}
        changed = content_fingerprint(before) != content_fingerprint(blueprint)
        if changed and current and base_revision is not None:
            revision = (before.get("editor") or {}).get("revision", 1)
            if revision != base_revision:
                raise OperationConflict("蓝图已被其他操作更新，请重新加载后再修改")
        ai_edit = changed and is_verified_ai_edit(conn, actor, session_id, operation_id, before, blueprint)
        if changed and not ai_edit:
            charge_usage(conn, actor, "operations")
        details = {"label": label[:200], "fingerprint": payload_hash,
                   "charged": changed and not ai_edit, "source": "ai" if ai_edit else "user",
                   **describe_changes(before, blueprint)}
        action = "blueprint.edit" if changed else "blueprint.save"
        if ai_edit:
            action = "blueprint.ai_apply"
        append_audit(conn, actor, action,
                     resource=filename, session_id=session_id, details=details,
                     key="blueprint.edit:" + operation_id if operation_id else None)
        return True

    def delete(self, filename: str) -> bool:
        validate_filename(filename)
        with database.engine.begin() as conn:
            row = conn.execute(select(blueprints).where(blueprints.c.filename == filename)
                               .with_for_update()).mappings().first()
            assert_row_unlocked(dict(row) if row else None)
            return bool(conn.execute(delete(blueprints).where(blueprints.c.filename == filename)).rowcount)


blueprint_repository = BlueprintRepository()
