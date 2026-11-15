# WildAgent Server

后端提供 FastAPI REST/WebSocket、LangGraph 编排、RAG 与确定性 Blueprint 校验，采用分层单体结构。

当前后端目录与启动配置见本文，Agent 职责说明见 [`app/agent/README.md`](app/agent/README.md)。阶段总结与修复报告沿用项目历史资料目录，不放进业务源码。

首次启动前，在远程 MySQL 8.0.19+ 创建并选中数据库（例如 `wild_agent`），手动导入完整建表脚本 [`db/schema.sql`](db/schema.sql)，然后填写 `.env` 的 `MYSQL__*`、`REDIS__*`、`SMTP__*`。启动只检查表和版本，不自动建表或修改结构。

```powershell
uv sync
uv run uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

MySQL 持久化账号、会话元数据、聊天消息、执行轮次、蓝图、设计版本、生成任务与检查点；Redis 管理登录会话、邮箱验证码、在线连接、任务租约和跨实例通知。图片、纹理、物品目录、Chroma 及诊断日志继续使用各自的存储模块。

```text
wild-server/
├── main.py                   # 保持 main:app 启动入口
├── config.py                 # .env 配置契约
├── app/
│   ├── bootstrap/            # 应用装配、生命周期、资源初始化
│   ├── api/                  # HTTP、WebSocket、身份解析和异常映射
│   ├── application/          # 账号、蓝图、会话等用例及生成任务交付
│   ├── agent/                # LangGraph、状态、节点、工作流、提示词和模型工具
│   ├── domain/               # 设计契约、蓝图计算、编译、几何和确定性校验
│   ├── infrastructure/       # MySQL、Redis、模型、检索、邮件和文件存储
│   └── paths.py              # 与工作目录无关的项目资源路径
├── tests/
│   ├── unit/                 # 规则、配方、配置行为
│   ├── integration/          # 仓储、账号、连接协调
│   ├── contracts/            # 协议、自动继续及依赖边界
│   ├── replay/               # 固定模型输出与失败证据回放
│   └── fixtures/             # 回放输入
├── db/schema.sql             # 手动导入的完整建表 SQL
├── scripts/                  # 迁移、运维、知识库维护等命令
└── storage/                  # 知识库、纹理和本地资源
```

HTTP / WebSocket 调用 `application` 用例；生成用例调用 `agent` 工作流，工作流复用 `domain` 的确定性计算和 `infrastructure` 的外部服务。`domain` 不依赖其他业务层，`agent` 不导入 API 或应用用例。应用装配统一在 `bootstrap` 完成。

生成入口为 `application/generation/runner.py`：请求预检 → 执行或恢复图 → `streaming.py` 处理流事件 → `finalize.py` 组织结果 → `delivery.py` 校验并保存。`jobs.py` 管理持久化任务、租约与事件补发，WebSocket 只持有物理连接。图纸和材质确定后自动继续生成。

应用启动时显式初始化数据库、缓存、模型和知识加载器；导入 `agent/runtime.py` 只创建空的资源容器。Studio 入口显式初始化，知识维护脚本按需创建检索资源。邮件模板和内嵌图标随 `infrastructure/mail/templates/` 管理。

接口地址、事件字段和 `.env` 配置项保持兼容。Agent 目录约定见 [`app/agent/README.md`](app/agent/README.md)。回归统一放在 `tests/`，在本目录执行 `uv run pytest`；隔离数据库端口约定见 `tests/conftest.py`。

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
