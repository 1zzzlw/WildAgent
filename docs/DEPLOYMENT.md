# 服务器部署与运维

最后核对：2026-08-09。本文件是当前服务器部署的正式事实来源；`docs-dev/` 中的远程运维手册仅供历史追溯。

## 1. 只选择一种部署方式

项目曾同时使用 Compose 和手工 `docker run`，两者的环境文件位置与容器命名不同。不要混用：

| 方式 | 环境文件 | 后端标识 | 当前建议 |
| --- | --- | --- | --- |
| Docker Compose | `<repo>/wild-server/.env` | 服务名 `server`，网络别名 `wild-server` | 推荐 |
| 旧版手工 `docker run` | 由 `--env-file` 指定，旧服务器通常为 `<repo>/.env` | 容器名 `wild-server` | 仅兼容存量环境 |

文档所在目录不会影响程序读取配置。真正的配置来源是 Compose 的 `env_file` 或 `docker run --env-file` 参数；修改另一份同名文件不会生效。

## 2. 推荐：Docker Compose

在服务器仓库根目录创建 `wild-server/.env`，不要提交该文件：

```dotenv
CHAT__NAME=glm-5.2
CHAT__API_KEY=replace-me
CHAT__BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

EMBEDDING__NAME=text-embedding-v4
EMBEDDING__API_KEY=replace-me
EMBEDDING__BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

RAG__ENABLED=true
RAG__ALLOW_HASH_FALLBACK=false
```

构建并强制重建：

```bash
docker compose up -d --build --force-recreate server web
docker compose ps
docker compose logs --tail=100 server
```

只执行 `docker compose restart` 不保证重新注入修改后的 `.env`。环境变量发生变化时必须重建容器。

`wild-web/nginx.conf` 使用 `wild-server:8000`。Compose 已给 `server` 服务声明同名网络别名，因此与旧版命名容器都兼容。

## 3. 旧版手工容器

如果服务器仍由 `docker run` 管理，以实际启动参数为准：

```bash
docker inspect wild-server --format '{{json .Config.Env}}'
docker inspect wild-server --format '{{json .HostConfig.Binds}}'
docker network inspect wild-net
```

旧方式必须同时满足：

- 后端容器名或网络别名为 `wild-server`，否则 Nginx 无法解析上游；
- `--env-file` 指向真正维护的服务器环境文件；
- `storage` 挂载到 `/app/storage`，否则场景、会话和 Chroma 索引不会持久化；
- 前后端加入同一个 Docker 网络。

建议迁移到 Compose。迁移前先备份服务器 `.env` 与 `storage`，不要直接删除仍承载数据的旧容器或卷。

## 4. 确认服务器运行的代码和配置

服务器仓库提交应与 GitHub `main` 一致：

```bash
git status --short --branch
git rev-parse HEAD
git ls-remote WildAgent refs/heads/main
```

如果服务器远端名称不是 `WildAgent`，用 `git remote -v` 查询真实名称。提交一致但行为仍旧，通常是镜像没有重新构建。

不要输出完整 API Key。Compose 环境可用以下命令核对模型、Endpoint 和 Key 指纹：

```bash
docker compose exec server python -c "import os,hashlib; k=os.environ.get('CHAT__API_KEY',''); print('model=',os.environ.get('CHAT__NAME')); print('base_url=',os.environ.get('CHAT__BASE_URL')); print('key_fingerprint=',hashlib.sha256(k.encode()).hexdigest()[:8])"
```

GLM 在百炼中的模型 ID 使用 `glm-5.2`，不是 `glm5.2`。

## 5. 生成中断排查

按日志错误码区分原因：

- `AllocationQuota.FreeTierOnly`：百炼免费额度或“仅使用免费额度”开关，和 Blueprint 解析无关；
- HTTP 429：RPM/TPM 限流；
- `finish_reason=length`：模型达到输出上限；
- `Blueprint 首次提取失败`：模型调用成功，但结构化内容缺失、被包装或 JSON 无效；
- `Blueprint 定向格式恢复成功`：系统已用一次非思考调用补回单一 JSON，可继续组件生成；
- WebSocket `heartbeat_timeout`：浏览器到 Nginx/后端的连接问题。

一次精密生成包含分类、骨架、多个组件、合并、校验和回调等多次模型请求。前几个节点成功、后续节点失败并不代表使用了不同模型，必须以具体节点错误和 HTTP 错误码判断。

## 6. 数据与回滚

生产服务器至少备份：

- 实际使用的 `.env`（放入安全凭据系统，不进入 Git）；
- `wild-server/storage/scenes`；
- `wild-server/storage/sessions`；
- `wild-server/storage/knowledge_base` 与需要保留的 Chroma 索引。

上线前记录当前提交哈希和镜像 ID。代码回滚不能覆盖或删除 `storage`；环境文件和模型计费开关也不随 Git 提交回滚。
