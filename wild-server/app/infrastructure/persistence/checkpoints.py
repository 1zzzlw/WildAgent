"""LangGraph 检查点兼容适配与手工建表校验，运行时不执行 DDL。"""
from hashlib import md5

from asyncmy.cursors import DictCursor as AsyncDictCursor
from langgraph.checkpoint.mysql.asyncmy import AsyncMySaver
from langgraph.checkpoint.mysql.base import MIGRATIONS
from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
from pymysql.cursors import DictCursor
from sqlalchemy import inspect, text

from app.infrastructure.persistence.database import database


_NAMED_NAMESPACE_HASH = "UNHEX(MD5(%(checkpoint_ns)s))"
_POSITIONAL_NAMESPACE_HASH = "UNHEX(MD5(%s))"


def _namespace_hash(namespace: str) -> bytes:
    # 保留已有 BINARY(16) 索引；这是命名空间标识，不用于密码或安全校验。
    return md5(namespace.encode("utf-8"), usedforsecurity=False).digest()


def _bind_namespace_hashes(query, args):
    """绑定依赖库的命名空间摘要，兼容不再内置 MD5() 的 MySQL 9.6+。"""
    if not isinstance(query, str) or args is None:
        return query, args
    if _NAMED_NAMESPACE_HASH in query:
        values = {**args, "checkpoint_ns_hash": _namespace_hash(args["checkpoint_ns"])}
        return query.replace(_NAMED_NAMESPACE_HASH, "%(checkpoint_ns_hash)s"), values
    if _POSITIONAL_NAMESPACE_HASH in query:
        values = list(args)
        index = 0
        for prefix in query.split(_POSITIONAL_NAMESPACE_HASH)[:-1]:
            index += prefix.count("%s")
            values[index] = _namespace_hash(values[index])
            index += 1
        return query.replace(_POSITIONAL_NAMESPACE_HASH, "%s"), tuple(values)
    return query, args


def _bind_many_namespace_hashes(query, args):
    prepared = [_bind_namespace_hashes(query, values) for values in (args or [])]
    return (prepared[0][0], [values for _, values in prepared]) if prepared else (query, [])


class _AsyncCheckpointCursor(AsyncDictCursor):
    async def execute(self, query, args=None):
        return await super().execute(*_bind_namespace_hashes(query, args))

    async def executemany(self, query, args):
        return await super().executemany(*_bind_many_namespace_hashes(query, args))


class _CheckpointCursor(DictCursor):
    def execute(self, query, args=None):
        return super().execute(*_bind_namespace_hashes(query, args))

    def executemany(self, query, args):
        return super().executemany(*_bind_many_namespace_hashes(query, args))


class AsyncMySQLCheckpointSaver(AsyncMySaver):
    """读、列举、单条及批量写入共用摘要适配，复用上游事务和序列化。"""

    @staticmethod
    def _get_cursor_from_connection(conn):
        return conn.cursor(_AsyncCheckpointCursor)


class MySQLCheckpointSaver(PyMySQLSaver):
    """磁盘检查点迁移使用相同索引与兼容逻辑。"""

    @staticmethod
    def _get_cursor_from_connection(conn):
        return conn.cursor(_CheckpointCursor)


def check_schema():
    required = {"checkpoint_migrations", "checkpoints", "checkpoint_blobs", "checkpoint_writes"}
    if required - set(inspect(database.engine).get_table_names()):
        raise RuntimeError("检查点表未初始化，请先在目标 MySQL 手动导入 db/schema.sql")
    with database.engine.connect() as conn:
        version = conn.execute(text("SELECT MAX(v) FROM checkpoint_migrations")).scalar()
        if version != len(MIGRATIONS) - 1:
            raise RuntimeError("检查点表版本与代码不一致，请由数据库管理员执行匹配版本的 SQL")
