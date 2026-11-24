"""DesignDocument 的数据库版本存储与 Patch 应用。"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from sqlalchemy import delete, insert, select, update
from app.infrastructure.persistence.database import Database
from app.infrastructure.persistence.database import database
from app.infrastructure.persistence.schema import designs
from app.infrastructure.persistence.repositories.conversations import ensure_session
from app.infrastructure.persistence.repositories.conversations import now_ms
from app.infrastructure.persistence.repositories.locks import assert_session_unlocked

from agent.utils.design.contracts import DesignDocument
from agent.utils.design.contracts import DesignPatch
from agent.utils.design.contracts import utc_now_iso
from agent.utils.design.resolver import resolve_design
from agent.utils.design.patch import apply_operation


_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_EDITABLE_ROOTS = ("/requirements", "/decisions", "/constraints", "/locks")


class DesignConflictError(ValueError):
    pass


class DesignRepository:
    def __init__(self, db: Database = database):
        self.database = db

    def _safe_session_id(self, session_id: str) -> str:
        if not _SESSION_RE.fullmatch(str(session_id or "")) or len(session_id) > 128:
            raise ValueError("无效的 session_id")
        return session_id

    def get(self, session_id: str) -> DesignDocument | None:
        self._safe_session_id(session_id)
        with self.database.engine.connect() as conn:
            row = conn.execute(select(designs.c.document_json).where(designs.c.session_id == session_id)
                               .order_by(designs.c.revision.desc()).limit(1)).first()
            return DesignDocument.model_validate(row[0]) if row else None

    def save(self, document: DesignDocument | dict[str, Any], *, expected_revision: int | None = None) -> tuple[DesignDocument, dict[str, Any]]:
        doc = document if isinstance(document, DesignDocument) else DesignDocument.model_validate(document)
        self._safe_session_id(doc.session_id)
        self._validate_component_capabilities(doc)
        resolved = resolve_design(doc)
        with self.database.engine.begin() as conn:
            ensure_session(conn, doc.session_id)
            assert_session_unlocked(conn, doc.session_id)
            latest = conn.execute(select(designs.c.revision).where(designs.c.session_id == doc.session_id)
                                  .order_by(designs.c.revision.desc()).limit(1).with_for_update()).scalar()
            if expected_revision is not None and latest != expected_revision:
                raise DesignConflictError("设计版本已更新，请重新读取后修改")
            if latest is not None and doc.revision < latest:
                raise DesignConflictError("不能覆盖较新的设计版本")
            condition = (designs.c.session_id == doc.session_id) & (designs.c.revision == doc.revision)
            value = dict(document_json=doc.model_dump(mode="json"),
                         resolved_json=resolved.model_dump(mode="json"), updated_at=now_ms())
            if conn.execute(select(designs.c.revision).where(condition)).first():
                conn.execute(update(designs).where(condition).values(**value))
            else:
                conn.execute(insert(designs).values(session_id=doc.session_id, revision=doc.revision, **value))
        return doc, resolved.model_dump(mode="json")

    @staticmethod
    def _validate_component_capabilities(document: DesignDocument) -> None:
        """阻止 Patch 把未实现构件重新写回可执行配额。"""

        from agent.utils.components.registry import get_implemented_components
        from agent.utils.design.contracts import ObjectDecisions

        supported = {item.component_type for item in get_implemented_components()}
        decisions = document.decisions
        # 物件文档没有 required_components / component_quota —— 它的"要做什么"写在
        # `objects` 里。这里必须按判别字段取对应的那支，否则 `AttributeError` 会在
        # 保存设计文档这一步就炸掉整轮生成。
        if isinstance(decisions, ObjectDecisions):
            selected = {str(item.kind) for item in decisions.objects}
        else:
            return  # 建筑设计不按原生构件能力拒绝；plan 可以用多个元素组合实现。
        unsupported = sorted(selected - supported)
        if unsupported:
            raise ValueError(
                "DesignDocument 含当前编译器未实现的构件: " + ", ".join(unsupported)
            )

    def delete(self, session_id: str) -> None:
        self._safe_session_id(session_id)
        with self.database.engine.begin() as conn:
            assert_session_unlocked(conn, session_id)
            conn.execute(delete(designs).where(designs.c.session_id == session_id))

    def apply_patch(self, session_id: str, patch: DesignPatch | dict[str, Any]) -> tuple[DesignDocument, dict[str, Any]]:
        change = patch if isinstance(patch, DesignPatch) else DesignPatch.model_validate(patch)
        current = self.get(session_id)
        if current is None:
            raise FileNotFoundError("设计文档不存在")
        if change.base_revision != current.revision:
            raise DesignConflictError(
                f"设计版本冲突：当前 r{current.revision}，Patch 基于 r{change.base_revision}"
            )
        data = current.model_dump(mode="json")
        for operation in change.operations:
            if not any(operation.path == root or operation.path.startswith(root + "/") for root in _EDITABLE_ROOTS):
                raise ValueError(f"不允许修改系统字段: {operation.path}")
            if any(
                operation.path == lock
                or operation.path.startswith(lock + "/")
                or lock.startswith(operation.path + "/")
                for lock in current.locks
            ):
                raise DesignConflictError(f"字段已锁定: {operation.path}")
            apply_operation(data, operation.op, operation.path, deepcopy(operation.value))
        data["revision"] = current.revision + 1
        data["status"] = "draft"
        data["approved_at"] = None
        data["updated_at"] = utc_now_iso()
        return self.save(DesignDocument.model_validate(data), expected_revision=current.revision)

    def approve(self, session_id: str, base_revision: int) -> tuple[DesignDocument, dict[str, Any]]:
        current = self.get(session_id)
        if current is None:
            raise FileNotFoundError("设计文档不存在")
        if current.revision != base_revision:
            raise DesignConflictError(
                f"设计版本冲突：当前 r{current.revision}，批准请求基于 r{base_revision}"
            )
        if current.status == "compiled":
            raise DesignConflictError("已编译设计必须先产生新 revision，不能降级为 approved")
        resolved = resolve_design(current)
        if resolved.compile_blockers:
            raise DesignConflictError("当前草稿有确定性编译阻断，请修订后重新审核：" +
                                      "；".join(d["evidence"] for d in resolved.compile_blockers))
        data = current.model_dump(mode="json")
        data["status"] = "approved"
        data["approved_at"] = utc_now_iso()
        data["updated_at"] = data["approved_at"]
        return self.save(DesignDocument.model_validate(data), expected_revision=current.revision)


design_repository = DesignRepository()
