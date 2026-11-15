"""请求身份解析与浏览器登录会话适配。"""
from fastapi import Request, Response
from app.application.accounts import open_session, public_account, resolve_session, session_key
from config import config


COOKIE_NAME = "wild_session"


def _session_key(token: str) -> str:
    return session_key(token)


def current_user(connection) -> dict | None:
    token = (getattr(connection, "cookies", None) or {}).get(COOKIE_NAME, "")
    return resolve_session(token)


def can_edit(connection) -> bool:
    return (current_user(connection) or {}).get("role") == "editor"


def _start_session(request: Request, response: Response, user: dict) -> dict:
    token = open_session(user, request.cookies.get(COOKIE_NAME, ""))
    response.set_cookie(COOKIE_NAME, token, max_age=config.redis.session_seconds,
                        httponly=True, samesite="lax", secure=request.url.scheme == "https")
    response.headers["Cache-Control"] = "no-store"
    return user


def _editor(account: dict) -> dict:
    return public_account(account)
