# WildAgent Server

后端提供 FastAPI REST/WebSocket、LangGraph 编排、RAG 与确定性 Blueprint 校验，采用分层单体结构。

当前后端目录与启动配置见本文，Agent 职责说明见 [`agent/README.md`](agent/README.md)。阶段总结与修复报告沿用项目历史资料目录，不放进业务源码。

首次启动前，在远程 MySQL 8.0.19+ 创建并选中数据库（例如 `wild_agent`），手动导入完整建表脚本 [`db/schema.sql`](db/schema.sql)，然后填写 `.env` 的 `MYSQL__*`、`REDIS__*`、`SMTP__*`。启动只检查表和版本，不自动建表或修改结构。

```powershell
uv sync
uv run uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

MySQL 持久化账号、会话元数据、聊天消息、执行轮次、蓝图、设计版本、生成任务与检查点；Redis 管理登录会话、邮箱验证码、在线连接、任务租约和跨实例通知。图片、纹理、物品目录、Chroma 及诊断日志继续使用各自的存储模块。

```text
wild-server/
├── main.py                   # 统一装配入口，监听 8000
├── config.py                 # 根目录 .env 的编辑器配置
├── app/                      # 编辑器 API、账号、会话、蓝图与存储
├── agent/                    # LangGraph、工作流、提示词、模型和检索
├── integration/              # WebSocket 协议、持久任务及结果交付
├── common/                   # 资源路径、事件信封及配置文件工具
├── db/schema.sql             # MySQL 建表脚本
├── scripts/                  # 数据迁移和运维命令
└── storage/                  # 知识库、纹理和本地资源
```

`app` 和 `agent` 各自读取根目录 `.env` 中的配置，基础文件工具由 `common` 提供。根目录 `main.py` 负责启动和装配，由 `integration` 将工作流接入编辑器的权限、任务和存储。前端通过 8000 上的 `/ws/agent` 发送对话，REST 接口也由同一个入口提供。

生成入口为 `integration/generation/runner.py`，负责请求预检、执行或恢复 `agent/graph.py`、转换流事件和交付结果。`jobs.py` 管理持久化任务、租约与事件补发。模型和知识加载器在启动时由 `agent/llm/resources.py` 初始化。知识文档从 `storage/knowledge_base/` 加载。

Studio 入口和维护脚本可直接引用 `agent`。用 `uv run python -m agent.script.export_design_schema` 导出图纸 Schema。邮件模板和内嵌图标随 `app/infrastructure/mail/templates/` 管理。

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
