# 服务器部署与运维

最后核对：2026-08-09。本文件是当前服务器部署的正式事实来源；`docs-dev/` 中的远程运维手册仅供历史追溯。

## 1. 生产事实来源：Jenkins

生产环境由仓库根目录的 `Jenkinsfile` 构建和部署。Jenkins 不会替开发者创建 Git 提交；它只会检出已经提交的 `HEAD`，通过 `git archive HEAD` 上传源码，再以提交短哈希构建唯一镜像。

| 场景 | 环境文件 | 后端标识 | 用途 |
| --- | --- | --- | --- |
| Jenkins 生产部署 | `DEPLOY_ENV_FILE`，默认 `/opt/wild-agent/.env` | 容器名 `wild-server` | 生产唯一主路径 |
| Docker Compose | `<repo>/wild-server/.env` | 服务名 `server`，网络别名 `wild-server` | 本地或临时部署 |

文档所在目录不会影响程序读取配置。生产环境修改 `wild-server/.env` 不会生效，除非 Jenkins 参数也改为该路径；默认只读取 `/opt/wild-agent/.env`。

Jenkins 生产流程为：

```text
检出提交 HEAD
  -> 上传该提交源码到远程临时目录
  -> 前端编译 + 后端语法/单元测试
  -> 构建 <branch>-<commit> 唯一镜像
  -> 删除旧容器
  -> 使用 /opt/wild-agent/.env 创建新容器
  -> 校验容器、镜像标签、模型名和后端 HTTP
```

只有 main/master 的非 Pull Request 构建会部署。流水线失败时，必须以 Jenkins 的具体 stage 为准，不能只看 GitHub 已经出现提交。

构建工具 uv 固定为 `0.11.14`，与仓库 `uv.lock` 的生成版本一致。禁止在流水线中使用无版本号的 `pip install uv`，否则 uv 自动升级后可能在业务代码未变化时把锁文件判定为过期。

## 2. Jenkins 环境文件

默认生产文件为 `/opt/wild-agent/.env`：

```dotenv
CHAT__NAME=replace-with-your-chat-model-id
CHAT__API_KEY=replace-me
CHAT__BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

EMBEDDING__NAME=text-embedding-v4
EMBEDDING__API_KEY=replace-me
EMBEDDING__BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

RAG__ENABLED=true
RAG__ALLOW_HASH_FALLBACK=false
```

该文件不进入 Git。修改后触发一次 main/master Jenkins 部署，流水线会删除并重新创建容器；无需在服务器手工执行 `docker restart`。

Jenkins 部署后可安全核对实际配置，不输出 API Key：

```bash
docker exec wild-server python -c "import os,hashlib; k=os.environ.get('CHAT__API_KEY',''); print('model=',os.environ.get('CHAT__NAME')); print('base_url=',os.environ.get('CHAT__BASE_URL')); print('key_fingerprint=',hashlib.sha256(k.encode()).hexdigest()[:8])"
```

模型 ID 必须与百炼控制台完全一致；不要把控制台展示名称或口头简称直接写入配置。

## 3. 如何确认某次提交已经部署

本地或 GitHub 的提交哈希并不能单独证明部署完成。Jenkins 日志应同时满足：

- `初始化` stage 显示预期 `commit=<短哈希>`；
- `远程后端语法检查` 中全部测试通过；
- `远程构建 Docker 镜像` 的标签包含同一短哈希；
- `远程部署到生产` 显示两个容器运行、镜像匹配和 `backend_http_status=200`。

服务器可查看当前运行镜像：

```bash
docker inspect -f '{{.Config.Image}}' wild-server
docker inspect -f '{{.Config.Image}}' wild-web
docker logs --tail=100 wild-server
```

镜像标签格式为：

```text
wild-agent/wild-server:<branch>-<commit-short>
wild-agent/wild-web:<branch>-<commit-short>
```

如果显示 `latest` 或旧提交标签，说明对应流水线没有成功走完部署 stage。

## 4. Docker Compose 仅用于本地或备用部署

Compose 读取仓库内的 `wild-server/.env`：

```bash
docker compose up -d --build --force-recreate server web
docker compose ps
docker compose logs --tail=100 server
```

`wild-web/nginx.conf` 使用 `wild-server:8000`。Compose 已给 `server` 声明 `wild-server` 网络别名，但 Compose 容器不应与 Jenkins 生产容器同时运行在同一端口。

仓库中的 `.gitlab-ci.yml` 是另一套独立流水线。未明确启用 GitLab/JihuLab Runner 时不要同时开启它和 Jenkins 的生产 deploy job，否则两个系统会竞争删除、重建同名容器。

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
