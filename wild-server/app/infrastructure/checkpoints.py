"""检查手工导入的 LangGraph 表，运行时只读验证，不执行 DDL。"""
from langgraph.checkpoint.mysql.base import MIGRATIONS
from sqlalchemy import inspect, text

from .database import database


def check_schema():
    required = {"checkpoint_migrations", "checkpoints", "checkpoint_blobs", "checkpoint_writes"}
    if required - set(inspect(database.engine).get_table_names()):
        raise RuntimeError("检查点表未初始化，请先在目标 MySQL 手动导入 db/schema.sql")
    with database.engine.connect() as conn:
        version = conn.execute(text("SELECT MAX(v) FROM checkpoint_migrations")).scalar()
        if version != len(MIGRATIONS) - 1:
            raise RuntimeError("检查点表版本与代码不一致，请由数据库管理员执行匹配版本的 SQL")
