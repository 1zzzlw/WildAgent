# RAGTrace 日志阅读指南

> 文档分类：RAG 专题。返回 [RAG 文档入口](README.md)。
>
> 适用版本：2026-08-24 起的请求级 RAG 观测实现。Gate 默认是 observe；只有显式配置 enforce 和已校准阈值才会改变行为。

## 1. RAGTrace 是什么

一次用户请求可能经历多个 Agent 节点，每个节点又可能各自检索知识库和调用大模型。如果只看零散的“命中了哪个文件”，很难回答：

- 这次检索属于哪一个用户请求？
- 实际使用了哪些查询词和过滤条件？
- Chroma 返回了哪些 `chunk_id`，原始距离是多少？
- 最终拼入 Prompt 的知识上下文有多大？
- 检索和模型分别花了多久、用了多少 Token？

`RAGTrace` 用同一个 `request_id` 把这些事实串成一条 JSON 日志。它只负责观察，不参与检索排序、拒答判断或答案生成。

## 2. 怎么产生一条日志

先启动后端：

```powershell
cd E:\AgentProject\WildAgent\wild-server
uv run uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

也可以直接使用项目虚拟环境：

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

随后在前端发送一条普通问题或建筑生成请求。请求完成、失败或被取消时，后端控制台会出现以 `[RAG_TRACE]` 开头的一行：

```text
[RAG_TRACE] {"request_id":"req_123", ...}
```

同一份数据会输出到控制台，并原子保存到：

```text
wild-server/storage/sessions/rag_traces/<session_id>/<request_id>.json
```

不要手工修改 JSON 后再拿它做评测依据。

## 3. 一个简化示例

为了便于阅读，下面把真实的单行 JSON 展开了：

```json
{
  "request_id": "req_123",
  "session_id": "session_123",
  "started_at": "2026-08-24T08:30:00.000+00:00",
  "status": "completed",
  "error_type": null,
  "elapsed_ms": 1520,
  "summary": {
    "retrieval_calls": 1,
    "retrieval_ms": 86,
    "context_builds": 1,
    "max_context_chars": 6420,
    "llm_calls": 1,
    "llm_ms": 1310,
    "token_usage": {
      "input": 2100,
      "output": 420,
      "total": 2520
    }
  },
  "retrievals": [
    {
      "operation": "retrieve_many",
      "elapsed_ms": 86,
      "error_type": null,
      "queries": [
        {
          "query": "基础静态窗参数",
          "query_sha256": "……",
          "metadata_filter": {"entity_type": "window"},
          "effective_filter": {"$and": ["……"]}
        }
      ],
      "hit_count": 1,
      "hits": [
        {
          "chunk_id": "wild_spec:……",
          "parent_chunk_id": "windows:……",
          "source": "components/windows.md",
          "heading": "基础静态窗组合构件 > 当前支持的基础静态窗 > 参数契约",
          "raw_distance": 0.18
        }
      ]
    }
  ],
  "contexts": [
    {
      "operation": "load_many",
      "base_chars": 3200,
      "retrieved_chars": 2800,
      "context_chars": 6420,
      "retrieved_count": 1,
      "injected_chunk_ids": ["wild_spec:……"]
    }
  ],
  "gate_decisions": [
    {
      "mode": "observe",
      "purpose": "chat",
      "decision": "pass",
      "reason": "distance_within_threshold",
      "threshold": 0.52,
      "best_distance": 0.18,
      "enforced": false
    }
  ],
  "citations": [
    {
      "cited_chunk_ids": ["wild_spec:……"],
      "invalid_chunk_ids": [],
      "appended_fallback": false
    }
  ],
  "llm_calls": [
    {
      "mode": "invoke",
      "elapsed_ms": 1310,
      "error_type": null,
      "token_usage": {"input": 2100, "output": 420, "total": 2520}
    }
  ]
}
```

## 4. 建议的阅读顺序

### 第一步：确认是不是同一次请求

先看 `request_id`，再去对照 WebSocket 消息、Agent 节点日志和最终结果。不同 `request_id` 的数据不能混在一起分析。

`status` 当前主要有：

- `completed`：请求处理函数正常结束；
- `error`：异常离开请求边界，`error_type` 会记录异常类型。

`session_id` 决定文件夹，`request_id` 决定文件名。两者都会先过滤路径特殊字符，因此客户端不能通过 `../` 把日志写到 `storage/sessions/rag_traces` 之外。

### 第二步：看 Agent 实际查了什么

查看 `retrievals[].queries`：

- `query`：送给向量检索的查询文本，压缩空白后最多保留 300 个字符；
- `query_sha256`：完整查询文本的稳定哈希，文本相同则哈希相同；
- `metadata_filter`：当前节点主动传入的业务过滤，例如 `entity_type=window`；
- `effective_filter`：Loader 最终交给 Chroma 的完整过滤，还包含 `namespace`、`doc_scope`、`status` 和 `authority` 等默认约束。

如果“应该查窗，实际却查了屋顶”，问题更可能在查询规划；如果查询正确但结果不对，再继续看命中和距离。

### 第三步：看命中了什么

查看 `retrievals[].hits`：

- `chunk_id`：Chroma 中真实的分片 ID，不是日志临时生成的编号；
- `source`：知识库 Markdown 来源；
- `heading`：分片所属的完整标题路径；
- `parent_chunk_id`：超长章节被拆成多个 part 时，它们共享的父分片 ID；
- `raw_distance`：Chroma 返回的原始向量距离。

`heading` 例如“基础静态窗组合构件 > 当前支持的基础静态窗 > 参数契约”，来自 Markdown 的多级标题组合，并不是向量模型生成的内容。详细来源见 [RAG 全链路研究说明书](RAG_PIPELINE_GUIDE.md)。

### 第四步：正确理解 raw_distance

在当前索引配置中，可以先按“距离越小，向量越接近”来阅读，但必须注意：

- 它是距离，不是百分比，也不是模型置信度；
- `0.2` 不能直接解释成“80% 可信”；
- 不同 Embedding 模型、距离算法、知识库版本和查询写法的数值不能直接横向比较；
- 当前排序还会考虑知识状态与权威性，因此最终顺序不只由原始距离决定；
- 命中超长章节时，系统会补充相邻 part。相邻 part 不是独立向量命中，所以其 `raw_distance` 是 `null`。

现阶段先收集正样本和负样本的距离分布。等离线校准完成后，才能决定 Retrieval Gate 阈值。

### 第五步：看上下文是不是过大

查看 `contexts` 和 `summary.max_context_chars`：

- `base_chars`：每次都会注入的基础规范字符数；
- `retrieved_chars`：召回分片正文字符数之和；
- `context_chars`：组装完成后的总上下文字符数，包含标题、分隔和来源说明；
- `retrieved_count`：进入组装阶段的分片数量。
- `injected_chunk_ids`：预算筛选后真正进入 Prompt 的 ID。检索到了但没有出现在这里的片段，不能作为最终回答引用。

一次精确模式请求可能有多个节点，因此会出现多条 context 记录。不要把每条都当成同一个 Prompt 的重复内容；应结合节点日志判断是哪次加载。

### 第六步：看耗时和 Token

`summary` 是快速总览：

- `retrieval_ms`：本请求各次 Loader 检索耗时之和；
- `llm_ms`：已纳入统一调用层或 Agent 调用层的耗时之和；
- `token_usage`：模型供应商返回的输入、输出与总 Token 累计值。

若供应商没有返回 usage，Token 会显示为 `0`，这表示“没有拿到统计”，不等于模型真的没有使用 Token。快速模式的 `agent_invoke` 耗时包含 Agent 工具循环；它比单次模型网络耗时范围更大，分析时要看 `mode`。

### 第七步：看门控有没有真的执行

查看 `gate_decisions`：

- `mode=observe`：`decision=reject` 只是一次“假如强制执行就会拒答”的观测，不会改变回答；
- `mode=enforce` 且 `enforced=true`：门控已经生效；知识问答会拒答，建筑生成会退回基础规范；
- `reason=threshold_not_calibrated`：没有生产阈值，系统选择安全放行；
- `best_distance`：本次语义命中的最小原始距离；`threshold` 是当时使用的阈值。

不要只统计 `decision=reject`。分析真实拒答率时必须同时检查 `enforced=true`。

### 第八步：核对引用、安全与反馈

- `citations[].cited_chunk_ids`：通过白名单校验的引用；
- `invalid_chunk_ids`：模型输出但不属于本次 Context 的伪造或错误 ID；
- `appended_fallback`：模型漏引时，系统是否补上了实际证据 ID；
- `safety`：内容安全的 `allowed/category/reason`，与知识不足拒答是两个概念；
- `feedback`：用户点赞或点踩，由 `/api/rag/feedback` 后写入，因此刚完成请求时可能还不存在。

排查“回答引用错了”时，应按 `retrievals[].hits → contexts[].injected_chunk_ids → citations[].cited_chunk_ids` 的顺序逐层核对。

## 5. 现在能用它判断什么

可以判断：

- 某次请求是否执行了检索；
- 查询规划和 metadata 过滤是否符合预期；
- 正确知识排在第几位、原始距离是多少；
- 上下文大小、检索耗时和模型开销是否异常；
- 同一问题在修改分片或 Embedding 前后的命中变化。

不能只凭 Trace 直接断言：

- 距离超过某个数就一定应该拒答；
- 召回正确就代表最终回答忠实；
- 引用存在就代表回答中的每句话都忠实于来源；
- 基础内容安全规则等价于生产审核供应商。

门控阈值仍需按生产 Embedding 校准；Faithfulness 需要 Judge 和人工抽查。

## 6. 隐私提醒

日志保存最多 300 字的脱敏查询预览。手机号、身份证号、邮箱和常见电话号码会在进入模型与日志前替换，但地址、人名等自由文本仍可能出现，因此仍应限制 Trace 文件的访问和保留范围。

## 7. 对应代码与测试

- 追踪数据结构与日志输出：`wild-server/app/agent/rag_trace.py`
- WebSocket 请求边界：`wild-server/app/api/ws_agent.py`
- Chroma ID、距离与上下文记录：`wild-server/app/spec/loader.py`
- LLM 耗时与 Token 记录：`wild-server/app/agent/llm_invocation.py`
- 快速模式 Agent 汇总：`wild-server/app/services/agent_service.py`
- 多文件指标汇总：`wild-server/app/agent/rag_reporting.py` 与 `wild-server/scripts/rag/summarize_rag_traces.py`
- 不连接真实数据库的单元测试：`wild-server/tests/rag/test_rag_trace.py`
