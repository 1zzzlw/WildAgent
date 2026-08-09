# WildAgent LangGraph 图拓扑总结

## 一、整体架构概览

WildAgent 的 LangGraph 模式（精密模式）采用**意图分类 + 分层并行生成架构**，通过 5 层节点实现：
- **闲聊/问答路径**：classifier → chat → END
- **建筑生成路径**：classifier → skeleton → gen→val 并行 → merge → final_validate → callback

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         LangGraph 完整流程图                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌──────────────┐                                                      │
│   │  classifier  │  Layer -1: 意图分类                                   │
│   │ (意图分类)   │  LLM 判断 GENERATE / CHAT                              │
│   └──────┬───────┘                                                      │
│          │                                                              │
│    ┌─────▼─────┐                                                        │
│    │_classifier│  条件路由:                                              │
│    │ _dispatch │  chat    → chat_node                                    │
│    └─────┬─────┘  generate → skeleton                                    │
│          │                                                              │
│    ┌─────┼──────────────────────┐                                       │
│    │     │                      │                                       │
│    ▼     │                      ▼                                       │
│ ┌──────┐ │              ┌──────────────┐                                │
│ │ chat │ │              │   skeleton   │  Layer 0: 骨架生成              │
│ │(问答)│ │              │  (骨架节点)  │  RAG + LLM → 骨架 + 组件建议     │
│ └──┬───┘ │              └──────┬───────┘                                │
│    │     │                     │                                        │
│    ▼     │              ┌──────▼──────┐                                 │
│   END    │              │ _dispatch_  │  条件路由:                        │
│          │              │ components  │  fail → END, merge → merge       │
│          │              └──────┬──────┘  send → [gen→val chains]         │
│          │                     │                                        │
│           │                                                              │
│    ╔══════╩══════════════════════════════════════════════════╗           │
│    ║          Send 动态并行派发 (Layer 1)                      ║           │
│    ║                                                          ║           │
│    ║  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐    ║           │
│    ║  │door_gen │  │window_  │  │roof_gen │  │railing_ │    ║           │
│    ║  │ →door_  │  │gen →    │  │ →roof_  │  │gen →    │    ║           │
│    ║  │  val    │  │window_  │  │  val    │  │railing_ │    ║           │
│    ║  │         │  │  val    │  │         │  │  val    │    ║           │
│    ║  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘    ║           │
│    ║       │            │            │            │          ║           │
│    ║  (另有 canopy, balcony, light, ramp, bay_window,      ║           │
│    ║   cornice, chimney 共 11 组 gen→val 链)                 ║           │
│    ╚═══════╤══════════════╤════════════╤════════════╤═══════╝           │
│            │              │            │            │                    │
│            └──────────────┴──────┬─────┴────────────┘                    │
│                                  │  (fan-in: 所有 val → merge)           │
│                          ┌───────▼───────┐                              │
│                          │    merge      │  Layer 2: 合并 + 校验 + 修复   │
│                          │  (合并节点)   │  - 收集所有组件分片             │
│                          │               │  - merge_fragments()          │
│                          │               │  - 校验→修复→循环 (最多3轮)    │
│                          │               │  - 发射 thinking_delta        │
│                          └───────┬───────┘                              │
│                                  │                                      │
│                          ┌───────▼───────┐                              │
│                          │ final_validate│  Layer 3: 最终校验             │
│                          │ (最终校验)    │  - 15步校验流水线              │
│                          │               │  - 追溯失败组件               │
│                          └───────┬───────┘                              │
│                                  │                                      │
│                          ┌───────▼───────┐                              │
│                          │ _final_validate│  条件路由:                    │
│                          │ _dispatch     │  - status=complete → END      │
│                          │               │  - status=partial  → callback │
│                          │               │  - 重试上限达     → END       │
│                          └───────┬───────┘                              │
│                                  │                                      │
│                    ┌─────────────▼─────────────┐                        │
│                    │      callback             │  Layer 4: 回调修复       │
│                    │  (LLM 重新生成失败组件)    │  - RAG 精准检索          │
│                    │                           │  - LLM 修正              │
│                    └─────────────┬─────────────┘                        │
│                                  │                                      │
│                                  └──→ merge (回到合并节点)               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 二、节点详解

### Layer -1: classifier（意图分类节点）

| 属性 | 值 |
|------|-----|
| **文件** | `app/agent/nodes/classifier_node.py` |
| **输入** | `user_message` |
| **输出** | `intent` ("generate" \| "chat") |

**职责：**
用轻量 LLM 调用快速判断用户意图：
- **GENERATE**：含"生成/建造/创建/设计"等关键词 → 路由到 skeleton
- **CHAT**：含"什么是/怎么/为什么/介绍一下"或纯闲聊 → 路由到 chat

**降级策略：** LLM 不可用时自动降级为关键词匹配。

### Layer -1: chat（知识问答节点）

| 属性 | 值 |
|------|-----|
| **文件** | `app/agent/nodes/chat_node.py` |
| **输入** | `user_message`, `on_reasoning_delta` |
| **输出** | `chat_reply`, `chat_diag` |

**职责：**
1. 多角度 RAG 检索（全局 + 建筑类型 + 构件参数 + 设计原则，4 条查询）
2. LLM 生成专业建筑领域知识回答
3. 流式推送回复内容到前端

### Layer 0: skeleton（骨架节点）

| 属性 | 值 |
|------|-----|
| **文件** | `app/agent/nodes/skeleton_node.py` |
| **输入** | `user_message`, `thinking_mode`, `on_reasoning_delta` |
| **输出** | `skeleton_blueprint`, `skeleton_summary`, `suggested_components`, `skeleton_diag` |

**职责：**
1. RAG 检索（3 条查询：建筑类型、配方、结构构件）
2. LLM 生成骨架结构（walls / floors / columns / beams）
3. 构建骨架摘要（含每面墙的建议开口方案）
4. 分析需要的组件类型，输出 `_components:` 行

**关键逻辑：**
- 流式模式下通过 `on_reasoning_delta("skeleton", delta)` 实时推送思考内容
- 骨架摘要 `_build_skeleton_summary()` 提供门/窗定位规则和每面墙的建议开口数量

### Layer 1: gen → val 组件链（并行）

| 属性 | 值 |
|------|-----|
| **文件** | `app/agent/nodes/base_component_node.py` |
| **工厂** | `create_component_generator(cfg)` / `create_component_validator(cfg)` |
| **注册表** | `app/agent/component_registry.py`（11 种组件） |

**已注册的 11 组 gen→val 链：**

| 组件类型 | 中文标签 | entity_type | is_list | is_element |
|----------|----------|-------------|---------|------------|
| door | 门 | opening | True | False |
| window | 窗 | opening | True | False |
| roof | 屋顶 | roof | False | True |
| railing | 栏杆 | railing | True | False |
| canopy | 雨棚 | canopy | True | False |
| balcony | 阳台 | balcony | True | False |
| light | 灯具 | light | True | False |
| ramp | 坡道 | ramp | True | False |
| bay_window | 凸窗 | bay_window | True | False |
| cornice | 檐口 | cornice | True | False |
| chimney | 烟囱 | chimney | True | False |

**gen 节点（生成器）：**
1. RAG 检索（entity_type + 组件规则 + 建筑类型上下文）
2. 构建 component prompt（含骨架摘要 + 组件专属规则）
3. LLM 流式调用（信号量限并发 = 3）
4. 提取 JSON，基本校验（类型匹配 + 必填字段）
5. 通过 `on_reasoning_delta(f"{type}_gen", delta)` 推送思考内容

**val 节点（校验器）：**
1. 将分片放入临时 Blueprint
2. 调用 `validate_component(type, blueprint)` 工具校验
3. 如有错误，调用 `fix_component(type, blueprint)` 自动修复
4. 返回修复后的分片

### Layer 2: merge（合并节点）—— 含校验+修复+循环

| 属性 | 值 |
|------|-----|
| **文件** | `app/agent/nodes/merge_node.py` |
| **输入** | `skeleton_blueprint` + 所有组件分片 |
| **输出** | `merged_blueprint`, `merge_diag` |

**流程：**
1. **收集分片**：遍历 COMPONENT_REGISTRY，收集所有已生成的组件
2. **合并**：调用 `merge_fragments(skeleton, fragments)` 合并为完整 Blueprint
3. **校验→修复→循环**（最多 3 轮）：
   - 执行 `run_validation_pipeline(merged_blueprint)` 完整 15 步校验
   - 如有错误，根据错误名映射到对应的 `fix_*` 工具自动修复
   - 循环直到全部通过或达到最大迭代次数
4. **思考过程**：每轮校验通过 `on_reasoning_delta("merge", ...)` 推送：
   - 收集到的分片摘要
   - 每轮校验的通过/警告/错误数
   - 修复工具执行结果
   - 最终状态

**fix 工具映射：**

| 校验器 | 修复工具 |
|--------|----------|
| validate_opening_coords | fix_opening_coords |
| validate_opening_fit | fix_opening_fit |
| validate_wall_junctions | fix_wall_junctions |
| validate_stair_alignment | fix_stair_alignment |
| validate_element_dimensions | fix_element_dimensions |
| validate_roof_coverage | fix_roof_coverage |

### Layer 3: final_validate（最终校验）

| 属性 | 值 |
|------|-----|
| **文件** | `app/agent/nodes/validate_node.py` |
| **输入** | `merged_blueprint` |
| **输出** | `validation_results`, `failed_components`, `passed_component_ids`, `status` |

**职责：**
1. 执行完整 15 步校验流水线
2. 将错误追溯到具体组件（`_trace_errors_to_components`）
3. 计算通过的组件 ID
4. 决定状态：`complete` / `partial` / `failed`

**15 步校验流水线：**

| 步骤 | 校验器 | 类型 |
|------|--------|------|
| 1 | validate_blueprint_structure | 结构校验 |
| 2 | validate_element_required_fields | 必填字段 |
| 3 | validate_reference_integrity | 引用完整性 |
| 4 | validate_opening_coords | 门窗坐标 |
| 4b | validate_opening_fit | 开口越界 |
| 5 | validate_wall_junctions | 墙体连接 |
| 6 | validate_stair_alignment | 楼梯对齐 |
| 7 | validate_roof_coverage | 屋顶覆盖 |
| 7b | validate_element_dimensions | 构件尺寸 |
| 8 | fix_opening_coords | 修正门窗坐标 |
| 8b | fix_opening_fit | 修正开口越界 |
| 8c | fix_stair_alignment | 修正楼梯对齐 |
| 8d | fix_element_dimensions | 修正构件尺寸 |
| 8e | fix_roof_coverage | 修正屋顶覆盖 |
| 8f | fix_wall_junctions | 修正墙体连接 |
| 9 | validate_collision | 碰撞检测 |

### Layer 4: callback（回调修复，可选）

| 属性 | 值 |
|------|-----|
| **文件** | `app/agent/nodes/callback_node.py` |
| **输入** | `failed_components`, `passed_component_ids`, `skeleton_summary` |
| **输出** | 修复后的组件分片（写回 state 对应字段） |

**流程：**
1. 对失败组件执行精准 RAG 检索
2. 构建 `build_callback_prompt`（含失败原因 + 当前参数 + 工具校验数据）
3. LLM 重新生成修正后的组件 JSON
4. 返回修正后的分片 → 回到 merge 节点重新合并

## 三、条件路由

### 路由 0: classifier → chat / skeleton

```python
def _classifier_dispatch(state):
    intent = state.get("intent", "generate")
    return "chat" if intent == "chat" else "skeleton"
```

### 路由 1: skeleton → dispatch / merge / END

```python
def _dispatch_components(state):
    if state.get("error") or state.get("status") == "failed":
        return "fail"  # → END
    suggested = state.get("suggested_components", [])
    if not suggested:
        suggested = _keyword_fallback(user_message)  # 关键词兜底
    if not suggested:
        return "merge"  # → 直接合并
    return [Send(f"{ct}_gen", state) for ct in suggested]  # → 并行派发
```

### 路由 2: final_validate → callback / END

```python
def _final_validate_dispatch(state):
    if status != "partial":
        return END  # 全部通过或全部失败 → 结束
    if retry_count >= max_retries:
        return END  # 全局重试上限 → 结束
    retryable = [fc for fc in failed_components
                 if component_retry_counts.get(fc["component_id"], 0) < max_retries]
    return "callback" if retryable else END
```

## 四、状态流转 (GenerationState)

```
用户输入
  ├── user_message: str
  ├── thinking_mode: bool
  ├── on_reasoning_delta: Callable
  │
  ├── [classifier] → intent: "generate" | "chat"
  │
  ├── [CHAT 路径]
  │   └── [chat] → chat_reply, chat_diag → END
  │
  └── [GENERATE 路径]
      ├── [skeleton] → skeleton_blueprint, skeleton_summary, suggested_components
      │
      ├── [gen→val × N] → door_fragments, window_fragments, roof_fragment, ...
      │                  + *_gen_diag, *_val_diag (诊断数据)
      │
      ├── [merge] → merged_blueprint, merge_diag (含校验迭代记录)
      │
      ├── [final_validate] → validation_results, failed_components, status
      │
      ├── [callback] → 修正后的组件分片 (写回 state)
      │
      └── [END] → final_blueprint
```

## 五、并发与限流

| 机制 | 位置 | 说明 |
|------|------|------|
| LLM 并发信号量 | `base_component_node.py` | `asyncio.Semaphore(3)`，最多 3 个组件同时调 LLM |
| Send 动态派发 | `graph.py` | LangGraph 原生并行，所有 gen 节点同时启动 |
| gen→val 串行 | `graph.py` | 每个组件的 gen 完成后才会进入 val |
| fan-in | `graph.py` | 所有 val 节点完成后才会进入 merge |

## 六、流式思考推送

每个节点通过 `on_reasoning_delta(node_name, delta)` 回调实时推送思考内容：

| 节点 | node_name | 推送内容 |
|------|-----------|----------|
| chat | `"chat"` | 知识问答的实时回复流 |
| skeleton | `"skeleton"` | 骨架规划的推理过程 |
| door_gen | `"door_gen"` | 门组件生成的推理过程 |
| window_gen | `"window_gen"` | 窗组件生成的推理过程 |
| ..._gen | `"{type}_gen"` | 各组件生成的推理过程 |
| merge | `"merge"` | 合并校验→修复循环的思考过程 |

前端 `AIChatPanel.vue` 接收 `thinking_delta` WebSocket 消息，按 `node` 字段分发到 `nodeThinkingMap`，每个节点可独立折叠/展开。

## 七、Token 消耗追踪

| 层级 | 机制 |
|------|------|
| 模型层 | `ReasoningChatOpenAI` 捕获流式 `usage` chunk + 非流式 `token_usage` |
| 节点层 | skeleton_node / base_component_node 在流式和非流式路径都捕获 `token_usage` |
| 诊断层 | 每个节点的 `*_diag` 包含 `token_usage: {input, output, total}` |
| 汇总层 | `ws_agent.py` 累加所有节点的 token 到 `total_tokens` |
| 前端层 | `agentStore.sessionMetrics.total_tokens` 显示总消耗 |

## 八、与 LangChain 模式对比

| 维度 | LangGraph（精密模式） | LangChain（快速模式） |
|------|----------------------|----------------------|
| 架构 | 4 层节点 + 并行分片 | 单体 Agent + 工具调用 |
| RAG | 每组件独立检索（2~3 条查询） | 8 条并行查询（全局） |
| 生成 | 每组件独立 LLM 调用 | 单次 LLM 调用生成全部 |
| 校验 | merge 内循环 + final_validate 15 步 | 单次校验流水线 |
| 修复 | merge 内 fix_* + callback LLM 修复 | fix_* 工具自动修复 |
| 思考 | 每节点独立流式推送 | 单流推送 |
| Token | 逐节点统计 | 全局统计 |
| 质量 | 组件级精细化（数量/位置约束） | 整体一致性更好 |
| 速度 | 较慢（多节点+并行等待） | 较快（单次调用） |

## 九、文件索引

| 文件 | 职责 |
|------|------|
| `app/agent/graph.py` | 图定义、路由、编译 |
| `app/agent/graph_state.py` | GenerationState TypedDict |
| `app/agent/model_client.py` | ReasoningChatOpenAI + create_llm |
| `app/agent/prompts.py` | skeleton/component/callback prompt |
| `app/agent/component_registry.py` | 11 种组件配置 + 专属规则 |
| `app/agent/nodes/classifier_node.py` | 意图分类（GENERATE/CHAT） |
| `app/agent/nodes/chat_node.py` | RAG 知识问答节点 |
| `app/agent/nodes/skeleton_node.py` | 骨架生成节点 |
| `app/agent/nodes/base_component_node.py` | gen/val 工厂 |
| `app/agent/nodes/merge_node.py` | 合并+校验+修复+循环 |
| `app/agent/nodes/validate_node.py` | 最终校验节点 |
| `app/agent/nodes/callback_node.py` | LLM 回调修复 |
| `app/services/agent_service.py` | 校验流水线 + LangChain 模式 |
| `app/tools/spatial_tools.py` | 18 个 validate/fix 工具 |
| `app/tools/component_tools.py` | 组件级 validate/fix 工具 |
| `app/api/ws_agent.py` | WebSocket 流式推送 |
