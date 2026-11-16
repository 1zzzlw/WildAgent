"""管理员后台 API；每个接口都显式校验管理员身份。"""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.concurrency import run_in_threadpool

from app.application import administration as use_cases
from app.application.access import require_admin
from app.infrastructure.persistence.repositories import administration as repository

router = APIRouter(prefix="/api/admin", tags=["管理后台"])


def administrator(request: Request) -> dict:
    return require_admin(getattr(request.state, "user", None))


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identity: Literal[1, 2] | None = None
    status: Literal["active", "blocked"] | None = None
    operations_remaining: int | None = Field(default=None, ge=0, le=1000000000)
    ai_remaining: int | None = Field(default=None, ge=0, le=1000000000)
    operations_daily_limit: int | None = Field(default=None, ge=0, le=1000000000)
    ai_daily_limit: int | None = Field(default=None, ge=0, le=1000000000)

    @model_validator(mode="after")
    def reject_null(self):
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError("管理字段不能设置为 null")
        return self


class BlueprintLock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    locked: bool


@router.get("/stats")
def stats(user: dict = Depends(administrator)):
    return repository.statistics()


@router.get("/users")
def users(
    user: dict = Depends(administrator),
    query: str = Query(default="", max_length=128),
    status: Literal["active", "blocked"] | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    return use_cases.list_users(
        user, query=query, status=status, page=page, page_size=page_size
    )


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str, body: UserUpdate, user: dict = Depends(administrator)
):
    result = await run_in_threadpool(
        use_cases.update_user, user, user_id, body.model_dump(exclude_unset=True)
    )
    if result["status"] == "blocked":
        from app.application.generation.jobs import generation_job_service

        await generation_job_service.stop_account_jobs(user_id)
    return result


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, user: dict = Depends(administrator)):
    from app.application.generation.jobs import generation_job_service

    result = await run_in_threadpool(use_cases.delete_user, user, user_id)
    await generation_job_service.stop_account_jobs(user_id)
    return result


@router.get("/logs")
def logs(
    user: dict = Depends(administrator),
    user_id: str | None = Query(default=None, max_length=36),
    action: str | None = Query(default=None, max_length=64),
    query: str = Query(default="", max_length=128),
    since: int | None = Query(default=None, ge=0),
    until: int | None = Query(default=None, ge=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    return repository.list_activity(
        user_id, action, query, since, until, page, page_size
    )


@router.get("/blueprints")
def blueprints(
    user: dict = Depends(administrator),
    query: str = Query(default="", max_length=128),
    locked: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    return use_cases.list_blueprints(
        user, query=query, locked=locked, page=page, page_size=page_size
    )


@router.get("/blueprints/{filename:path}/metrics")
def blueprint_metrics(filename: str, user: dict = Depends(administrator)):
    return use_cases.get_blueprint_metrics(user, filename)


@router.patch("/blueprints/{filename:path}")
def lock_blueprint(
    filename: str, body: BlueprintLock, user: dict = Depends(administrator)
):
    return use_cases.set_blueprint_lock(user, filename, body.locked)
