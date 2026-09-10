"""DesignDocument 的原子文件持久化、版本归档与 Patch 应用。"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
import shutil
from typing import Any

from .contracts import DesignDocument, DesignPatch, utc_now_iso
from .resolver import render_design_svg, resolve_design


_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_EDITABLE_ROOTS = ("/requirements", "/decisions", "/constraints", "/locks")


class DesignConflictError(ValueError):
    pass


class DesignRepository:
    def __init__(self, root: Path | None = None):
        server_root = Path(__file__).resolve().parents[2]
        self.root = Path(root or server_root / "storage" / "designs")

    def _safe_session_id(self, session_id: str) -> str:
        if not _SESSION_RE.fullmatch(str(session_id or "")):
            raise ValueError("无效的 session_id")
        return session_id

    def document_path(self, session_id: str) -> Path:
        return self.root / f"{self._safe_session_id(session_id)}.design.json"

    def resolved_path(self, session_id: str) -> Path:
        return self.root / f"{self._safe_session_id(session_id)}.resolved.json"

    def svg_path(self, session_id: str) -> Path:
        return self.root / f"{self._safe_session_id(session_id)}.svg"

    def _atomic_write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)

    def get(self, session_id: str) -> DesignDocument | None:
        path = self.document_path(session_id)
        if not path.exists():
            return None
        return DesignDocument.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, document: DesignDocument | dict[str, Any]) -> tuple[DesignDocument, dict[str, Any]]:
        doc = document if isinstance(document, DesignDocument) else DesignDocument.model_validate(document)
        self._validate_component_capabilities(doc)
        resolved = resolve_design(doc)
        payload = doc.model_dump_json(indent=2)
        resolved_payload = resolved.model_dump_json(indent=2)
        self._atomic_write(self.document_path(doc.session_id), payload)
        self._atomic_write(self.resolved_path(doc.session_id), resolved_payload)
        self._atomic_write(self.svg_path(doc.session_id), render_design_svg(doc, resolved))
        history_dir = self.root / "history" / self._safe_session_id(doc.session_id)
        self._atomic_write(history_dir / f"revision_{doc.revision}.json", payload)
        return doc, resolved.model_dump(mode="json")

    @staticmethod
    def _validate_component_capabilities(document: DesignDocument) -> None:
        """阻止 Patch 把未实现构件重新写回可执行配额。"""

        from app.agent.component_registry import get_implemented_components

        supported = {item.component_type for item in get_implemented_components()}
        selected = set(document.decisions.required_components) | set(
            document.decisions.component_quota
        )
        unsupported = sorted(selected - supported)
        if unsupported:
            raise ValueError(
                "DesignDocument 含当前编译器未实现的构件: " + ", ".join(unsupported)
            )

    def delete(self, session_id: str) -> None:
        safe_session_id = self._safe_session_id(session_id)
        for path in (self.document_path(session_id), self.resolved_path(session_id), self.svg_path(session_id)):
            if path.exists():
                path.unlink()
        history_dir = self.root / "history" / safe_session_id
        if history_dir.exists():
            shutil.rmtree(history_dir)

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
            self._apply_operation(data, operation.op, operation.path, deepcopy(operation.value))
        data["revision"] = current.revision + 1
        data["status"] = "draft"
        data["approved_at"] = None
        data["updated_at"] = utc_now_iso()
        return self.save(DesignDocument.model_validate(data))

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
        data = current.model_dump(mode="json")
        data["status"] = "approved"
        data["approved_at"] = utc_now_iso()
        data["updated_at"] = data["approved_at"]
        return self.save(DesignDocument.model_validate(data))

    def mark_compiled(
        self,
        session_id: str,
        *,
        revision: int,
        design_hash: str,
    ) -> tuple[DesignDocument, dict[str, Any]]:
        """在 Blueprint 保存成功后，将完全相同的已批准设计标记为已编译。"""

        current = self.get(session_id)
        if current is None:
            raise FileNotFoundError("设计文档不存在")
        if current.revision != revision:
            raise DesignConflictError(
                f"设计版本冲突：当前 r{current.revision}，编译结果来自 r{revision}"
            )
        if current.status not in {"approved", "compiled"}:
            raise DesignConflictError("只有已批准的设计才能标记为 compiled")
        resolved = resolve_design(current)
        if resolved.design_hash != design_hash:
            raise DesignConflictError("Blueprint 的 designHash 与当前设计不一致")
        data = current.model_dump(mode="json")
        data["status"] = "compiled"
        data["updated_at"] = utc_now_iso()
        return self.save(DesignDocument.model_validate(data))

    @staticmethod
    def _tokens(path: str) -> list[str]:
        return [token.replace("~1", "/").replace("~0", "~") for token in path.lstrip("/").split("/")]

    @classmethod
    def _apply_operation(cls, data: dict[str, Any], op: str, path: str, value: Any) -> None:
        tokens = cls._tokens(path)
        if not tokens or any(token == "" for token in tokens):
            raise ValueError(f"无效 JSON Pointer: {path}")
        parent: Any = data
        for token in tokens[:-1]:
            if isinstance(parent, list):
                try:
                    parent = parent[int(token)]
                except (ValueError, IndexError) as exc:
                    raise ValueError(f"路径不存在: {path}") from exc
            elif isinstance(parent, dict) and token in parent:
                parent = parent[token]
            else:
                raise ValueError(f"路径不存在: {path}")
        key = tokens[-1]
        if isinstance(parent, list):
            if key == "-" and op == "add":
                parent.append(value)
                return
            try:
                index = int(key)
            except ValueError as exc:
                raise ValueError(f"列表下标无效: {path}") from exc
            if op == "add":
                if index < 0 or index > len(parent):
                    raise ValueError(f"列表下标越界: {path}")
                parent.insert(index, value)
            elif op == "replace":
                if index < 0 or index >= len(parent):
                    raise ValueError(f"路径不存在: {path}")
                parent[index] = value
            else:
                if index < 0 or index >= len(parent):
                    raise ValueError(f"路径不存在: {path}")
                parent.pop(index)
            return
        if not isinstance(parent, dict):
            raise ValueError(f"路径父节点不可修改: {path}")
        if op == "add":
            parent[key] = value
        elif op == "replace":
            if key not in parent:
                raise ValueError(f"路径不存在: {path}")
            parent[key] = value
        else:
            if key not in parent:
                raise ValueError(f"路径不存在: {path}")
            del parent[key]


design_repository = DesignRepository()
