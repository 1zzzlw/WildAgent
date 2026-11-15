"""检查点真实读写入口的 SQL 绑定回归，不连接数据库或调用模型。"""
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from hashlib import md5
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.base import WRITES_IDX_MAP, empty_checkpoint

from app.infrastructure.persistence.checkpoints import AsyncDictCursor
from app.infrastructure.persistence.checkpoints import AsyncMySQLCheckpointSaver
from app.infrastructure.persistence.checkpoints import DictCursor
from app.infrastructure.persistence.checkpoints import MySQLCheckpointSaver
from app.infrastructure.persistence.checkpoints import _AsyncCheckpointCursor
from app.infrastructure.persistence.checkpoints import _CheckpointCursor


@pytest.mark.parametrize("namespace", ["", "abc", "建筑/楼层:1"])
def test_async_saver_binds_legacy_keys_for_reads_blobs_and_both_write_modes(monkeypatch, namespace):
    async def scenario():
        statements = []

        async def execute(_cursor, query, args=None):
            statements.append((query, [args]))
            return 0

        async def executemany(_cursor, query, args):
            statements.append((query, args))
            return len(args)

        async def fetchone(_cursor):
            return None

        async def fetchall(_cursor):
            return []

        monkeypatch.setattr(AsyncDictCursor, "execute", execute)
        monkeypatch.setattr(AsyncDictCursor, "executemany", executemany)
        monkeypatch.setattr(AsyncDictCursor, "fetchone", fetchone)
        monkeypatch.setattr(AsyncDictCursor, "fetchall", fetchall)
        cursor = _AsyncCheckpointCursor(SimpleNamespace(loop=asyncio.get_running_loop()))
        conn = SimpleNamespace(cursor=lambda cursor_type: cursor_type(cursor.connection))
        saver = AsyncMySQLCheckpointSaver(conn)
        assert isinstance(saver._get_cursor_from_connection(conn), _AsyncCheckpointCursor)

        @asynccontextmanager
        async def open_cursor(**_options):
            yield cursor

        monkeypatch.setattr(saver, "_cursor", open_cursor)
        cfg = {"configurable": {"thread_id": "generation:compat", "checkpoint_ns": namespace}}
        original = deepcopy(cfg)
        assert await saver.aget_tuple(cfg) is None
        assert await saver.aget_tuple({"configurable": {**cfg["configurable"], "checkpoint_id": "previous"}}) is None
        assert [item async for item in saver.alist(cfg)] == []
        checkpoint = empty_checkpoint()
        checkpoint["channel_values"] = {"plain": 1, "shape": {"text": "UNHEX(MD5(%s))"}}
        checkpoint["channel_versions"] = {"plain": "1", "shape": "1"}
        saved = await saver.aput(cfg, checkpoint, {}, checkpoint["channel_versions"])
        await saver.aput_writes(saved, [("shape", {"value": "保留原始写入"})], "task")
        await saver.aput_writes(saved, [(next(iter(WRITES_IDX_MAP)), "failure")], "task")
        await saver.adelete_thread("generation:compat")
        assert cfg == original

        expected = md5(namespace.encode("utf-8"), usedforsecurity=False).digest()
        for query, rows in statements:
            assert "MD5(" not in query
            if "checkpoint_ns_hash" not in query:
                continue
            for args in rows:
                if isinstance(args, dict):
                    assert args["checkpoint_ns"] == namespace
                    assert args["checkpoint_ns_hash"] == expected
                else:
                    assert args[1] == namespace
                    assert args[2] == expected
        assert any("checkpoint_blobs" in query and "INSERT" in query for query, _ in statements)
        assert any("INSERT IGNORE INTO checkpoint_writes" in query for query, _ in statements)
        assert any("ON DUPLICATE KEY UPDATE" in query and "checkpoint_writes" in query for query, _ in statements)

    asyncio.run(scenario())


def test_sync_migration_cursor_uses_same_keys_without_mutating_parameters(monkeypatch):
    statements = []
    monkeypatch.setattr(DictCursor, "execute", lambda _cursor, query, args=None: statements.append((query, args)))

    def executemany(cursor, query, args):
        if not args:
            return None
        statements.append((query, args))
        # 驱动的批处理可能继续调用 execute，已经绑定的摘要不能被再次计算。
        for values in args:
            cursor.execute(query, values)

    monkeypatch.setattr(DictCursor, "executemany", executemany)
    cursor = MySQLCheckpointSaver._get_cursor_from_connection(SimpleNamespace(cursor=lambda cursor_type: cursor_type(None)))
    assert isinstance(cursor, _CheckpointCursor)
    named = {"thread_id": "generation:compat", "checkpoint_ns": "abc"}
    cursor.execute("SELECT * FROM checkpoints WHERE checkpoint_ns_hash = UNHEX(MD5(%(checkpoint_ns)s))", named)
    rows = [("generation:compat", "abc", "abc", "id", None, "{}", "{}")]
    cursor.executemany(MySQLCheckpointSaver.UPSERT_CHECKPOINTS_SQL, rows)
    assert named == {"thread_id": "generation:compat", "checkpoint_ns": "abc"}
    assert rows[0][2] == "abc"
    expected = bytes.fromhex("900150983cd24fb0d6963f7d28e17f72")
    assert statements[0][1]["checkpoint_ns_hash"] == expected
    assert statements[1][1][0][2] == expected
    assert statements[2][1][2] == expected
    assert all("MD5(" not in query for query, _ in statements)
    count = len(statements)
    assert cursor.executemany(MySQLCheckpointSaver.UPSERT_CHECKPOINTS_SQL, []) is None
    assert len(statements) == count
    cursor.execute("DELETE FROM checkpoints WHERE thread_id = %s", ("generation:compat",))
    assert statements[-1] == ("DELETE FROM checkpoints WHERE thread_id = %s", ("generation:compat",))
