-- WildAgent 完整建表 SQL：业务表 + LangGraph 检查点表。
-- 在远程 MySQL 8.0.19+ 中先创建并选中目标数据库（例如 wild_agent），再手动导入。
-- 初始化脚本保留已有数据；已有旧版表请对照字段结构手工更新。
-- users.identity：1 普通用户，2 管理员；当前两种身份功能一致，注册固定为 1。

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS generation_jobs (
	request_id VARCHAR(128) NOT NULL, 
	session_id VARCHAR(128) NOT NULL, 
	payload_json LONGTEXT NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	last_event_seq INTEGER NOT NULL, 
	error TEXT, 
	created_at BIGINT NOT NULL, 
	updated_at BIGINT NOT NULL, 
	PRIMARY KEY (request_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE INDEX idx_generation_jobs_session_status ON generation_jobs (session_id, status, updated_at);

CREATE TABLE IF NOT EXISTS users (
	id VARCHAR(36) NOT NULL, 
	username VARCHAR(64) NOT NULL, 
	email VARCHAR(254) NOT NULL, 
	identity SMALLINT NOT NULL DEFAULT 1, 
	password_hash VARCHAR(256) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	created_at BIGINT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_users_identity CHECK (identity IN (1, 2)), 
	UNIQUE (email)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS conversation_sessions (
	session_id VARCHAR(128) NOT NULL, 
	owner_id VARCHAR(36), 
	metadata_json JSON NOT NULL, 
	created_at BIGINT NOT NULL, 
	updated_at BIGINT NOT NULL, 
	PRIMARY KEY (session_id), 
	FOREIGN KEY(owner_id) REFERENCES users (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE INDEX ix_sessions_owner_updated ON conversation_sessions (owner_id, updated_at);

CREATE TABLE IF NOT EXISTS generation_events (
	request_id VARCHAR(128) NOT NULL, 
	seq INTEGER NOT NULL, 
	payload_json LONGTEXT NOT NULL, 
	created_at BIGINT NOT NULL, 
	PRIMARY KEY (request_id, seq), 
	FOREIGN KEY(request_id) REFERENCES generation_jobs (request_id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS agent_turns (
	session_id VARCHAR(128) NOT NULL, 
	request_id VARCHAR(128) NOT NULL, 
	position INTEGER NOT NULL, 
	payload_json JSON NOT NULL, 
	PRIMARY KEY (session_id, request_id), 
	FOREIGN KEY(session_id) REFERENCES conversation_sessions (session_id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS blueprints (
	filename VARCHAR(255) NOT NULL, 
	session_id VARCHAR(128), 
	owner_id VARCHAR(36), 
	name VARCHAR(255) NOT NULL, 
	elements_count INTEGER NOT NULL, 
	components_count INTEGER NOT NULL, 
	blueprint_json JSON NOT NULL, 
	created_at BIGINT NOT NULL, 
	updated_at BIGINT NOT NULL, 
	PRIMARY KEY (filename), 
	FOREIGN KEY(session_id) REFERENCES conversation_sessions (session_id) ON DELETE CASCADE, 
	FOREIGN KEY(owner_id) REFERENCES users (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE INDEX ix_blueprints_owner_updated ON blueprints (owner_id, updated_at);

CREATE INDEX ix_blueprints_session_updated ON blueprints (session_id, updated_at);

CREATE TABLE IF NOT EXISTS conversation_messages (
	session_id VARCHAR(128) NOT NULL, 
	message_id VARCHAR(128) NOT NULL, 
	position INTEGER NOT NULL, 
	payload_json JSON NOT NULL, 
	PRIMARY KEY (session_id, message_id), 
	FOREIGN KEY(session_id) REFERENCES conversation_sessions (session_id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS design_documents (
	session_id VARCHAR(128) NOT NULL, 
	revision INTEGER NOT NULL, 
	document_json JSON NOT NULL, 
	resolved_json JSON NOT NULL, 
	updated_at BIGINT NOT NULL, 
	PRIMARY KEY (session_id, revision), 
	FOREIGN KEY(session_id) REFERENCES conversation_sessions (session_id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

-- 对应 langgraph-checkpoint-mysql 3.0.0 的最终表结构，迁移版本 21。
-- 来源：https://github.com/tjni/langgraph-checkpoint-mysql
-- 后端运行时只检查版本，不自动建表或执行 ALTER。


CREATE TABLE IF NOT EXISTS checkpoint_migrations (
    v INTEGER PRIMARY KEY
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id VARCHAR(150) NOT NULL,
    checkpoint_ns VARCHAR(2000) NOT NULL DEFAULT '',
    checkpoint_ns_hash BINARY(16) NOT NULL,
    checkpoint_id VARCHAR(150) NOT NULL,
    parent_checkpoint_id VARCHAR(150),
    type VARCHAR(150),
    checkpoint JSON NOT NULL,
    metadata JSON NOT NULL DEFAULT ('{}'),
    PRIMARY KEY (thread_id, checkpoint_ns_hash, checkpoint_id),
    KEY checkpoints_thread_id_idx (thread_id),
    KEY checkpoints_checkpoint_id_idx (checkpoint_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS checkpoint_blobs (
    thread_id VARCHAR(150) NOT NULL,
    checkpoint_ns VARCHAR(2000) NOT NULL DEFAULT '',
    checkpoint_ns_hash BINARY(16) NOT NULL,
    channel VARCHAR(150) NOT NULL,
    version VARCHAR(150) NOT NULL,
    type VARCHAR(150) NOT NULL,
    `blob` LONGBLOB,
    PRIMARY KEY (thread_id, checkpoint_ns_hash, channel, version),
    KEY checkpoint_blobs_thread_id_idx (thread_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id VARCHAR(150) NOT NULL,
    checkpoint_ns VARCHAR(2000) NOT NULL DEFAULT '',
    checkpoint_ns_hash BINARY(16) NOT NULL,
    checkpoint_id VARCHAR(150) NOT NULL,
    task_id VARCHAR(150) NOT NULL,
    idx INTEGER NOT NULL,
    channel VARCHAR(150) NOT NULL,
    type VARCHAR(150),
    `blob` LONGBLOB NOT NULL,
    task_path VARCHAR(2000) NOT NULL DEFAULT '',
    PRIMARY KEY (thread_id, checkpoint_ns_hash, checkpoint_id, task_id, idx),
    KEY checkpoint_writes_thread_id_idx (thread_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

INSERT IGNORE INTO checkpoint_migrations (v) VALUES
    (0),(1),(2),(3),(4),(5),(6),(7),(8),(9),(10),
    (11),(12),(13),(14),(15),(16),(17),(18),(19),(20),(21);
