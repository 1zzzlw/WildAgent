# 服务器部署与运维

最后核对：2026-08-10。本文件是当前服务器部署的正式事实来源；`docs-dev/` 中的远程运维手册仅供历史追溯。

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
  -> 新镜像读取生产 .env，校验必填配置并执行一次最小真实模型请求
  -> 删除旧容器
  -> 使用 /opt/wild-agent/.env 创建新容器
  -> 等待后端（最多 180 秒）与前端（最多 40 秒）真正就绪
  -> 校验容器、镜像标签、模型/RAG 配置和后端 HTTP
  -> 新版本启动失败时恢复旧版本镜像
```

只有 main/master 的非 Pull Request 构建会部署。流水线失败时，必须以 Jenkins 的具体 stage 为准，不能只看 GitHub 已经出现提交。

构建工具 uv 固定为 `0.11.14`。Jenkins 上传的是一次性远程构建目录；后端验证会先在该临时目录执行 `uv lock`，补齐 Linux 平台解析结果，再以 `--frozen` 运行测试，后续 Docker 构建继续使用同一份临时锁文件。该过程不会修改 GitHub 工作区，也不需要维护 Windows/Linux 两份锁文件。禁止在流水线中使用无版本号的 `pip install uv`，否则构建工具自动升级仍可能导致解析行为漂移。

后端验证容器不会挂载生产 `/opt/wild-agent/.env`。测试收集会导入全局 `AgentService`，因此 Jenkins 只为该临时容器注入 `ci-placeholder` 占位 Key，并把模型地址指向不可用的本机端口 `127.0.0.1:9`；这既满足客户端初始化，也能让误发起的真实模型调用立即失败，不会泄露或消耗生产凭据。RAG 在该阶段显式使用 hash fallback，并将临时 Chroma 数据写入容器 `/tmp`。正式部署容器仍只读取 `DEPLOY_ENV_FILE` 指定的服务器环境文件。

部署前 smoke test 与单元测试不同：它使用本次新镜像和生产 `DEPLOY_ENV_FILE`，检查 Chat 配置、RAG/Embedding 必填项，向实际 Chat 服务发送一个最多 128 token 的最小请求，并用实际 Embedding 服务生成一个测试向量。探针复用运行时的多内容块解析，并按 `content → reasoning_content` 回退选择响应；部分推理模型在很小输出预算下只返回推理字段，不会再被误判为模型断连。日志额外输出实际文本来源和 `finish_reason`，但不输出模型回复、API Key 或向量内容。该步骤在删除旧容器之前执行，90 秒内没有成功就终止部署，因此仍能提前发现错误 Key、额度耗尽、模型 ID 不存在、兼容参数不支持、Embedding 配置失效和服务器无法访问模型服务，同时保留旧服务。

`storage/knowledge_base` 是镜像内置的只读 Agent 输入，不能被 `.dockerignore` 的通用 `storage` 规则排除。生产只把 `scenes/sessions/chroma/assets/geoip` 子目录挂载到 `/app/storage`，不会遮住镜像知识库；其中 `assets` 保存 PBR 图片和不可变清单，重新部署不能删除。Docker 构建与部署前预检都会要求镜像内存在 `BLUEPRINT-SPEC-MINIMAL.md` 且知识库 Markdown 不少于 30 个；日志必须出现 `knowledge_base_files=<数量>`。否则构建立即失败，不允许空知识库容器启动后把持久化 Chroma 分片删除。

后端每次启动都会执行 Chroma 增量同步：内容或 metadata 变化时更新对应分片，文件删除时移除旧分片，Embedding/分块索引签名变化时重建 collection。修复空知识库镜像后的第一次生产启动会重新写入完整索引，`RAG 索引同步` 日志中的 `total` 和 `updated` 应恢复为知识库实际分片数；后续没有知识变更时 `updated=0` 属于正常复用，不代表未更新。

Docker 与 Jenkins 使用 `/health/ready` 而不是普通首页判断后端就绪。该接口读取当前服务进程中的真实 Loader：生产开启 RAG 时必须满足 `loader=RAGSpecLoader`、`source_count>=30` 且 `sync.total>0`；Embedding 或 Chroma 初始化失败后若代码降级成 `FileSpecLoader`，接口返回 503，部署会输出日志并恢复旧镜像。只有显式配置 `RAG__ENABLED=false` 时，文件 Loader 才被视为健康。

后端启动时需要加载应用、同步 Chroma 知识库并创建模型客户端，5 秒内未监听端口并不等于启动失败。Jenkins 不再固定 `sleep 5` 后只探测一次，而是轮询容器状态和 HTTP；新后端超过 180 秒仍未就绪、前端超过 40 秒仍未就绪或容器提前退出时，会打印新容器日志并使用部署前记录的版本镜像恢复旧容器。后端镜像也包含 Docker `HEALTHCHECK`，便于部署后持续查看健康状态。

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

ASSETS__BACKEND=local
ASSETS__ROOT_DIR=storage/assets
ASSETS__PUBLIC_BASE_URL=/api/assets
```

当前 `ASSETS__PUBLIC_BASE_URL=/api/assets` 让 `.wild` 保存站内 URL。迁移对象存储/CDN 时，把它改为公开 HTTPS 前缀，并确保对象路径仍为 `{assetId}/files/{filename}`、CDN CORS 允许前端站点读取图片；不要把宿主机文件路径或 `file://` 地址写进 Blueprint。

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
- `远程部署到生产` 显示 `knowledge_base_files`、`model_smoke=ok`、`embedding_smoke=ok`、两个容器已就绪、镜像匹配和 `backend_http_status=200`。

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
- 部署预检的 `source=reasoning_content`：模型连通，但最小探针的普通 `content` 为空；这对连通性检查是有效响应，正式生成仍会使用相同兼容提取逻辑；
- `model returned no text in content or reasoning_content`：Chat 请求返回了响应对象，但两个文本通道都为空，需要结合日志中的 `finish_reason` 检查模型输出上限或供应商兼容性；
- `Blueprint 首次提取失败`：模型调用成功，但结构化内容缺失、被包装或 JSON 无效；
- `Blueprint 定向格式恢复成功`：系统已用一次非思考调用补回单一 JSON，可继续组件生成；
- WebSocket `heartbeat_timeout`：浏览器到 Nginx/后端的连接问题。

一次精密生成包含分类、骨架、多个组件、合并、校验和回调等多次模型请求。前几个节点成功、后续节点失败并不代表使用了不同模型，必须以具体节点错误和 HTTP 错误码判断。

## 6. 数据与回滚

生产服务器至少备份：

- 实际使用的 `.env`（放入安全凭据系统，不进入 Git）；
- `wild-server/storage/scenes`；
- `wild-server/storage/sessions`；
- `wild-server/storage/assets`（PBR 图片和 `manifest.json`）；
- `wild-server/storage/knowledge_base` 与需要保留的 Chroma 索引。

上线前记录当前提交哈希和镜像 ID。代码回滚不能覆盖或删除 `storage`；环境文件和模型计费开关也不随 Git 提交回滚。
