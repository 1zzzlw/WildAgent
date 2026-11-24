"""designs 业务用例，传输协议由 API 层适配。"""


from app.application.errors import ApplicationError


from app.domain.design.contracts import DesignDocument
from app.domain.design.contracts import DesignPatch
from app.infrastructure.persistence.repositories.designs import DesignConflictError
from app.infrastructure.persistence.repositories.designs import design_repository
from app.domain.design.resolver import resolve_design


def _package(document: DesignDocument, resolved: dict) -> dict:
    return {
        "document": document.model_dump(mode="json"),
        "resolved": resolved,
    }


def get_design_schema():
    return DesignDocument.model_json_schema()


def get_design(session_id: str):
    try:
        document = design_repository.get(session_id)
    except ValueError as exc:
        raise ApplicationError('invalid_input', str(exc)) from exc
    if document is None:
        raise ApplicationError('not_found', "设计文档不存在")
    resolved = resolve_design(document).model_dump(mode="json")
    return _package(document, resolved)


def patch_design(session_id: str, patch: DesignPatch):
    try:
        document, resolved = design_repository.apply_patch(session_id, patch)
    except FileNotFoundError as exc:
        raise ApplicationError('not_found', str(exc)) from exc
    except DesignConflictError as exc:
        raise ApplicationError('conflict', str(exc)) from exc
    except ValueError as exc:
        raise ApplicationError('invalid_data', str(exc)) from exc
    return _package(document, resolved)


def approve_design(session_id: str, base_revision: int):
    try:
        document, resolved = design_repository.approve(session_id, base_revision)
    except FileNotFoundError as exc:
        raise ApplicationError('not_found', str(exc)) from exc
    except DesignConflictError as exc:
        raise ApplicationError('conflict', str(exc)) from exc
    except ValueError as exc:
        raise ApplicationError('invalid_data', str(exc)) from exc
    return _package(document, resolved)
