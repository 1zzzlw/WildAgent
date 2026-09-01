# RAG 在线门控、权限、引用与质量控制手册

> 本文介绍步骤 0～7 的运行方式。代码能力已经接入，但生产距离阈值、身份代理密钥和 Judge 模型仍必须按部署环境配置。

## 1. 当前请求链路

```text
WebSocket 用户请求
  ↓ 服务端身份头验证
AccessContext + 权限过滤
  ↓ PII 脱敏 + 内容安全检查
多意图向量检索
  ↓ chunk_id + raw_distance
Retrieval Gate（off / observe / enforce）
  ├─ chat 证据不足：enforce 时确定性拒答
  ├─ generation 证据不足：enforce 时退回基础规范
  └─ 通过：构造带 chunk_id 的 Context
  ↓
LLM / Agent
  ↓ 引用只允许来自实际注入 Context
回答 + cited_chunk_ids
  ↓
storage/sessions/rag_traces/<session_id>/<request_id>.json
```

## 2. Trace 文件

默认目录：

```text
E:\AgentProject\WildAgent\wild-server\storage\sessions\rag_traces\
  session_123\
    req_456.json
```

文件使用“临时文件写完后原子替换”的方式保存，避免进程中断留下半个 JSON。文件包括：

- 查询、查询哈希、业务过滤和服务端最终过滤；
- Chroma 的真实 `chunk_id`、来源、标题和 `raw_distance`；
- 实际注入 Context 的 chunk IDs；
- observe/enforce 门控结论；
- LLM 耗时与 Token；
- 有效引用和被清除的伪造引用；
- PII 类别、内容安全结论、脱敏后的最终回答；
- 非密钥 AccessContext 和用户反馈。

汇总运行指标：

```powershell
.\.venv\Scripts\python.exe scripts\rag\summarize_rag_traces.py `
  --output scripts\reports\rag_trace_summary.json
```

脚本会计算空召回率、平均最佳距离、强制拒答率、总/检索/LLM P95 延迟、Token 和反馈。模型价格不会写死；需要成本估算时再传入：

```powershell
  --input-cost-per-million 2.0 --output-cost-per-million 8.0
```

这里的数字只是命令格式示例，实际单价必须填写当前供应商和模型的价格；未提供时 `estimated_token_cost` 为 `null`。
如果通过 `RAG__TRACE__ROOT_DIR` 改过默认目录，运行汇总脚本时同步传入 `--root <实际目录>`。

## 3. Retrieval Gate

环境变量采用 Pydantic 双下划线写法：

```dotenv
RAG__RETRIEVAL_GATE__MODE=observe
RAG__RETRIEVAL_GATE__MAX_DISTANCE=0.52
RAG__RETRIEVAL_GATE__MIN_HITS=1
```

三种模式：

- `off`：不计算拒答用途的结论；
- `observe`：记录“如果 enforce 会不会拒答”，但不改变回答；
- `enforce`：阈值已配置时执行拒答或生成降级。

`MAX_DISTANCE` 默认是 `null`。即使误把模式设为 enforce，没有校准阈值时也会以 `threshold_not_calibrated` 放行，避免拿猜测数字阻断服务。

### 3.1 正负样本校准

当前 Golden Set 有 60 题：28 道正样本、32 道跨领域负样本。先使用生产相同的 Embedding、索引签名、Top-K 和知识库运行：

```powershell
cd E:\AgentProject\WildAgent\wild-server
$env:PYTHONPATH="."

.\.venv\Scripts\python.exe scripts\rag\eval_retrieval.py `
  --json-output scripts\reports\rag_eval.json `
  --output scripts\reports\rag_eval.md

.\.venv\Scripts\python.exe scripts\rag\calibrate_retrieval_gate.py `
  scripts\reports\rag_eval.json `
  --output scripts\reports\rag_gate_calibration.json
```

校准器会比较正样本错误拒答率和负样本错误放行率，选择 balanced accuracy 最高的候选阈值，并把 Embedding 与索引签名写入报告。先保持 observe，人工查看误判题后再切 enforce。

快捷模式：`calibrate_retrieval_gate.py --eval` 会直接复用 eval 的 Loader 装配跑一遍评测再校准，免去先手动输出 JSON 的两步：

```powershell
.\.venv\Scripts\python.exe scripts\rag\calibrate_retrieval_gate.py `
  --eval --embedding hash `
  --output scripts\reports\rag_gate_calibration.json
```

`--eval` 模式支持与 `eval_retrieval.py` 对齐的 `--questions / --top-k / --namespace / --embedding / --temporary-index / --chunk-size / --chunk-overlap / --sync-index`。评测包含检索异常时脚本会打印警告（异常样本按空召回计入，阈值偏保守）。注意 `--limit` 截断问题集可能抽不到负样本，导致 `阈值校准至少需要一个正样本和一个负样本` 报错；校准应使用完整评测集。

## 4. chunk_id 引用闭环

Loader 注入格式：

```text
[chunk_id=wild_spec:...]
```

回答引用格式：

```text
[引用:wild_spec:...]
```

系统会执行确定性校验：

1. 只允许本次实际进入 Context 的 ID；
2. 删除模型虚构的 ID；
3. 模型漏引时，补充本次实际证据中的前 1～3 个 ID；
4. WebSocket `agent_reply` 返回 `cited_chunk_ids`；
5. Trace 同时保存有效引用、无效引用和是否使用了兜底引用。

这能保证“引用存在且属于本次证据”，但不能单独证明每句话都被该分片支持；Faithfulness 仍需 Judge 和人工抽查。

## 5. 服务端身份与权限过滤

默认匿名请求只能访问 `access_scope=public`。知识库 `config.yaml` 已把当前仓库文档统一标成 public。

受限身份必须由可信反向代理添加以下请求头：

```text
X-Wild-Auth-Secret
X-Wild-User-Id
X-Wild-Tenant-Id
X-Wild-Department
X-Wild-Clearance-Level
X-Wild-RAG-Scopes: public,tenant,department
```

后端环境配置：

```dotenv
RAG__SECURITY__TRUSTED_HEADER_SECRET=<随机长密钥>
```

只有 `X-Wild-Auth-Secret` 与服务端密钥一致时，其余身份头才被接受。客户端 JSON 中自报的 `tenant_id/department/clearance_level/access_scope` 会被删除，不能覆盖服务端条件。

受限文档示例 metadata：

```yaml
access_scope: department
tenant_id: tenant_a
department: engineering
clearance_level: 2
```

## 6. PII 与内容安全

默认在消息进入持久化任务、Embedding 和 LLM 前替换：

- 中国大陆手机号；
- 18 位身份证号；
- 邮箱；
- 常见连续电话号码。

替换后的标记例如 `[手机号]`，Trace 不保存原号码，查询哈希也基于脱敏文本。

内容安全目前是高置信确定性兜底，只覆盖少量明确的未成年人色情、暴力制作指导和凭证窃取规则。它不会把一般政治、历史或建筑讨论一律屏蔽，也不能替代生产级审核供应商。

## 7. 用户反馈

接口：

```http
POST /api/rag/feedback
Content-Type: application/json

{
  "session_id": "session_123",
  "request_id": "req_456",
  "rating": "up",
  "comment": "召回内容正确"
}
```

`rating` 只接受 `up/down`。找不到对应 Trace 时返回 404，避免形成无法关联的孤儿反馈；评论在写文件前再次做 PII 脱敏。

## 8. LLM-as-Judge

Judge 不自动运行在每次在线请求中，避免额外延迟和费用。准备输入：

```json
{
  "question": "基础静态窗有哪些参数？",
  "answer": "……[引用:chunk_id]",
  "contexts": ["本次引用分片正文"]
}
```

运行：

```powershell
.\.venv\Scripts\python.exe scripts\rag\judge_rag_answer.py `
  scripts\reports\judge_input.json `
  --output scripts\reports\judge_result.json
```

输出固定包含 `answer_relevance`、`faithfulness`、`citation_quality`、模型名和 `prompt_version=rag-judge-v1`。Judge 是辅助信号，不能覆盖权限门禁、引用校验或 Blueprint 确定性验证。

## 9. CI 门禁

GitLab `RAG质量门禁` 会：

1. 运行 `tests/rag`；
2. 使用 HashEmbedding 和临时 Chroma 跑 60 题结构回归；
3. 生成 JSON/Markdown artifact；
4. 根据 `evals/rag_quality_gate.json` 检查题数、负样本数、Hit@K、Recall@K、MRR 和检索异常。

HashEmbedding 门禁用于发现代码、分片和数据集的大幅回归，不代表生产中文语义质量。生产 Embedding 仍应单独运行报告并保存基线。
