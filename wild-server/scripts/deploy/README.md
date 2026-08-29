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

生产部署前默认离线检查镜像知识库；需要时可显式测试 Chat 与 Embedding 连通性。

## 文件清单

| 文件 | 作用 |
|---|---|
| `deployment_preflight.py` | 默认只检查镜像知识库，不访问外部供应商；传入 `--live-providers` 后才创建 LLM 与 Embedding 并执行真实冒烟。提供 `select_smoke_response_text()` 等可复用函数。 |

## 运行方式

需在 **wild-server 根目录** 下运行，并设置 `PYTHONPATH="."`：

```powershell
cd E:\AgentProject\WildAgent\wild-server
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe scripts\deploy\deployment_preflight.py
```

默认输出 `preflight_mode=offline`，不会消耗模型额度。只有排查生产连通性时才运行：

```powershell
.\.venv\Scripts\python.exe scripts\deploy\deployment_preflight.py --live-providers
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
| `preflight_mode=offline/live_providers` | 本次是否调用外部供应商 | Jenkins 默认必须是 `offline`；手工诊断才使用 `live_providers` |
| `model_smoke=skipped reason=...` | 默认未调用聊天模型 | 离线发布时是正常结果，不是失败 |
| `embedding_smoke=skipped reason=...` | 默认未调用 Embedding | 离线发布时是正常结果，不是失败 |
| `model_smoke=ok source=...` | 真实模式下聊天模型返回了有效文本 | `source` 可以是 `content` 或 `reasoning_content`；仅在 `--live-providers` 下出现 |
| `embedding_smoke=ok dimensions=N` | 真实模式下调用一次 Embedding 返回向量 | N 应为模型输出维度；仅在 `--live-providers` 下出现 |

**如何判断失败**：默认模式只会因镜像知识库不完整而失败。`--live-providers` 模式还会因供应商配置、额度、网络或响应异常而失败。

**可复用函数**：`select_smoke_response_text()` 等函数可从脚本导入，供测试与二次开发使用（见 `tests/misc/test_deployment_preflight.py`）。

## 相关引用

- `tests/misc/test_deployment_preflight.py` 通过 `from scripts.deploy.deployment_preflight import select_smoke_response_text` 导入测试。
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
