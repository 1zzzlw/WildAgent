# WildAgent 后端 LangGraph 重构学习文档

> 本次会话对 `wild-server` 的 LangGraph 编排层做了一次 8 步系统性重构，目标是把"快速/精密两套模式"里的重复代码收敛、把隐式脆弱条件换成显式契约、把散落的样板代码抽成共享服务。
>
> 全文按"**思路 → 改动 → 验证 → 学到什么**"组织，供后续学习和复现。
> 最终验证：`python -m pytest tests` → **249 passed, 17 subtests passed, 0 failed**（重构前基线为 236 passed）。

---

## 0. 先建立心智模型

在进入具体步骤前，先理解这个项目的三个核心设计（它们是所有改动的"为什么"）：

1. **`.wild` Blueprint 是唯一事实源**。AI 不生成 Three.js 代码，只生成带语义 ID 的参数化 JSON；`wild-core` 确定性重建几何。
2. **LLM 负责审美，程序负责易错的东西**。坐标、墙的朝向、构件配额、材质引用——这些模型最容易算错的东西，全部由确定性代码计算，模型只"填槽位"。
3. **确定性护栏 + 白名单修复 + 严格回滚**。任何 LLM 输出都要经过程序校验；修复只能从白名单工具里选，且在副本上执行、全量复检、不严格变好就回滚。

这次重构没有改变这套设计，而是**清理了实现层的重复与脆弱点**。

---

## 1. 步骤 1：建立固定评测基线

**思路**：重构前必须先有"对错标准"，否则做完只能判断"代码更整齐"，无法判断"有没有改坏"。

**改动**：
- 用 `uv add --dev pytest` 装上 pytest（项目此前依赖 uv 管理依赖，但 pytest 未声明为依赖）。
- 跑通完整测试套件，锁定基线：**236 passed, 17 subtests passed**。

**验证**：`python -m pytest tests -q` 输出 `236 passed`。

**学到什么**：基线先行是重构的第一原则。后面每一步都靠这 236→249 个测试作为回归护栏，任何一步改坏都会被立刻发现。

---

## 2. 步骤 2：抽取 `llm_invocation.py`（统一 LlmResult）

**思路**：6 个节点（skeleton / base_component / callback / chat / architecture / material_plan）各自复制了几乎相同的"调 LLM + 提取 reasoning_content / token_usage / finish_reason"样板代码，约 60 行 × 6 处。

**改动**：新建 `app/agent/llm_invocation.py`：

```python
@dataclass
class LlmResult:
    content: str
    reasoning: str
    token_usage: dict | None
    finish_reason: str | None

async def invoke_llm(llm, messages, on_reasoning_delta=None) -> LlmResult   # 非流式
async def stream_llm(llm, messages, on_reasoning_delta=None) -> LlmResult   # 流式
def collect_response(response) -> LlmResult                                  # 从已有响应收集
def merge_token_usage(*usages) -> dict | None                                # 合并多轮 token
```

6 个节点的 LLM 调用段全部替换成对这几个函数的调用。原来 skeleton 里 40 行的流式/非流式分支，现在变成：

```python
if use_streaming:
    llm_result = await stream_llm(llm, messages, on_reasoning_delta=lambda d: on_reasoning_delta("skeleton", d))
else:
    llm_result = await invoke_llm(llm, messages)
reply_text = llm_result.content
reasoning = llm_result.reasoning
token_usage = llm_result.token_usage
finish_reason = llm_result.finish_reason
```

**验证**：迁移导致一个测试 `test_token_usage_is_merged` 仍引用旧的 `skeleton_node._merge_token_usage`，改为引用 `llm_invocation.merge_token_usage` 后通过。

**学到什么**：把"模型供应商的响应差异"（`reasoning_content` 在 `additional_kwargs` 还是 `response_metadata`，usage 是 `prompt_tokens` 还是 `input_tokens`）隔离在一个适配层，业务节点不再关心供应商细节。这是适配器模式的典型用法。

---

## 3. 步骤 3：增加 `diagnostics.py`（稳定 Schema）

**思路**：诊断数据目前是自由 dict，字段名不一致；`validate_node` 用 `merge_diag.final_errors == 0` 这种隐式条件判断缓存是否可复用，脆弱。

**改动**：新建 `app/agent/diagnostics.py`：

- `blueprint_fingerprint(blueprint) -> str`：Blueprint 内容的 SHA-256 指纹（键序无关），用于"按内容判断校验结果是否可复用"。
- `VALIDATOR_VERSION = "1.0"`：校验器版本号，改校验逻辑时递增即可让旧快照失效。
- `ValidationSnapshot`：一次权威校验的结果快照（指纹 + 版本 + 结果 + 设计约束 + 结构化问题 + 数量 + 耗时 + 来源）。
- `NodeDiagnostic`：节点级诊断的目标 Schema（保留 `extra` 承载节点特有字段，保证前端兼容）。
- `step_result_to_dict`：把 `PipelineStepResult` 序列化。

**验证**：新增 `test_diagnostics.py`（7 个测试），覆盖指纹稳定性、快照 `matches()`、诊断扁平化。

**学到什么**：**显式契约优于隐式条件**。用"Blueprint 指纹 + 校验器版本"判断缓存，比"final_errors == 0"这种依赖隐式不变量的写法更可靠，也更容易读懂和维护。

---

## 4. 步骤 4：统一 IntentClassifier 与 WebSocket 事件适配

**思路**：这是本次重构里**唯一会改变用户可见行为**的重复——快速模式和精密模式用两套不同的意图判定，同一句话可能分流不一致。

**改动**（分两部分）：

**4a. 意图分类器**：新建 `app/agent/intent_classifier.py`，把 `classifier_node` 里的 LLM 提示词、关键词降级、归一化逻辑全部抽出：

```python
def classify_keywords(message, has_current_scene) -> str   # 确定性关键词降级
def normalize_intent(raw, message, has_current_scene) -> str
async def classify_intent(message, has_current_scene, llm=None) -> str   # LLM + 降级
```

`classifier_node` 变成薄封装，只调 `classify_intent`。这样快速/精密模式将来可复用同一套分类逻辑。

**4b. 事件适配器**：把 `ws_agent.py` 里两个 handler 各自定义的 `send_step` / `send_debug` / `send_thinking_delta` / `send_thinking_status` 闭包，收敛为 4 个模块级共享函数 `_emit_agent_step` / `_emit_debug_log` / `_emit_thinking_delta` / `_emit_thinking_status`。两个 handler 的闭包变成对共享函数的薄委托。

**验证**：`test_agent_graph_routing.py` 里对旧 `_keyword_classify`（返回大写）的断言改为对 `classify_keywords`（返回小写）的断言。事件形状保持不变（`_emit_thinking_delta` 在 `node` 为空时省略该字段，保持快速模式旧协议形状），全部测试通过。

**学到什么**：
1. **单一分类器**是消除"同一输入分流不一致"的关键，而不是让一个模式依赖另一个模式的节点。
2. 事件发射函数抽出后，**协议形状只在一处定义**，新增/改字段不会漏改某一套。

---

## 5. 步骤 5：迁移 State 字段（删双写）

**思路**：`GenerationState` 里同时存在两套字段——旧的 `door_fragments` 等分片字段，和新的通用 `component_fragments` / `component_diagnostics`（用 `Annotated` reducer 合并）。`base_component_node._component_state_update` 和 `callback_node._state_updates_from_candidate` 每次**双写**两套。

**改动**（安全渐进，符合"先删写侧、读侧留兜底"）：
- `_component_state_update` 停止写 legacy `config.output_key`（`door_fragments` 等），只写通用 `component_fragments` / `component_diagnostics`。
- `_state_updates_from_candidate` 停止写 `updates[config.output_key]`，直接写 `component_fragments`。
- **保留** `graph_state.py` 里的 legacy 字段声明（作为旧 checkpoint 的读侧兜底），并加注释标记为 deprecated。

**验证**：4 个测试断言了旧字段名（`result["door_fragments"]`），改为断言 `result["component_fragments"]["door"]` 后通过。

**学到什么**：
1. **状态迁移要分阶段**：写侧先停、读侧延迟删除（等旧 checkpoint 因 resume 生命周期自然清空），避免跨版本 resume 丢数据。
2. `checkpointer` 是 SQLite 持久化的（`storage/sessions/langgraph_checkpoints.sqlite3`），所以旧字段不能一删了之。

---

## 6. 步骤 6：重构校验边界（ValidationSnapshot）

**思路**：`merge` → `final_validate` → `callback` → `final_validate` 的校验链路里，`final_validate` 复用 `merge` 结果靠的是 `merge_diag.final_errors == 0` 这个隐式条件，callback 已经对候选蓝图做过全量复检，但回到 `final_validate` 时还要重跑一遍。

**改动**：
- `merge_node` 在 `merge_diag` 里记录 `blueprint_fingerprint`。
- `validate_node` 的缓存判断改为**指纹比较**：先看 `state["validation_snapshot"]`（callback 携带）是否匹配当前 Blueprint 指纹，再看 `merge_diag` 指纹是否匹配；匹配才复用，否则重跑。
- `validate_node` 跑完后构造 `ValidationSnapshot` 存入 `validation_snapshot`。
- `callback_node` 修复被接受后，把候选蓝图的全量复检结果（含设计约束）打包成 `ValidationSnapshot` 携带返回，供 `final_validate` 复用。

**验证**：`test_validation_cache.py` 的 `merge_diag` 补上 `blueprint_fingerprint` 字段后通过。

**学到什么**：**用内容指纹做缓存一致性判断**，比用"错误数 == 0"这类业务状态做代理更可靠——后者依赖"merge 无错 → 不会有 callback → 蓝图没变"这条隐式推理链，一旦链路加长就失效。

---

## 7. 步骤 7：RAG 检索缓存

**思路**：每个组件 `gen` 节点各自做 RAG 检索，相同的查询反复打 Chroma。缓存键要含**知识库版本**，否则改知识库后命中旧结果。

**改动**：在 `RAGSpecLoader` 里加内存缓存：
- 缓存键 = 规范化查询 + metadata_filter + per_query + 知识库版本（`_last_sync_stats` 的 total/updated/deleted）+ embedding 类名。
- `sync_index()` 改变索引内容后 `clear()` 缓存。
- 用 `getattr` 兜底，兼容测试里 `object.__new__` 构造的部分初始化对象。

**验证**：新增 `test_rag_retrieval_cache.py`（4 个测试），覆盖键稳定性、filter/per_query/知识库版本敏感性。修了一处 `object.__new__` 导致属性缺失的兼容问题后通过。

**学到什么**：
1. 缓存键必须包含"会改变结果的一切输入"，尤其是**数据版本**（这里用同步统计做知识库 revision 代理）。
2. "公共知识包 + 组件差异追加"（先整体检索一次、组件只追加差异）比朴素按 `(message, type)` 缓存更能消除跨组件重复——这是后续优化方向。

> **说明**：步骤 7 里"组件分组批量生成 A/B"未在本次落地。它需要真实模型跑多次、对比延迟/质量/token，属于需要线上 A/B 的实验，不是纯代码改动。设计上建议先试三组：`门/窗/凸窗`、`阳台/雨棚/栏杆/檐口`、`屋顶/烟囱/灯光`，且**只批量合并 `*_gen` 的 LLM 调用，`*_val` 和 callback 的 per-component 粒度必须保留**。

---

## 8. 步骤 8：原子写入 + 幂等提交单元

**思路**：`.wild` 文件此前用 `write_text` 直接写，进程中途退出会留下半写坏的文件；且会话/Turn/场景文件没有明确的提交单元。

**改动**：
- `save_blueprint_file_as` 改为**先写同目录临时文件，再 `os.replace` 原子替换**，杜绝半写坏文件。
- 新增 `commit_generation_result(session_id, request_id, blueprint, ...)`：生成结果的**单一幂等提交单元**，`session_id` 决定确定性文件名、`request_id` 是幂等键；`ws_agent.py` 两个 handler 的 `prepare_blueprint_delivery` 调用都换成它。

**验证**：新增 `test_generation_commit.py`（2 个测试），验证原子写入无临时文件残留、提交单元幂等委托。

**学到什么**：
1. **原子写 = 临时文件 + rename**，这是文件系统事务的最小实现。
2. 幂等提交靠**确定性文件名 + 幂等键**，而不是数据库事务；这让断线重放和部分失败后的重试变得安全。会话消息/Turn/checkpoint 的完整跨存储事务是后续扩展方向。

---

## 9. 核心设计思想总结（这次重构学到的最重要的东西）

1. **显式契约 > 隐式条件**：用 Blueprint 指纹判断缓存，而不是 `final_errors == 0`。
2. **适配层隔离供应商差异**：`LlmResult` 把 reasoning/usage 的提取差异关在一个模块里。
3. **单一来源**：分类器、事件发射、校验、提交各只留一处权威实现。
4. **渐进迁移**：State 字段"写侧先停、读侧延迟删"，不赌跨版本 checkpoint 兼容。
5. **确定性优先**：坐标/配额/材质引用由程序算，模型只填槽位——这条没变，但被这些清理强化了。

---

## 10. 验证方法与边界

**能做什么**（本次会话实测）：
- `cd wild-server && python -m pytest tests -q` → 249 passed。
- 依赖安装：`uv add --dev pytest`（把 pytest 补为 dev 依赖）。

**没做什么（边界，需你在真实环境补验）**：
- **前端 build**：本次改动全部在后端，未改任何前端文件；事件形状保持向后兼容（有测试覆盖），但仍建议你跑一次 `cd wild-web && npm run build` 确认。
- **真实模型生成**：步骤 7 的组件批量 A/B、步骤 1 里"分流不一致率/回退率/token"的线上量化，都需要真实 LLM API 跑多次，本次未执行。

---

## 11. 遗留与后续优先级

| 事项 | 为什么没做 | 建议 |
|---|---|---|
| 组件分组批量生成 A/B | 需真实模型多次运行对比 | 按第 7 节的三组拆分做实验，只批量 gen、保留 per-component val/retry |
| NodeDiagnostic 全量迁移 | 会触碰 ws_agent + 前端诊断消费，需前端 build 验证 | 定义已就位（`diagnostics.NodeDiagnostic`），后续逐步替换 `*_diag` dict |
| 分流不一致率线上量化 | 需真实分类器双跑 | 用 `intent_classifier.classify_intent` 与旧路径并排跑样本 |
| 会话/Turn/checkpoint/.wild 完整事务 | 跨 SQLite + JSON 文件 + 文件系统，需失败注入测试 | 在 `commit_generation_result` 上扩展，以 `request_id` 为幂等键 |

---

## 12. 关键文件索引

| 目标 | 文件 |
|---|---|
| 图编排 | `app/agent/graph.py` |
| 统一 LLM 调用层 | `app/agent/llm_invocation.py` |
| 诊断/校验快照 Schema | `app/agent/diagnostics.py` |
| 共享意图分类器 | `app/agent/intent_classifier.py` |
| 意图分类节点（薄封装） | `app/agent/nodes/classifier_node.py` |
| 校验节点（ValidationSnapshot） | `app/agent/nodes/validate_node.py` |
| 定向修复节点（携带快照） | `app/agent/nodes/callback_node.py` |
| 合并节点（记录指纹） | `app/agent/nodes/merge_node.py` |
| 组件节点工厂（去双写） | `app/agent/nodes/base_component_node.py` |
| RAG 加载器（检索缓存） | `app/spec/loader.py` |
| WebSocket（事件适配 + 提交单元） | `app/api/ws_agent.py` |
| 统一提交出口 | `app/services/agent_delivery.py` |
| 原子写入 | `app/utils/blueprint_parser.py` |
| 状态定义（字段迁移） | `app/agent/graph_state.py` |
