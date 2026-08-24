# WildAgent RAG 能力与演进规划

> 文档分类：RAG 专题。返回 [RAG 文档入口](README.md)。
>
> 最后核对：2026-08-24。本文明确区分“当前已实现”和“计划新增”，规划内容不代表已经交付。

## 1. 文档目的

本文回答三个问题：

1. 当前 WildAgent 的 RAG 已经具备哪些能力？
2. 在线查询阶段已经接入哪些门控、权限、引用和可观测能力，它们还有哪些生产配置边界？
3. 应该按什么顺序实施和验证，避免一次修改整条 Agent 链路？

状态约定：

- `已实现`：当前代码已经存在，并有源码或测试依据；
- `部分实现`：底层字段或局部能力存在，但尚未形成完整闭环；
- `计划新增`：尚未实现，不能写入对外功能说明。

## 2. 当前 RAG 的基础设计

当前核心仍然是标准向量 RAG：

```text
文档切片 → 文档向量化 → Chroma 索引
                         ↓
用户问题 → 查询向量化 → Top-K 检索 → 上下文组装 → Agent/LLM 生成
```

### 2.1 建立索引

```text
知识库 Markdown
  ↓ 合并 config.yaml、frontmatter、rag-meta
MarkdownChunker 按标题和业务实体切片
  ↓ 超长普通正文按 chunk_size 兜底，保护代码块和表格
SpecChunk：正文 + heading_path + source + entity metadata
  ↓ Embedding
Chroma：保存正文、向量和 metadata
```

`RAGSpecLoader.sync_index()` 采用增量同步：新增或正文变化的分片重新向量化；仅 metadata 变化时只更新 metadata；已失效的旧分片从当前 namespace 删除。

### 2.2 在线查询

```text
用户问题
  ↓ 建筑类型、配方、结构、墙、门、窗、栏杆、屋顶等检索意图
查询文本 + metadata 过滤
  ↓ 使用与索引兼容的 Embedding
Chroma 向量检索
  ↓ 按语义距离和知识成熟度排序、内容去重、补相邻 part
Top-K 知识片段
  ↓ 与基础规范一起组装 Prompt
architecture / skeleton / component / callback / chat 节点
  ↓
回答、Blueprint 或 ScenePatch
```

RAG Loader 的职责到“检索并组装知识上下文”为止。最终生成由 Agent/LLM 完成，因此召回正确不等于最终建筑一定正确。

## 3. 当前能力盘点

| 能力 | 状态 | 当前实现或边界 |
|---|---|---|
| Markdown 标题分片 | 已实现 | `MarkdownChunker` 读取 H1～H5，生成完整 `heading_path` |
| 长文本兜底分片 | 已实现 | 使用 `chunk_size/chunk_overlap`，代码块和表格优先保持原子性 |
| 路径与文档 metadata | 已实现 | 支持 `config.yaml`、frontmatter、`rag-meta` 的覆盖与继承 |
| Embedding | 已实现 | 正式配置使用真实 Embedding；HashEmbedding 只用于本地冒烟或显式降级 |
| Chroma 持久化与增量同步 | 已实现 | 支持新增、正文变更、metadata 更新和旧分片删除 |
| 多意图检索 | 已实现 | 建筑生成可拆成建筑类型、配方和关键组件查询 |
| metadata 与权限预过滤 | 已实现 | 默认条件与业务过滤之外，服务端 AccessContext 强制加入 public/tenant/department/clearance 条件，调用方不能覆盖 |
| 检索排序与去重 | 已实现 | 多取候选后按距离和知识成熟度排序，正文去重并补同一父章节相邻片 |
| 上下文预算 | 已实现 | 基础规范完整保留，RAG 片段按 `max_context_chars` 选择，不截断单片 |
| 检索缓存 | 已实现 | 相同多意图查询可复用结果；索引变化后清空缓存 |
| 同步状态检查 | 已实现 | `check_sync_status.py` 触发同步并打印总数、更新数和删除数 |
| 分片预览 | 已实现 | `inspect_knowledge_chunks.py` 使用生产 `MarkdownChunker` 展示真实分片 |
| 离线召回评测 | 已实现 | Golden Set 包含 60 道题，其中 32 道负样本；计算 Hit@K、Recall@K、MRR、距离与逐题明细 |
| `request_id` 与 RAGTrace | 已实现 | WebSocket 快速模式和精确模式都在请求边界建立 RAGTrace，检索、上下文和 LLM 记录使用同一 request_id |
| Trace 指标汇总 | 已实现 | 离线汇总空召回率、平均最佳距离、强制拒答率、P95 延迟、Token 与反馈；成本只按显式传入的模型单价估算 |
| Token 统计 | 已实现 | 统一 LLM 调用层记录 usage；快速模式汇总 Agent 消息中的 usage。供应商不返回 usage 时记为 0 |
| 检索距离与 chunk_id 日志 | 已实现 | Loader 保留真实 chunk_id/raw_distance；控制台输出且原子写入 `storage/sessions/rag_traces` |
| Retrieval Gate | 已实现、待生产校准 | 支持 off/observe/enforce；默认 observe 且阈值为空，真实 Embedding 校准前不会强制拒答 |
| 用户级权限过滤 | 已实现、待部署身份代理 | 共享密钥验证可信身份头；匿名只能读取 public，调用方权限字段会被移除 |
| 引用来源闭环 | 已实现 | Context 标记真实 chunk_id；伪造引用被清除，WebSocket 返回经过白名单校验的 cited_chunk_ids，聊天界面展示实际引用 |
| 用户反馈与在线质量监控 | 已实现 | 聊天界面的 👍/👎 通过 `/api/rag/feedback` 按 session_id/request_id 写回 Trace；评论写入前脱敏 |
| PII 脱敏与内容安全层 | 基础实现 | 常见手机号、身份证号、邮箱和电话在模型前脱敏；高置信安全规则兜底，不冒充完整审核服务 |
| LLM-as-Judge | 已实现、按需运行 | 固定 Prompt 版本和输出契约的离线脚本，不自动增加每次在线请求成本 |
| CI 质量门禁 | 已实现、待 CI 首跑 | GitLab 使用 60 题、临时 HashEmbedding 和固定阈值检查结构回归；生产 Embedding 需另存基线 |

## 4. 目标在线查询链路

当前已接入的目标链路：

```text
服务端认证得到 AccessContext
        ↓
强制权限预过滤
        ↓
用户问题 → 多意图查询规划 → 查询向量化
        ↓
Chroma：权限过滤 + 向量检索
        ↓
chunk_id + source + heading + distance + document
        ↓
Retrieval Gate
   ├─ 权限不允许 → 必须拒绝
   ├─ 证据不足   → 问答拒答；建筑生成按策略降级
   └─ 证据充足   → 构造带引用 Context
                              ↓
                         Agent / LLM
                              ↓
               回答或 Blueprint + 引用 + RAG 诊断
```

阶段三的可观测性、权限、评测和安全能力已经作为横切底座接入；生产阈值与可信身份头仍由部署配置决定。

## 5. 已落地能力与生产配置边界

### 5.1 检索结果契约与全链路追踪（步骤 0 已实现）

当前已建立统一 `RAGTrace`。observe 不改变生成行为；enforce 只有在配置已校准阈值时生效。已记录：

```text
request_id
query_intents
metadata_filters
retrieved chunk_ids、sources、headings、raw_distances
retrieval/context/LLM 各阶段耗时
context 字符数
LLM 输入、输出和总 Token 数
请求最终状态
session_id、非密钥 AccessContext
embedding/index_signature
gate_decision、引用、安全结论和反馈
```

Trace 文件位于 `storage/sessions/rag_traces/<session_id>/<request_id>.json`。日志字段和阅读方法见 [RAGTrace 日志阅读指南](RAG_TRACE_GUIDE.md)。

查询预览最多 300 字。常见联系方式和证件号已经自动替换，但自由文本中的人名和地址仍需要受控日志权限与保留周期。

### 5.2 权限预过滤

已支持的权限 metadata：

```text
tenant_id
department
clearance_level
namespace
status
authority
access_scope
```

权限条件由服务端验证共享密钥后的身份头生成。Loader 会移除调用方传入的保留权限字段，再强制合并 AccessContext；业务调用方只能增加普通业务过滤，不能移除安全过滤。

当前 `namespace=wild_spec` 是逻辑索引隔离字段，不应在没有设计迁移方案时直接拿它代替 tenant 或 department。

### 5.3 Retrieval Gate

门控位置在向量检索之后、构造 Prompt 之前，当前支持：

```yaml
rag:
  retrieval_gate:
    mode: observe       # off / observe / enforce
    max_distance: null  # 通过评测校准后填写
```

不能直接照搬“相似度低于 0.45”。当前 Loader 返回的是 `distance`，通常越小越相关，而且数值范围取决于 Embedding、距离算法和索引配置。应先记录真实分布，再确定阈值，并同时保留：

```text
raw_distance
adjusted_rank_score
gate_threshold
gate_decision
gate_reason
```

门控策略需要区分场景：

- 知识问答：证据不足可以返回“知识库中暂无可靠信息”；
- 建筑生成：单个可选组件意图没有命中时不应拒绝整个任务，可回退到基础规范；
- 权限不允许：必须拒绝，不能回退到未授权知识；
- 多意图查询：按必要意图和可选意图分别判断，不能只看所有结果中的一个全局最高分。

先使用 `observe` 模式记录“如果启用会怎样”，验证错误拒答率后再切换 `enforce`。

### 5.4 带来源的 Context 和输出引用

注入 Prompt 的每个分片使用稳定标签：

```text
[chunk_id=wild_spec:...]
来源：components/windows-supported.md
知识路径：基础静态窗组合构件 > 当前支持的基础静态窗 > 参数契约
正文：……
```

问答结果可以返回：

```json
{
  "answer": "……",
  "cited_chunk_ids": ["wild_spec:..."],
  "evidence_status": "supported"
}
```

引用必须通过确定性校验：模型给出的 `chunk_id` 必须属于本次真正注入的 Context。建筑生成结果不把诊断字段写进 `.wild`，而是通过 WebSocket 事件或生成结果旁路 metadata 返回。

LLM 自报的 `confidence` 没有经过校准，不能单独充当安全门禁。它最多作为界面提示，硬门控优先使用权限结果、检索证据和确定性验证。

### 5.5 离线与在线质量评估

当前固定集为60道题，其中28道建筑知识正样本、32道跨领域负样本。后续新增题目仍不能为凑数量而重复改写。当前及后续需要覆盖：

- 建筑类型、配方和各类组件；
- 单来源与多来源问题；
- 模糊问题和完全无关问题；
- 应拒答、应降级和不应拒答的问题；
- 权限允许与权限拒绝问题；
- 容易误召回 `proposed/inferred` 的问题。

保留现有 Hit@K、Recall@K、MRR，并增加：

- Gate 正确拒答率；
- Gate 错误拒答率；
- 越权召回率，目标必须为0；
- 引用正确率和引用覆盖率；
- Context Faithfulness；
- 最终 Blueprint 确定性校验通过率。

LLM-as-Judge 只作为辅助信号。Judge 模型、Prompt 和版本必须记录，并保留人工抽查，不能用单一模型分数替代确定性门禁。

### 5.6 PII 与内容安全

- 用户问题发送给外部 Embedding 或 LLM 前，根据业务要求进行脱敏；
- 日志写入前再次脱敏，避免原始敏感信息进入长期存储；
- PII 检测工具需要验证中文手机号、身份证号、地址等实际召回影响；
- 内容安全拒答与“知识库证据不足”使用不同的 decision/reason；
- 不把简单敏感词列表当成完整安全系统，避免误判和绕过。

## 6. 实施顺序与验收标准

以下步骤按顺序执行。后一步必须建立在前一步已经实现、产生基线数据并通过回归测试的基础上，不并行跳过阈值校准直接开启强制拒答。

| 步骤 | 工作 | 验收标准 |
|---|---|---|
| 0（已完成） | `RAGTrace` 和距离日志 | 每个 request_id 能定位查询、过滤、chunk_id、原始距离、耗时和 Token；只增加观测，不改变当前回答 |
| 1（已完成） | Retrieval Gate `observe` 模式 | 计算并记录门控结论，但不真正拒答；评测报告能统计假设拒答结果 |
| 2（工具与题集已完成） | 离线负样本与阈值校准 | 60 题含 32 个负样本，校准器输出阈值、错误拒答/放行率和索引签名；生产报告需在目标 Embedding 环境运行 |
| 3（已实现、默认未启用） | Retrieval Gate `enforce` 模式 | 问答证据不足拒答，建筑生成降级；阈值为空时安全放行，不使用猜测阈值 |
| 4（已完成） | `chunk_id` 引用闭环 | 输出引用全部属于实际注入的 Context，错误或伪造引用被确定性清除 |
| 5（已完成、待部署密钥） | 用户身份和权限过滤 | 服务端产生 AccessContext；匿名仅 public，调用方不能覆盖强制过滤 |
| 6（已完成、待 CI 首跑） | 50～100题评测集及 CI 门禁 | 60 题和 GitLab 门禁已接入，报告作为 CI artifact 保存 |
| 7（基础能力已完成） | PII、反馈、LLM-as-Judge 和内容安全 | 模型前脱敏、反馈关联、Judge 版本化和安全原因区分均已实现；生产审核服务仍可后续接入 |

每个阶段先写失败用例，再实现功能，并保证原有 RAG 分片、索引同步和召回测试继续通过。

## 7. 不应混淆的边界

- `检索成功` 不等于 `Agent 正确使用知识`；
- `没有空召回` 不等于 `召回内容正确`；
- `HashEmbedding 测试通过` 不等于 `真实中文语义召回良好`；
- `LLM confidence 高` 不等于回答可信；
- `用户声称自己属于某部门` 不等于已通过权限认证；
- `安全拒答`、`权限拒绝`、`证据不足拒答` 必须记录为不同原因。

## 8. 相关代码与操作入口

- 当前分片、同步和检索：[loader.py](../../wild-server/app/spec/loader.py)
- Agent 上下文注入：[agent_service.py](../../wild-server/app/services/agent_service.py)
- 固定评测集：[rag_retrieval_cases.json](../../wild-server/evals/rag_retrieval_cases.json)
- RAG 脚本入门：[scripts/rag/README.md](../../wild-server/scripts/rag/README.md)
- 当前全链路细节：[RAG_PIPELINE_GUIDE.md](RAG_PIPELINE_GUIDE.md)
- RAGTrace 日志阅读：[RAG_TRACE_GUIDE.md](RAG_TRACE_GUIDE.md)
- 在线门控与安全配置：[RAG_RUNTIME_CONTROLS.md](RAG_RUNTIME_CONTROLS.md)
