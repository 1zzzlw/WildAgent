"""HTTP 身份与资料归属检查。"""
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from app.api.dependencies import current_user
from app.application.errors import ApplicationError
from app.api.exception_handlers import application_error_response
from app.api.exception_handlers import permission_error_handler
from app.application.access import require_admin, check_session_writable
from app.infrastructure.persistence.repositories.activity import record_activity
from app.infrastructure.persistence.repositories.errors import AccountUnavailable, BlueprintLocked


async def enforce_write_access(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/") or path.startswith("/api/auth/"):
        return await call_next(request)
    try:
        user = await run_in_threadpool(current_user, request)
    except (RedisError, SQLAlchemyError):
        return JSONResponse(status_code=503, content={"detail": "登录服务暂不可用，请稍后重试"})
    request.state.user = user
    protected = request.method not in {"GET", "HEAD", "OPTIONS"} or path.startswith(("/api/config/", "/api/admin/"))
    if protected and (user or {}).get("role") != "editor":
        return JSONResponse(status_code=403 if user else 401, content={"detail": "请使用账号密码登录后操作"})
    from app.application.access import check_blueprint
    from app.application.access import check_session
    try:
        if path.startswith(("/api/admin/", "/api/config/")):
            require_admin(user)
        if request.method == "DELETE" and path.startswith("/api/scenes/"):
            require_admin(user)
        if path.startswith("/api/scenes/"):
            await run_in_threadpool(check_blueprint, path.removeprefix("/api/scenes/"), user)
        elif path.startswith(("/api/sessions/", "/api/designs/")):
            sid = path.split("/")[3]
            if sid != "schema":
                await run_in_threadpool(check_session, sid, user)
                if request.method not in {"GET", "HEAD", "OPTIONS"} and (
                    path.startswith("/api/designs/") or len(path.rstrip("/").split("/")) == 4
                ):
                    await run_in_threadpool(check_session_writable, sid, user)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    except ApplicationError as exc:
        return application_error_response(exc)
    except (AccountUnavailable, BlueprintLocked) as exc:
        return await permission_error_handler(request, exc)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except (SQLAlchemyError, RedisError):
        return JSONResponse(status_code=503, content={"detail": "数据服务暂不可用，请稍后重试"})
    response = await call_next(request)
    if response.status_code < 400 and user and user.get("id"):
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not path.startswith(("/api/scenes/", "/api/admin/")):
            action = "config.update" if path == "/api/config/llm" else "http." + request.method.lower()
            await run_in_threadpool(record_activity, user["id"], action,
                                    resource=path, details={"method": request.method, "status": response.status_code})
        elif request.method == "GET" and path.startswith("/api/scenes/"):
            await run_in_threadpool(record_activity, user["id"], "blueprint.view",
                                    resource=path.removeprefix("/api/scenes/"))
    return response
