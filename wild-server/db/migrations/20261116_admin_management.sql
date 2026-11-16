-- 在现有 WildAgent 数据库中执行一次。保留账号、蓝图、会话和检查点数据。
-- 新数据库直接使用 db/schema.sql，不需要执行本文件。
ALTER TABLE users
    ADD COLUMN operations_remaining INTEGER NOT NULL DEFAULT 1000,
    ADD COLUMN modifications_remaining INTEGER NOT NULL DEFAULT 200,
    ADD COLUMN generations_remaining INTEGER NOT NULL DEFAULT 20,
    ADD COLUMN operations_used INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN modifications_used INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN generations_used INTEGER NOT NULL DEFAULT 0;

ALTER TABLE blueprints
    ADD COLUMN locked BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN locked_at BIGINT NULL,
    ADD COLUMN locked_by VARCHAR(36) NULL;

CREATE TABLE IF NOT EXISTS audit_logs (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    actor_id VARCHAR(36) NOT NULL,
    actor_name VARCHAR(64) NOT NULL,
    action VARCHAR(64) NOT NULL,
    resource VARCHAR(255) NOT NULL DEFAULT '',
    session_id VARCHAR(128) NULL,
    request_id VARCHAR(128) NULL,
    details JSON NOT NULL,
    created_at BIGINT NOT NULL,
    INDEX ix_audit_actor_created (actor_id, created_at),
    INDEX ix_audit_action_created (action, created_at)
) ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;
