---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 120c9aab85e3ed979ff6cbda3bbcb633_986ce7959c4911f184de525400f8a581
    ReservedCode1: P+Qqn2M3CEcn5ZwvpdiyiwmQ40XkPwtlWg7FyhngX9EFwXhC95bj+AwdTpB+V6/FXqoVtpkop43/KgHzfaKhxEcy+hO6Lw++PXw1+oEs0G2NbGq6xCeEWXTkxDIqvMEthcgWZWZ33hDb4seKJVfCvnXoVD3/rZN2LBdUx+ffADOcjpjy6Gj5+W11eR8=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 120c9aab85e3ed979ff6cbda3bbcb633_986ce7959c4911f184de525400f8a581
    ReservedCode2: P+Qqn2M3CEcn5ZwvpdiyiwmQ40XkPwtlWg7FyhngX9EFwXhC95bj+AwdTpB+V6/FXqoVtpkop43/KgHzfaKhxEcy+hO6Lw++PXw1+oEs0G2NbGq6xCeEWXTkxDIqvMEthcgWZWZ33hDb4seKJVfCvnXoVD3/rZN2LBdUx+ffADOcjpjy6Gj5+W11eR8=
---



# deploy/ — 部署前检查脚本

生产部署前对模型、Embedding 与镜像知识库的连通性做冒烟检查。

## 文件清单

| 文件 | 作用 |
|---|---|
| `deployment_preflight.py` | 部署前预检：创建 LLM 并验证模型能返回有效文本（优先 content，兼容仅 reasoning 的供应商）；创建 Embedding 函数；检查镜像知识库文件数量等。提供 `select_smoke_response_text()` 等可复用函数。 |

## 运行方式

需在 **wild-server 根目录** 下运行，并设置 `PYTHONPATH="."`：

```powershell
cd E:\AgentProject\WildAgent\wild-server
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe scripts\deploy\deployment_preflight.py
```

或使用 uv（免手动激活）：

```powershell
$env:PYTHONPATH="."; uv run --no-project python scripts/deploy/deployment_preflight.py
```

## 输出解读

运行 `deployment_preflight.py` 会在控制台打印一组 `preflight_*` 字段，逐项含义与通过标准：

| 输出 | 含义 | 通过标准 |
|---|---|---|
| `knowledge_base_files=N` | 镜像知识库实际文件数 | 大于 0；同时脚本断言 `BLUEPRINT-SPEC-MINIMAL.md` 等关键文件存在 |
| `preflight_model=...` | 聊天模型名（`config.chat.name`） | 与部署目标模型一致 |
| `preflight_base_url=...` | 聊天模型 base URL | 非空 / 与预期网关一致（`(default)` 表示未显式配置） |
| `preflight_rag_enabled=true/false` | RAG 开关（`config.rag.enabled`） | 按部署规划应为 `true` |
| `preflight_embedding=...` | embedding 模型名（`config.embedding.name`） | 与预期一致 |
| `embedding_smoke=ok dimensions=N` | embedding 冒烟：真实调用一次返回向量 | N 应为模型输出维度（如 qwen 为 1024）；`embedding_smoke=skipped` 表示未配置 Key 跳过 |

**如何判断失败**：脚本任一断言失败（如关键文件缺失、模型响应异常）会抛出异常并以非 0 退出码结束，需要修复对应配置 / 网络 / 密钥后重跑，直到所有 `preflight_*` 字段正常。

**可复用函数**：`select_smoke_response_text()` 等函数可从脚本导入，供测试与二次开发使用（见 `tests/misc/test_deployment_preflight.py`）。

## 相关引用

- `tests/misc/test_deployment_preflight.py` 通过 `from scripts.deploy.deployment_preflight import select_smoke_response_text` 导入测试。
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
