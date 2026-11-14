"""默认离线仓储回归；设置 WILD_TEST_MYSQL_PORT / WILD_TEST_REDIS_PORT 才连接隔离服务。"""
import os
from pathlib import Path
import sys
from uuid import uuid4

os.environ.setdefault("SystemRoot", r"C:\Windows")
os.environ.setdefault("WINDIR", r"C:\Windows")
os.environ.setdefault("USERNAME", "Administrator")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import fakeredis
import fakeredis.aioredis
import pytest
from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL

from app.infrastructure.cache import cache
from app.infrastructure.database import database
from app.infrastructure.schema import metadata
from config import MySQLConfig, RedisConfig, config


@pytest.fixture
def storage(monkeypatch, tmp_path):
    mysql_port = os.getenv("WILD_TEST_MYSQL_PORT")
    database_name = "wild_test_" + uuid4().hex
    admin = None
    if mysql_port:
        # 只允许显式指定的隔离实例；绝不使用 .env 中的业务连接。
        url = URL.create("mysql+pymysql", username="root", password="", host="127.0.0.1",
                         port=int(mysql_port), query={"charset": "utf8mb4"})
        admin = create_engine(url)
        with admin.begin() as conn:
            conn.execute(text(f"CREATE DATABASE `{database_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin"))
        engine = create_engine(url.set(database=database_name), pool_pre_ping=True)
        monkeypatch.setattr(config, "mysql", MySQLConfig(port=int(mysql_port), database=database_name, username="root"))
    else:
        engine = create_engine(f"sqlite:///{tmp_path / 'storage.sqlite3'}", connect_args={"check_same_thread": False})
        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")
    if mysql_port:
        sql = (Path(__file__).resolve().parents[2] / "db/schema.sql").read_text(encoding="utf-8")
        with engine.begin() as conn:
            for statement in sql.split(";"):
                if statement.strip():
                    conn.exec_driver_sql(statement)
    else:
        metadata.create_all(engine)
    monkeypatch.setattr(database, "_engine", engine)
    prefix = "wild-test:" + uuid4().hex + ":"
    redis_port = os.getenv("WILD_TEST_REDIS_PORT")
    monkeypatch.setattr(config, "redis", RedisConfig(port=int(redis_port or 6379), key_prefix=prefix))
    if redis_port:
        client = Redis(host="127.0.0.1", port=int(redis_port), decode_responses=True)
        async_client = AsyncRedis(host="127.0.0.1", port=int(redis_port), decode_responses=True)
    else:
        server = fakeredis.FakeServer()
        client = fakeredis.FakeRedis(server=server, decode_responses=True)
        async_client = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    monkeypatch.setattr(cache, "_client", client)
    monkeypatch.setattr(cache, "_async_client", async_client)
    yield engine
    keys = list(client.scan_iter(prefix + "*"))
    if keys:
        client.delete(*keys)
    client.close()
    engine.dispose()
    if admin is not None:
        # 数据库名由本夹具创建，只删除本轮隔离数据库。
        with admin.begin() as conn:
            conn.execute(text(f"DROP DATABASE `{database_name}`"))
        admin.dispose()
