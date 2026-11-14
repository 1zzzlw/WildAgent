"""仅供本机浏览器回归：隔离数据库、邮件替身，绝不连接 .env 的业务存储。"""
import os
os.environ.setdefault("SystemRoot", r"C:\Windows")
os.environ.setdefault("WINDIR", r"C:\Windows")
os.environ.setdefault("USERNAME", "Administrator")
os.environ["RAG__ENABLED"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["CHAT__API_KEY"] = "browser-test-not-a-real-key"
os.environ["CHAT__BASE_URL"] = "http://127.0.0.1:9/v1"
os.environ["CHAT__PROVIDER"] = "openai"
os.environ["EMBEDDING__API_KEY"] = ""
for proxy in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(proxy, None)

import importlib
from pathlib import Path
import re
import sys
import tempfile
from uuid import uuid4

import uvicorn
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
temporary = tempfile.TemporaryDirectory(prefix="wild-editor-smoke-")
storage = Path(temporary.name)
database_name = "wild_browser_" + uuid4().hex
mysql_port = os.getenv("WILD_TEST_MYSQL_PORT")
admin = None
if mysql_port:
    os.environ.update(MYSQL__HOST="127.0.0.1", MYSQL__PORT=mysql_port, MYSQL__USERNAME="root",
                      MYSQL__PASSWORD="", MYSQL__DATABASE=database_name)
from config import SMTPConfig, RedisConfig, config
from app.infrastructure.database import database
from app.infrastructure.cache import cache
from app.infrastructure.schema import metadata, blueprints

if mysql_port:
    url = URL.create("mysql+pymysql", host="127.0.0.1", port=int(mysql_port), username="root", password="",
                     query={"charset":"utf8mb4"})
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f"CREATE DATABASE `{database_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin"))
    database._engine = create_engine(url.set(database=database_name), pool_pre_ping=True)
    with database.engine.begin() as conn:
        for statement in (ROOT/"db/schema.sql").read_text(encoding="utf-8").split(";"):
            if statement.strip(): conn.exec_driver_sql(statement)
else:
    database._engine = create_engine(f"sqlite:///{storage/'storage.sqlite3'}", connect_args={"check_same_thread":False})
    metadata.create_all(database.engine)
    jobs = importlib.import_module("app.services.generation_job_service")
    jobs.generation_job_service = jobs.GenerationJobService(storage/"jobs.sqlite3")

prefix = "wild-browser:" + uuid4().hex + ":"
redis_port = os.getenv("WILD_TEST_REDIS_PORT")
config.redis = RedisConfig(port=int(redis_port or 6379), key_prefix=prefix)
if not redis_port:
    import fakeredis
    import fakeredis.aioredis
    fake_server = fakeredis.FakeServer()
    cache._client = fakeredis.FakeRedis(server=fake_server, decode_responses=True)
    cache._async_client = fakeredis.aioredis.FakeRedis(server=fake_server, decode_responses=True)
    cache.create_async_client = lambda **_: fakeredis.aioredis.FakeRedis(server=fake_server, decode_responses=True)

from app.repositories.accounts import accounts
from app.services import account_service

for username in ("zlw", "lxw", "mf"):
    accounts.create(username, username + "@example.com", account_service.hash_password("123456"))
with database.engine.begin() as conn:
    conn.execute(text("UPDATE users SET identity = 2 WHERE email = 'zlw@example.com'"))

sent_mail = []
class SMTP:
    def __init__(self, *args, **kwargs): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def login(self, *args): pass
    def send_message(self, message): sent_mail.append(message)
config.smtp = SMTPConfig(host="test.example.com", from_address="wild@example.com")
account_service.smtplib.SMTP_SSL = SMTP

from main import app


@app.get("/api/editor-smoke-storage")
def storage_snapshot():
    with database.engine.connect() as conn:
        return {row.filename: row.blueprint_json for row in conn.execute(select(blueprints.c.filename,blueprints.c.blueprint_json))}


@app.get("/api/editor-smoke-mail")
def mail_snapshot():
    return {"count":len(sent_mail), "code": re.search(r"[0-9]{6}",sent_mail[-1].get_body(preferencelist=("plain",)).get_content()).group() if sent_mail else None}


@app.get("/api/editor-smoke-info")
def smoke_info():
    return {"database": database.engine.dialect.name, "redis": "redis" if redis_port else "fakeredis", "smtp": "test transport"}


if __name__ == "__main__":
    try:
        uvicorn.run(app, host="127.0.0.1", port=18080, log_level="warning")
    finally:
        if admin is not None:
            with admin.begin() as conn:
                conn.execute(text(f"DROP DATABASE `{database_name}`"))
            admin.dispose()
        temporary.cleanup()
