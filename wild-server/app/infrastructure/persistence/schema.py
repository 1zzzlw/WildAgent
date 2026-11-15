"""业务表数据契约，初始化 DDL 位于 db/schema.sql。时间统一为 Unix 毫秒。"""
from sqlalchemy import (JSON, BigInteger, CheckConstraint, Column, ForeignKey, Index, Integer,
                        MetaData, SmallInteger, String, Table, Text, text)
from sqlalchemy.dialects.mysql import LONGTEXT

metadata = MetaData()
options = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_bin"}
users = Table("users", metadata,
    Column("id", String(36), primary_key=True),
    Column("username", String(64), nullable=False),
    Column("email", String(254), nullable=False, unique=True),
    Column("identity", SmallInteger, nullable=False, default=1, server_default=text("1")),
    Column("password_hash", String(256), nullable=False),
    Column("status", String(16), nullable=False, default="active"),
    Column("created_at", BigInteger, nullable=False),
    CheckConstraint("identity IN (1, 2)", name="ck_users_identity"), **options)
sessions = Table("conversation_sessions", metadata,
    Column("session_id", String(128), primary_key=True),
    Column("owner_id", String(36), ForeignKey("users.id")),
    Column("metadata_json", JSON, nullable=False),
    Column("created_at", BigInteger, nullable=False),
    Column("updated_at", BigInteger, nullable=False), **options)
Index("ix_sessions_owner_updated", sessions.c.owner_id, sessions.c.updated_at)
messages = Table("conversation_messages", metadata,
    Column("session_id", String(128), ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"), primary_key=True),
    Column("message_id", String(128), primary_key=True),
    Column("position", Integer, nullable=False),
    Column("payload_json", JSON, nullable=False), **options)
turns = Table("agent_turns", metadata,
    Column("session_id", String(128), ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"), primary_key=True),
    Column("request_id", String(128), primary_key=True),
    Column("position", Integer, nullable=False),
    Column("payload_json", JSON, nullable=False), **options)
blueprints = Table("blueprints", metadata,
    Column("filename", String(255), primary_key=True),
    Column("session_id", String(128), ForeignKey("conversation_sessions.session_id", ondelete="CASCADE")),
    Column("owner_id", String(36), ForeignKey("users.id")),
    Column("name", String(255), nullable=False),
    Column("elements_count", Integer, nullable=False),
    Column("components_count", Integer, nullable=False),
    Column("blueprint_json", JSON, nullable=False),
    Column("created_at", BigInteger, nullable=False),
    Column("updated_at", BigInteger, nullable=False), **options)
Index("ix_blueprints_session_updated", blueprints.c.session_id, blueprints.c.updated_at)
Index("ix_blueprints_owner_updated", blueprints.c.owner_id, blueprints.c.updated_at)
designs = Table("design_documents", metadata,
    Column("session_id", String(128), ForeignKey("conversation_sessions.session_id", ondelete="CASCADE"), primary_key=True),
    Column("revision", Integer, primary_key=True),
    Column("document_json", JSON, nullable=False),
    Column("resolved_json", JSON, nullable=False),
    Column("updated_at", BigInteger, nullable=False), **options)
jobs = Table("generation_jobs", metadata,
    Column("request_id", String(128), primary_key=True),
    Column("session_id", String(128), nullable=False),
    Column("payload_json", Text().with_variant(LONGTEXT(), "mysql"), nullable=False),
    Column("status", String(24), nullable=False),
    Column("last_event_seq", Integer, nullable=False, default=0),
    Column("error", Text),
    Column("created_at", BigInteger, nullable=False),
    Column("updated_at", BigInteger, nullable=False), **options)
Index("idx_generation_jobs_session_status", jobs.c.session_id, jobs.c.status, jobs.c.updated_at)
events = Table("generation_events", metadata,
    Column("request_id", String(128), ForeignKey("generation_jobs.request_id", ondelete="CASCADE"), primary_key=True),
    Column("seq", Integer, primary_key=True),
    Column("payload_json", Text().with_variant(LONGTEXT(), "mysql"), nullable=False),
    Column("created_at", BigInteger, nullable=False), **options)
