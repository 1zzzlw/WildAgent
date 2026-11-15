"""账号 HTTP 接口。"""
from fastapi import APIRouter, Request, Response
from app.application.accounts import register_account
from app.application.accounts import send_email_code
from app.application.accounts import authenticate, close_session
from app.api.dependencies import COOKIE_NAME
from app.api.schemas.auth import EmailCodeInput
from app.api.schemas.auth import LoginInput
from app.api.schemas.auth import RegisterInput
from app.api.dependencies import _editor
from app.api.dependencies import _start_session
from app.api.dependencies import current_user


router = APIRouter(prefix="/api/auth", tags=["登录"])


@router.post("/login")
def login(body: LoginInput, request: Request, response: Response):
    user = authenticate(str(body.email), body.password, request.client.host if request.client else "unknown")
    return _start_session(request, response, user)


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
    close_session(token)
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}
