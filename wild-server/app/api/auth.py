"""MySQL 账号与 Redis 登录会话；浏览器只持有 HttpOnly Cookie。"""
import hashlib
import json
from secrets import token_urlsafe

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from starlette.concurrency import run_in_threadpool
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.infrastructure.cache import cache
from app.repositories.accounts import accounts
from app.services.account_service import limit, register_account, send_email_code, verify_password
from config import config

router = APIRouter(prefix="/api/auth", tags=["登录"])
COOKIE_NAME = "wild_session"


class LoginInput(BaseModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(max_length=128)


class EmailCodeInput(BaseModel):
    email: EmailStr = Field(max_length=254)


class RegisterInput(EmailCodeInput):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)
    code: str = Field(pattern=r"^[0-9]{6}$")

    @field_validator("username")
    @classmethod
    def valid_username(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2 or any(ord(char) < 32 for char in value):
            raise ValueError("用户名至少 2 个字符，且不能包含控制字符")
        return value

    @model_validator(mode="after")
    def matching_passwords(self):
        if self.password != self.confirm_password:
            raise ValueError("两次输入的密码不一致")
        return self


def _session_key(token: str) -> str:
    return cache.key("auth:session:" + hashlib.sha256(token.encode()).hexdigest())


def current_user(connection) -> dict | None:
    token = (getattr(connection, "cookies", None) or {}).get(COOKIE_NAME, "")
    if not token or len(token) > 128:
        return None
    value = cache.client.get(_session_key(token))
    if not value:
        return None
    stored = json.loads(value)
    if stored.get("role") == "guest":
        return stored
    account = accounts.get(stored.get("id", ""))
    return _editor(account) if account and account["status"] == "active" else None


def can_edit(connection) -> bool:
    return (current_user(connection) or {}).get("role") == "editor"


def _start_session(request: Request, response: Response, user: dict) -> dict:
    old = request.cookies.get(COOKIE_NAME, "")
    token = token_urlsafe(32)
    with cache.client.pipeline() as pipe:
        if old:
            pipe.delete(_session_key(old))
        stored = {"id": user["id"]} if user.get("id") else user
        pipe.set(_session_key(token), json.dumps(stored, ensure_ascii=False), ex=config.redis.session_seconds)
        pipe.execute()
    response.set_cookie(COOKIE_NAME, token, max_age=config.redis.session_seconds,
                        httponly=True, samesite="lax", secure=request.url.scheme == "https")
    response.headers["Cache-Control"] = "no-store"
    return user


def _editor(account: dict) -> dict:
    return {"id": account["id"], "username": account["username"], "email": account["email"],
            "identity": account["identity"], "role": "editor"}


@router.post("/login")
def login(body: LoginInput, request: Request, response: Response):
    limit("login:" + hashlib.sha256((request.client.host if request.client else "unknown").encode()).hexdigest(), 30, 60)
    account = accounts.find(str(body.email).lower())
    encoded = account["password_hash"] if account else "scrypt$" + "00" * 16 + "$" + "00" * 32
    verified = verify_password(body.password, encoded)
    if not account or not verified or account["status"] != "active":
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    return _start_session(request, response, _editor(account))


@router.post("/email-code")
def email_code(body: EmailCodeInput, request: Request):
    return send_email_code(str(body.email).lower(), request.client.host if request.client else "unknown")


@router.post("/register", status_code=201)
def register(body: RegisterInput, request: Request, response: Response):
    account = register_account(body.username, str(body.email).lower(), body.password, body.code)
    return _start_session(request, response, _editor(account))


@router.post("/guest")
def guest_login(request: Request, response: Response):
    return _start_session(request, response, {"username": "游客", "role": "guest"})


@router.get("/session")
def session(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return current_user(request)


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME, "")
    if token:
        cache.client.delete(_session_key(token))
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


async def enforce_write_access(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/") or path.startswith("/api/auth/"):
        return await call_next(request)
    try:
        user = await run_in_threadpool(current_user, request)
    except (RedisError, SQLAlchemyError):
        return JSONResponse(status_code=503, content={"detail": "登录服务暂不可用，请稍后重试"})
    request.state.user = user
    protected = request.method not in {"GET", "HEAD", "OPTIONS"} or path.startswith("/api/config/")
    if protected and (user or {}).get("role") != "editor":
        return JSONResponse(status_code=403 if user else 401, content={"detail": "请使用账号密码登录后操作"})
    from app.services.access_service import check_blueprint, check_session
    try:
        if path.startswith("/api/scenes/"):
            await run_in_threadpool(check_blueprint, path.removeprefix("/api/scenes/"), user)
        elif path.startswith(("/api/sessions/", "/api/designs/")):
            sid = path.split("/")[3]
            if sid != "schema":
                await run_in_threadpool(check_session, sid, user)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except (SQLAlchemyError, RedisError):
        return JSONResponse(status_code=503, content={"detail": "数据服务暂不可用，请稍后重试"})
    return await call_next(request)
