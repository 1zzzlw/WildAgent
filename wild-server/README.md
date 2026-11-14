# WildAgent Server

后端提供 FastAPI REST/WebSocket、快速 Agent、LangGraph 精密编排、RAG 与确定性 Blueprint 校验。

正式架构和配置说明见 [`../docs/`](../docs/README.md)，不要在本目录新增阶段总结或修复报告；这类历史材料统一放到 `../docs-dev/wild-server/`。

首次启动前，在远程 MySQL 8.0.19+ 创建并选中数据库（例如 `wild_agent`），手动导入完整建表脚本 [`db/schema.sql`](db/schema.sql)，然后填写 `.env` 的 `MYSQL__*`、`REDIS__*`、`SMTP__*`。启动只检查表和版本，不自动建表或修改结构。

```powershell
uv sync
uv run uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

MySQL 持久化账号、会话元数据、聊天消息、执行轮次、蓝图、设计版本、生成任务与检查点；Redis 管理登录会话、邮箱验证码、在线连接、任务租约和跨实例通知。图片、纹理、Chroma 及诊断日志继续使用各自的存储模块。代码按 `infrastructure → repositories → services → api` 分层。

邮箱作为登录账号，用户名作为展示名。`users.identity` 中 `1` 表示普通用户，`2` 表示管理员，注册固定写入 `1`；当前两种身份使用相同功能，尚未划分身份权限。需要标记管理员时，手动执行：

```sql
UPDATE users SET identity = 2 WHERE email = 'admin@example.com';
```

新建资料关联账号，原磁盘资料迁为共享历史。需要迁移旧数据时，先停止旧后端写入并备份，再运行独立的数据迁移工具；该工具不执行建表 SQL，默认只检查，`--apply` 才写入数据，源文件保持不变：

```powershell
uv run python scripts/migrate_legacy_storage.py --source storage
uv run python scripts/migrate_legacy_storage.py --source storage --apply
```

容器连接远程 MySQL / Redis 时，HOST 填实际远程地址；连接宿主机时可用 `host.docker.internal`。`.env.example` 只保留示例值，实际密码和邮箱授权码填写到 `.env`。
