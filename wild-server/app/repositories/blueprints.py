from __future__ import annotations

from pathlib import PurePosixPath
import re

from sqlalchemy import delete, insert, select, update

from app.infrastructure.database import database
from app.infrastructure.schema import blueprints
from .conversations import ensure_session, now_ms, visible_to
from .errors import AccessDenied

SUMMARY_COLUMNS = [blueprints.c[key] for key in ("filename", "name", "elements_count", "components_count", "updated_at")]


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
        return {key: row[key] for key in ("filename", "name", "elements_count", "components_count", "updated_at")}

    def for_session(self, session_id: str) -> dict | None:
        with database.engine.connect() as conn:
            row = conn.execute(select(*SUMMARY_COLUMNS).where(blueprints.c.session_id == session_id)
                               .order_by(blueprints.c.updated_at.desc()).limit(1)).mappings().first()
            return self.summary(dict(row)) if row else None

    def for_sessions(self, session_ids: list[str]) -> dict[str, dict]:
        if not session_ids:
            return {}
        with database.engine.connect() as conn:
            rows = conn.execute(select(blueprints.c.session_id, *SUMMARY_COLUMNS)
                .where(blueprints.c.session_id.in_(session_ids)).order_by(blueprints.c.updated_at.desc())).mappings()
            result = {}
            for row in rows:
                result.setdefault(row["session_id"], self.summary(dict(row)))
            return result

    def save(self, filename: str, blueprint: dict, *, session_id: str | None = None,
             owner_id: str | None = None, timestamp: int | None = None) -> str:
        validate_filename(filename)
        session_id = session_id or session_for_filename(filename)
        now = timestamp if timestamp is not None else now_ms()
        geometry = blueprint.get("geometry") or {}
        value = dict(name=str((blueprint.get("meta") or {}).get("name") or PurePosixPath(filename).stem)[:255],
                     elements_count=len(geometry.get("elements") or []),
                     components_count=len(geometry.get("components") or []),
                     blueprint_json=blueprint, updated_at=now)
        with database.engine.begin() as conn:
            if session_id:
                owner_id = ensure_session(conn, session_id, owner_id)["owner_id"]
            current = conn.execute(select(blueprints.c.filename, blueprints.c.owner_id).where(
                blueprints.c.filename == filename).with_for_update()).first()
            if current:
                if owner_id is not None and current.owner_id not in {None, owner_id}:
                    raise AccessDenied("资料不存在")
                conn.execute(update(blueprints).where(blueprints.c.filename == filename).values(**value))
            else:
                conn.execute(insert(blueprints).values(filename=filename, session_id=session_id,
                             owner_id=owner_id, created_at=now, **value))
        return filename

    def delete(self, filename: str) -> bool:
        validate_filename(filename)
        with database.engine.begin() as conn:
            return bool(conn.execute(delete(blueprints).where(blueprints.c.filename == filename)).rowcount)


blueprint_repository = BlueprintRepository()
