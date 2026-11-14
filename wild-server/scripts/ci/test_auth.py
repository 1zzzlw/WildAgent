"""邮箱账号、管理员权限、游客隔离及认证失效回归；不调用模型。"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.api import auth


@pytest.fixture
def client(storage):
    app = FastAPI()
    app.include_router(auth.router)
    app.middleware("http")(auth.enforce_write_access)
    writes = []

    @app.api_route("/api/scenes/test.wild", methods=["GET", "PUT", "POST", "DELETE", "PATCH"])
    async def scene_route():
        writes.append(True)
        return {"ok": True}

    @app.get("/api/config/llm")
    async def config_route():
        return {"ok": True}

    from app.repositories.accounts import accounts
    from app.services.account_service import hash_password
    from app.infrastructure.schema import users
    for username in ("zlw", "lxw", "mf"):
        accounts.create(username, username + "@example.com", hash_password("123456"))
    with storage.begin() as conn:
        conn.execute(users.update().where(users.c.email == "zlw@example.com").values(identity=2))
    with TestClient(app) as http:
        yield http, writes


@pytest.mark.parametrize("username", ["zlw", "lxw", "mf"])
def test_email_accounts_share_the_same_editor_functions(client, username):
    http, writes = client
    response = http.post("/api/auth/login", json={"email": username + "@example.com", "password": "123456"})
    assert response.status_code == 200
    assert response.json()["username"] == username
    assert response.json()["role"] == "editor"
    assert response.json()["id"]
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "123456" not in response.headers["set-cookie"]
    assert http.get("/api/auth/session").json() == response.json()
    assert http.put("/api/scenes/test.wild").status_code == 200
    assert http.get("/api/config/llm").status_code == 200
    assert auth.can_edit(SimpleNamespace(cookies=dict(http.cookies)))


@pytest.mark.parametrize("username,password", [("zlw", "wrong"), ("lxw", ""), ("unknown", "123456"), ("mf", "１２３４５６")])
def test_invalid_login_does_not_grant_access(client, username, password):
    http, _ = client
    assert http.post("/api/auth/login", json={"email": username + "@example.com", "password": password}).status_code == 401
    assert http.get("/api/auth/session").json() is None
    assert http.put("/api/scenes/test.wild").status_code == 401


def test_guest_can_read_but_cannot_write_or_configure(client):
    http, writes = client
    assert http.post("/api/auth/guest").json()["role"] == "guest"
    for method in ["PUT", "POST", "PATCH", "DELETE"]:
        assert http.request(method, "/api/scenes/test.wild").status_code == 403
    assert writes == []
    assert http.get("/api/config/llm").status_code == 403
    assert not auth.can_edit(SimpleNamespace(cookies=dict(http.cookies)))
    assert http.get("/api/scenes/test.wild").status_code == 200


def test_logout_rejects_replayed_token_and_guest_downgrade_revokes_editor(client):
    http, _ = client
    http.post("/api/auth/login", json={"email": "zlw@example.com", "password": "123456"})
    editor = SimpleNamespace(cookies=dict(http.cookies))
    http.post("/api/auth/guest")
    assert not auth.can_edit(editor)
    guest = SimpleNamespace(cookies=dict(http.cookies))
    http.post("/api/auth/logout")
    assert auth.current_user(guest) is None
    assert http.get("/api/auth/session").json() is None
    assert http.put("/api/scenes/test.wild").status_code == 401


def test_expired_or_forged_cookie_is_not_an_editor(client):
    http, _ = client
    http.post("/api/auth/login", json={"email": "mf@example.com", "password": "123456"})
    editor = SimpleNamespace(cookies=dict(http.cookies))
    from app.infrastructure.cache import cache
    cache.client.expire(auth._session_key(editor.cookies[auth.COOKIE_NAME]), -1)
    assert not auth.can_edit(editor)
    assert http.put("/api/scenes/test.wild").status_code == 401
    http.cookies.set(auth.COOKIE_NAME, '{"username":"mf","role":"editor"}')
    assert http.put("/api/scenes/test.wild").status_code == 401
