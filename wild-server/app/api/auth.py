"""固定账号登录与游客权限；认证令牌只保存在 HttpOnly Cookie 中。"""

from secrets import compare_digest, token_urlsafe
from time import time

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/auth", tags=["登录"])
ACCOUNTS = {"zlw": "123456", "lxw": "123456", "mf": "123456"}
COOKIE_NAME = "wild_session"
SESSION_SECONDS = 12 * 60 * 60
_sessions: dict[str, tuple[dict, float]] = {}


class LoginInput(BaseModel):
    username: str
    password: str


def current_user(connection) -> dict | None:
    token = (getattr(connection, "cookies", None) or {}).get(COOKIE_NAME, "")
    entry = _sessions.get(token)
    if not entry:
        return None
    user, expires = entry
    if expires <= time():
        _sessions.pop(token, None)
        return None
    return user


def can_edit(connection) -> bool:
    user = current_user(connection)
    return bool(user and user["role"] == "editor")


def _start_session(request: Request, response: Response, user: dict) -> dict:
    _sessions.pop(request.cookies.get(COOKIE_NAME, ""), None)
    for token, (_, expires) in list(_sessions.items()):
        if expires <= time():
            _sessions.pop(token, None)
    token = token_urlsafe(32)
    _sessions[token] = (user, time() + SESSION_SECONDS)
    response.set_cookie(COOKIE_NAME, token, max_age=SESSION_SECONDS,
                        httponly=True, samesite="lax", secure=request.url.scheme == "https")
    response.headers["Cache-Control"] = "no-store"
    return user


@router.post("/login")
def login(body: LoginInput, request: Request, response: Response):
    username = body.username.strip()
    expected = ACCOUNTS.get(username)
    if expected is None or not compare_digest(body.password.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    return _start_session(request, response, {"username": username, "role": "editor"})


@router.post("/guest")
def guest_login(request: Request, response: Response):
    return _start_session(request, response, {"username": "游客", "role": "guest"})


@router.get("/session")
def session(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return current_user(request)


@router.post("/logout")
def logout(request: Request, response: Response):
    _sessions.pop(request.cookies.get(COOKIE_NAME, ""), None)
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


async def enforce_write_access(request: Request, call_next):
    path = request.url.path
    protected = (path.startswith("/api/") and not path.startswith("/api/auth/")
                 and (request.method not in {"GET", "HEAD", "OPTIONS"}
                      or path.startswith("/api/config/")))
    if protected and not can_edit(request):
        logged_in = current_user(request) is not None
        return JSONResponse(status_code=403 if logged_in else 401,
                            content={"detail": "请使用账号密码登录后操作"})
    return await call_next(request)
