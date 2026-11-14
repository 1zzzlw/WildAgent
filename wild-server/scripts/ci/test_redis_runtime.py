"""真实 Redis/MySQL 或离线替身下的连接协调与断线恢复回归。"""
import asyncio
import json
import os
from pathlib import Path
import time
from typing import TypedDict

from langgraph.graph import StateGraph, START, END
import pytest

from app.extensions.presence.service import WebSocketConnectionRegistry
from app.infrastructure.cache import cache
from app.infrastructure.realtime import RealtimeBus
from app.repositories.conversations import conversations
from app.services.generation_job_service import GenerationJobService


class Socket:
    def __init__(self): self.events = []
    async def send_json(self, payload): self.events.append(payload)


async def eventually(predicate, timeout=5):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if predicate(): return
        await asyncio.sleep(.02)
    raise AssertionError("等待跨实例状态同步超时")


def test_global_presence_rename_disconnect_and_expired_connections(storage):
    async def run():
        a = RealtimeBus(client=cache.async_client)
        b = RealtimeBus(client=cache.async_client)
        first = WebSocketConnectionRegistry(bus=a)
        second = WebSocketConnectionRegistry(bus=b)
        ws1, ws2 = Socket(), Socket()
        try:
            await first.connect(ws1, client_ip="127.0.0.1", region="测试", display_name="甲")
            await second.connect(ws2, client_ip="127.0.0.1", region="测试", display_name="乙")
            await eventually(lambda: ws1.events[-1]["online_count"] == 2 and ws2.events[-1]["online_count"] == 2)
            await second.update_display_name(ws2, "新名称")
            await eventually(lambda: any(v["display_name"] == "新名称" for v in ws1.events[-1]["clients"]))
            first._last_touch[ws1] -= 30
            await first.touch(ws1)
            identity = first._connections[ws1]
            assert await cache.async_client.ttl(cache.key("presence:client:" + identity)) > 100
            await first.disconnect(ws1)
            await eventually(lambda: ws2.events[-1]["online_count"] == 1)
            await cache.async_client.set(cache.key("presence:client:dead"), json.dumps({"id":"dead","connected_at":0}), ex=120)
            await cache.async_client.zadd(cache.key("presence:connections"), {"dead": time.time()-1})
            assert (await second._snapshot())["online_count"] == 1
            assert await cache.async_client.zscore(cache.key("presence:connections"), "dead") is None
        finally:
            await first.shutdown()
            await second.shutdown()
            await a.close()
            await b.close()
            await cache.aclose()
    asyncio.run(run())


def mysql_only(storage):
    if storage.dialect.name != "mysql" or not os.getenv("WILD_TEST_REDIS_PORT"):
        pytest.skip("需要显式指定隔离 MySQL 和 Redis 端口")


def test_two_workers_share_single_job_and_receive_persisted_events(storage):
    mysql_only(storage)
    async def run():
        a, b = RealtimeBus(), RealtimeBus()
        first, second = GenerationJobService(bus=a), GenerationJobService(bus=b)
        calls = []
        gate = asyncio.Event()
        async def runner(sink, payload, resume):
            calls.append(payload["request_id"])
            await sink.send_json({"type":"agent_step", "request_id":payload["request_id"], "session_id":"session_1"})
            await gate.wait()
            await sink.send_json({"type":"agent_reply", "content":"完成", "request_id":payload["request_id"], "session_id":"session_1"})
        ws1, ws2 = Socket(), Socket()
        try:
            await first.startup(runner)
            await second.startup(runner)
            job, created = await first.start_job({"request_id":"req_one", "session_id":"session_1"}, ws1)
            assert created
            await eventually(lambda: len(calls) == 1)
            duplicate, created = await second.start_job({"request_id":"req_two", "session_id":"session_1"}, ws2)
            assert not created and duplicate.request_id == job.request_id
            await second.resume_or_replay(ws2, request_id=job.request_id, session_id="session_1")
            await asyncio.sleep(.1)
            assert calls == ["req_one"]
            gate.set()
            await eventually(lambda: any(e["type"] == "agent_reply" for e in ws2.events))
            assert [e["event_seq"] for e in await second.events_after(job.request_id, 0)] == [1,2]
            assert (await second.get_job(job.request_id)).status == "completed"
            with pytest.raises(ValueError, match="属于"):
                await second.resume_or_replay(Socket(), request_id=job.request_id, session_id="other_session")
        finally:
            await first.shutdown(); await second.shutdown()
            await a.close(); await b.close(); await cache.aclose()
    asyncio.run(run())


def test_remote_stop_cancels_owner_worker(storage):
    mysql_only(storage)
    async def run():
        a, b = RealtimeBus(), RealtimeBus()
        first, second = GenerationJobService(bus=a), GenerationJobService(bus=b)
        running, cancelled = asyncio.Event(), asyncio.Event()
        async def runner(sink, payload, resume):
            running.set()
            try: await asyncio.Event().wait()
            finally: cancelled.set()
        try:
            await first.startup(runner); await second.startup(runner)
            await first.start_job({"request_id":"req_stop", "session_id":"session_2"}, Socket())
            await asyncio.wait_for(running.wait(), 5)
            await second.stop_job(Socket(), request_id="req_stop", session_id="session_2")
            await asyncio.wait_for(cancelled.wait(), 5)
            assert (await first.get_job("req_stop")).status == "stopped"
            assert (await first.events_after("req_stop",0))[-1]["type"] == "generation_stopped"
        finally:
            await first.shutdown(); await second.shutdown()
            await a.close(); await b.close(); await cache.aclose()
    asyncio.run(run())


class State(TypedDict):
    value: int


def test_mysql_checkpoints_reload_after_service_restart(storage):
    mysql_only(storage)
    async def run():
        bus = RealtimeBus()
        first = GenerationJobService(bus=bus)
        second = GenerationJobService(bus=bus)
        graph = StateGraph(State)
        graph.add_node("step", lambda state: {"value":state["value"] + 1})
        graph.add_edge(START,"step"); graph.add_edge("step",END)
        cfg = {"configurable":{"thread_id":"generation:restart"}}
        try:
            await first.initialize()
            assert (await graph.compile(checkpointer=first.checkpointer).ainvoke({"value":4},cfg))["value"] == 5
            await first.shutdown()
            await second.initialize()
            snapshot = await graph.compile(checkpointer=second.checkpointer).aget_state(cfg)
            assert snapshot.values == {"value":5}
            await second.checkpointer.adelete_thread("generation:restart")
            assert (await graph.compile(checkpointer=second.checkpointer).aget_state(cfg)).values == {}
        finally:
            await first.shutdown(); await second.shutdown(); await bus.close(); await cache.aclose()
    asyncio.run(run())


def test_mysql_parallel_message_merges_and_event_sequences(storage):
    mysql_only(storage)
    from concurrent.futures import ThreadPoolExecutor
    from app.repositories.jobs import JobRepository
    conversations.ensure("session_parallel")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda n: conversations.append_messages("session_parallel", [{"id":str(n),"content":str(n)}], None), range(12)))
    assert len(conversations.read("session_parallel")["messages"]) == 12
    jobs = JobRepository()
    jobs.insert("req_parallel", "session_parallel", {})
    with ThreadPoolExecutor(max_workers=4) as pool:
        result = list(pool.map(lambda n: jobs.append("req_parallel", {"type":"agent_step","number":n},None), range(12)))
    assert sorted(result) == list(range(1,13))
    assert len(jobs.events_after("req_parallel",0)) == 12


def test_manual_sql_and_dml_only_checkpoint_account(storage, monkeypatch):
    mysql_only(storage)
    from secrets import token_hex
    from sqlalchemy import text
    from app.infrastructure.schema import metadata
    from config import MySQLConfig, config
    # 本测试夹具刚创建的数据库，只在其中重建业务表，直接回放交付 SQL。
    metadata.drop_all(storage)
    sql = (Path(__file__).resolve().parents[2]/"db/schema.sql").read_text(encoding="utf-8")
    with storage.begin() as conn:
        for statement in sql.split(";"):
            if statement.strip(): conn.exec_driver_sql(statement)
    username = "wild_dml_" + token_hex(5)
    password = token_hex(16)
    cfg = config.mysql
    with storage.begin() as conn:
        conn.execute(text(f"CREATE USER '{username}'@'%' IDENTIFIED BY '{password}'"))
        conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON `{cfg.database}`.* TO '{username}'@'%'") )
    monkeypatch.setattr(config,"mysql",MySQLConfig(port=cfg.port,database=cfg.database,username=username,password=password))
    try:
        test_mysql_checkpoints_reload_after_service_restart(storage)
    finally:
        with storage.begin() as conn:
            conn.execute(text(f"DROP USER '{username}'@'%'") )


def test_sqlite_runtime_history_and_checkpoints_migrate_without_source_changes(storage, tmp_path):
    mysql_only(storage)
    from scripts.migrate_legacy_storage import migrate_legacy
    from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
    from app.repositories.jobs import JobRepository
    from config import config
    import hashlib
    import pymysql
    source = tmp_path/"legacy"
    (source/"sessions").mkdir(parents=True)
    path = source/"sessions/langgraph_checkpoints.sqlite3"
    async def prepare():
        service = GenerationJobService(path)
        try:
            await service.initialize()
            await service._insert_job("req_migrated","session_migrated",{})
            await service.publish_event("req_migrated",{"type":"agent_reply","content":"历史结果"})
            graph = StateGraph(State)
            graph.add_node("step",lambda state:{"value":state["value"]+1})
            graph.add_edge(START,"step"); graph.add_edge("step",END)
            await graph.compile(checkpointer=service.checkpointer).ainvoke({"value":6},
                {"configurable":{"thread_id":"generation:req_migrated"}})
        finally:
            await service.shutdown()
    asyncio.run(prepare())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    result = migrate_legacy(source,apply=True)
    assert result["records_found"]["checkpoints"] >= 2
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    assert JobRepository().get("req_migrated")[3] == "completed"
    assert JobRepository().events_after("req_migrated",0)[0]["content"] == "历史结果"
    cfg = config.mysql
    with pymysql.connect(host=cfg.host,port=cfg.port,user=cfg.username,password=cfg.password.get_secret_value(),
                         database=cfg.database,autocommit=True,charset="utf8mb4") as conn:
        saved = PyMySQLSaver(conn).get_tuple({"configurable":{"thread_id":"generation:req_migrated"}})
        assert saved.checkpoint["channel_values"]["value"] == 7
    migrate_legacy(source,apply=True)
    assert len(JobRepository().events_after("req_migrated",0)) == 1
