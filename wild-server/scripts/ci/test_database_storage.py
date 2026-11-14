"""存储、账号与数据归属回归；不调用模型，不向外部邮箱发送邮件。"""
import hashlib
import json
import re

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api import auth, scenes, sessions
from app.infrastructure.cache import cache
from app.infrastructure.schema import users
from app.repositories.accounts import accounts
from app.repositories.blueprints import blueprint_repository
from app.repositories.conversations import conversations
from app.repositories.errors import AccessDenied
from app.services.account_service import email_key, hash_password
from config import SMTPConfig, config


def blueprint(name="测试蓝图"):
    return {"meta": {"version": "1.1", "type": "building", "name": name},
            "geometry": {"elements": [], "components": []}, "materials": {}}


@pytest.fixture
def signup(storage, monkeypatch):
    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(scenes.router)
    app.include_router(sessions.router)
    app.middleware("http")(auth.enforce_write_access)
    @app.get("/api/config/test")
    def admin_config():
        return {"scope": "admin"}
    sent = []
    class SMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def send_message(self, message): sent.append(message)
        def login(self, *args): pass
    monkeypatch.setattr(config, "smtp", SMTPConfig(host="smtp.example.com", from_address="wild@example.com"))
    monkeypatch.setattr("app.services.account_service.smtplib.SMTP_SSL", SMTP)
    with TestClient(app) as client:
        yield client, sent, app


def request_code(client, sent, email="designer@example.com"):
    result = client.post("/api/auth/email-code", json={"email": email})
    assert result.status_code == 200, result.text
    assert result.json()["resend_after"] == 60
    return re.search(r"[0-9]{6}", sent[-1].get_body(preferencelist=("plain",)).get_content()).group()


def registration(code, **changes):
    return {"username": "设计师", "email": "designer@example.com", "password": "Wild-test-123",
            "confirm_password": "Wild-test-123", "code": code, **changes}


def test_signup_email_login_and_cookie_survive_new_http_client(signup, storage):
    client, sent, app = signup
    code = request_code(client, sent)
    assert client.post("/api/auth/email-code", json={"email": "designer@example.com"}).status_code == 429
    stored = cache.client.get(cache.key("email:code:" + email_key("designer@example.com")))
    assert "digest" in json.loads(stored) and code not in stored
    result = client.post("/api/auth/register", json=registration(code))
    assert result.status_code == 201, result.text
    account = accounts.find("designer@example.com")
    assert account["email"] == "designer@example.com"
    assert account["password_hash"].startswith("scrypt$")
    assert "Wild-test-123" not in account["password_hash"]
    assert "password" not in result.text
    assert cache.client.get(cache.key("email:code:" + email_key(account["email"]))) is None
    with TestClient(app) as reconnected:
        reconnected.cookies.update(client.cookies)
        assert reconnected.get("/api/auth/session").json()["id"] == account["id"]
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "designer@example.com", "password": "Wild-test-123"}).status_code == 200
    assert client.post("/api/auth/register", json=registration(code)).status_code == 400


def test_wrong_code_has_attempt_limit_and_confirmation_is_enforced(signup):
    client, sent, _ = signup
    code = request_code(client, sent)
    assert client.post("/api/auth/register", json=registration(code, confirm_password="Different-password")).status_code == 422
    wrong = f"{(int(code) + 1) % 1000000:06d}"
    for _ in range(5):
        assert client.post("/api/auth/register", json=registration(wrong)).status_code == 400
    assert client.post("/api/auth/register", json=registration(code)).status_code == 400
    assert accounts.find("designer@example.com") is None


def test_identity_is_database_managed_and_does_not_change_functions(signup, storage):
    client, sent, _ = signup
    code = request_code(client, sent)
    assert client.post("/api/auth/register", json={**registration(code), "identity": 2}).status_code == 422
    result = client.post("/api/auth/register", json=registration(code))
    assert result.status_code == 201
    assert result.json()["identity"] == 1
    assert client.get("/api/config/test").status_code == 200
    assert client.post("/api/auth/login", json={"username":"设计师", "password":"Wild-test-123"}).status_code == 422
    with storage.begin() as conn:
        conn.execute(users.update().where(users.c.email == "designer@example.com").values(identity=2))
    assert client.get("/api/auth/session").json()["identity"] == 2
    assert client.get("/api/config/test").status_code == 200
    with storage.begin() as conn:
        conn.execute(users.update().where(users.c.email == "designer@example.com").values(identity=1))
    assert client.get("/api/config/test").status_code == 200


def test_expired_code_and_smtp_failure_are_not_successful(signup, monkeypatch):
    client, sent, _ = signup
    code = request_code(client, sent)
    cache.client.expire(cache.key("email:code:" + email_key("designer@example.com")), -1)
    assert client.post("/api/auth/register", json=registration(code)).status_code == 400
    def unavailable(*args, **kwargs):
        raise OSError("test smtp unavailable")
    monkeypatch.setattr("app.services.account_service.smtplib.SMTP_SSL", unavailable)
    response = client.post("/api/auth/email-code", json={"email": "another@example.com"})
    assert response.status_code == 503
    assert cache.client.get(cache.key("email:cooldown:" + email_key("another@example.com"))) is None
    assert cache.client.get(cache.key("email:code:" + email_key("another@example.com"))) is None


def test_private_sessions_are_isolated_and_shared_history_remains_visible(signup, storage):
    client, _, app = signup
    first = accounts.create("first", "first@example.com", hash_password("Wild-test-123"))
    second = accounts.create("second", "second@example.com", hash_password("Wild-test-123"))
    client.post("/api/auth/login", json={"email": "first@example.com", "password": "Wild-test-123"})
    sid = client.post("/api/sessions").json()["session_id"]
    path = f"2026-11-14/{sid}_私有蓝图.wild"
    assert client.put("/api/scenes/" + path, json=blueprint()).status_code == 200
    assert client.post(f"/api/sessions/{sid}/messages", json=[{"id":"one", "role":"user", "content":"私人消息"}]).json()["message_count"] == 1
    assert client.post(f"/api/sessions/{sid}/messages", json=[{"id":"one", "role":"user", "content":"私人消息"}]).json()["message_count"] == 1
    assert client.get(f"/api/sessions/{sid}/messages").json()[0]["content"] == "私人消息"
    assert blueprint_repository.get(path)["owner_id"] == first["id"]
    blueprint_repository.save("session_900_shared.wild", blueprint("共享资料"))
    with TestClient(app) as other:
        other.post("/api/auth/login", json={"email":"second@example.com", "password":"Wild-test-123"})
        assert {row["filename"] for row in other.get("/api/scenes").json()} == {"session_900_shared.wild"}
        assert other.get("/api/scenes/" + path).status_code == 404
        assert other.get(f"/api/sessions/{sid}/messages").status_code == 404
        assert other.put(f"/api/scenes/{sid}_其他名字.wild", json=blueprint()).status_code == 404
        assert other.delete(f"/api/sessions/{sid}").status_code == 404
    with pytest.raises(AccessDenied):
        conversations.ensure(sid, second["id"])
    with TestClient(app) as guest:
        guest.post("/api/auth/guest")
        assert len(guest.get("/api/sessions").json()) == 1
        assert guest.get("/api/scenes/session_900_shared.wild").status_code == 200
        assert guest.get("/api/scenes/" + path).status_code == 404
    storage.dispose()
    assert client.get("/api/scenes/" + path).json() == blueprint()


def test_legacy_migration_is_repeatable_and_preserves_source(storage, tmp_path):
    from scripts.migrate_legacy_storage import migrate_legacy
    (tmp_path/"sessions").mkdir()
    (tmp_path/"scenes").mkdir()
    meta = tmp_path/"sessions/session_123.json"
    meta.write_text(json.dumps({"name":"历史", "messages":[{"id":"old", "content":"历史消息"}],
        "turns":[{"request_id":"req_old", "status":"done"}], "created_at":100, "updated_at":200}), encoding="utf-8")
    wild = tmp_path/"scenes/session_123_历史.wild"
    wild.write_text(json.dumps(blueprint("历史")), encoding="utf-8")
    original = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (meta,wild)}
    assert migrate_legacy(tmp_path)["mode"] == "dry_run"
    assert conversations.read("session_123") is None
    migrate_legacy(tmp_path, apply=True)
    migrate_legacy(tmp_path, apply=True)
    assert conversations.owner("session_123") == (True,None)
    assert len(conversations.read("session_123")["messages"]) == 1
    assert conversations.read("session_123")["created_at"] == 100
    assert len(blueprint_repository.list(None)) == 1
    assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in original} == original
    assert (tmp_path/"scenes").is_dir()
