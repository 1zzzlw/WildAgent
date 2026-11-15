from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.infrastructure.persistence.repositories.errors import AccessDenied
from app.application.errors import ApplicationError

ERROR_STATUS = {"invalid_input": 400, "unauthenticated": 401, "forbidden": 403,
                "not_found": 404, "conflict": 409, "payload_too_large": 413, "invalid_data": 422,
                "rate_limited": 429, "internal_error": 500, "upstream_error": 502,
                "unavailable": 503, "upstream_timeout": 504}


def application_error_response(exc: ApplicationError):
    return JSONResponse(status_code=ERROR_STATUS[exc.code], content={"detail": exc.detail})


async def application_error_handler(request, exc):
    return application_error_response(exc)


async def storage_error_handler(request, exc):
    return JSONResponse(status_code=503, content={"detail": "数据服务暂不可用，请稍后重试"})


async def ownership_error_handler(request, exc):
    return JSONResponse(status_code=404, content={"detail": "资料不存在"})


def install_exception_handlers(app):
    app.add_exception_handler(ApplicationError, application_error_handler)
    app.add_exception_handler(SQLAlchemyError, storage_error_handler)
    app.add_exception_handler(RedisError, storage_error_handler)
    app.add_exception_handler(AccessDenied, ownership_error_handler)
