"""MySQL 连接池；测试可注入隔离引擎，生产不回退到本地文件。"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, Engine

from config import config


class Database:
    def __init__(self, engine: Engine | None = None):
        self._engine = engine

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            cfg = config.mysql
            url = URL.create("mysql+pymysql", username=cfg.username,
                             password=cfg.password.get_secret_value(), host=cfg.host,
                             port=cfg.port, database=cfg.database, query={"charset": "utf8mb4"})
            self._engine = create_engine(url, pool_size=cfg.pool_size, max_overflow=cfg.pool_size,
                                        pool_pre_ping=True, pool_recycle=1800,
                                        connect_args={"connect_timeout": cfg.connect_timeout},
                                        hide_parameters=True)
        return self._engine

    def check(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def initialize(self) -> None:
        from app.infrastructure.persistence.schema import metadata
        self.check()
        inspector = inspect(self.engine)
        missing = set(metadata.tables) - set(inspector.get_table_names())
        if missing == {"audit_logs"}:
            raise RuntimeError("请先在现有数据库执行 db/migrations/20261116_admin_management.sql，再启动服务")
        if missing:
            raise RuntimeError("业务数据表未初始化，请先在目标 MySQL 手动导入 db/schema.sql")
        for name, table in metadata.tables.items():
            actual = {column["name"] for column in inspector.get_columns(name)}
            missing_columns = set(table.c.keys()) - actual
            if name == "users" and missing_columns & {
                "operations_daily_limit", "ai_daily_limit", "ai_remaining", "ai_used", "usage_reset_at"
            }:
                raise RuntimeError("每日额度表结构未升级，请先执行 db/migrations/20261116_daily_usage.sql，再启动服务")
            if missing_columns:
                raise RuntimeError("业务表字段与代码不一致；已有数据库请执行 db/migrations/20261116_admin_management.sql，其他版本对照 db/schema.sql 更新")

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None


database = Database()
