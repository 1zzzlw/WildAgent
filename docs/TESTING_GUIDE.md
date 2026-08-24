---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 120c9aab85e3ed979ff6cbda3bbcb633_7e8cf1139b6d11f19bec525400826444
    ReservedCode1: +DaqhpUJw30jArsxCBAWSNCMs6qQ7OlrtS8+gOHyXOWO1kQrCXCL9i1i6jRzzJCvX1m1KhgP4W2Kl2aztIeT4G3xqdO+X6xJXspSsUkPyL8bBZ06Tt6L5xGbAVxDW86t/be8HCwdJGVtg1Cm8zHOBBcWgUcqPGxW3khEhBwK6NkxytAA+BFfxIrz9uI=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 120c9aab85e3ed979ff6cbda3bbcb633_7e8cf1139b6d11f19bec525400826444
    ReservedCode2: +DaqhpUJw30jArsxCBAWSNCMs6qQ7OlrtS8+gOHyXOWO1kQrCXCL9i1i6jRzzJCvX1m1KhgP4W2Kl2aztIeT4G3xqdO+X6xJXspSsUkPyL8bBZ06Tt6L5xGbAVxDW86t/be8HCwdJGVtg1Cm8zHOBBcWgUcqPGxW3khEhBwK6NkxytAA+BFfxIrz9uI=
---



---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 120c9aab85e3ed979ff6cbda3bbcb633_c400aa4b9ae411f1a98a525400f8a581
    ReservedCode1: 1JFwAbOaiMmFh1YQ11YR0ShF3ASJekLNalpedEM/8/2sThLk0/HQ17yAyiciHjhckv9xv9I+Rx1CXuRMLpECexZfnnYq23Ixa1F16VuCEluYMLkrz6pIhJ5gfdoB66T/FCgFM2sCmLb5Q5NzwNvkSUO8S4/kIzeg/JQc3eCgHxKygRitFSSEn1bfLAY=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 120c9aab85e3ed979ff6cbda3bbcb633_c400aa4b9ae411f1a98a525400f8a581
    ReservedCode2: 1JFwAbOaiMmFh1YQ11YR0ShF3ASJekLNalpedEM/8/2sThLk0/HQ17yAyiciHjhckv9xv9I+Rx1CXuRMLpECexZfnnYq23Ixa1F16VuCEluYMLkrz6pIhJ5gfdoB66T/FCgFM2sCmLb5Q5NzwNvkSUO8S4/kIzeg/JQc3eCgHxKygRitFSSEn1bfLAY=
---

# WildAgent 测试文件说明

本文档详细介绍 `wild-server/tests/` 目录下所有测试文件的作用、测试内容和使用方法。

---

## 📋 目录

- [测试运行指南](#测试运行指南)
- [测试文件分类](#测试文件分类)
- [详细测试说明](#详细测试说明)
- [RAG 分片检查脚本](#rag-分片检查脚本)
- [🎯 测试策略](#-测试策略)

---

## 测试运行指南

### 环境准备

```bash
# 1. 激活虚拟环境
.\.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# 2. 设置 PYTHONPATH
$env:PYTHONPATH="."  # Windows PowerShell
export PYTHONPATH=.  # Linux/Mac
```

### 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 按子包运行（tests/ 下按功能分包，共 9 个：agent/components/rag/blueprint/validators/repair/network/assets/misc）
python -m pytest tests/rag -v
python -m pytest tests/agent -v

# 运行单个测试文件
python -m pytest tests/rag/test_rag_semantic_chunking.py -v

# 运行特定测试方法
python -m pytest tests/rag/test_rag_semantic_chunking.py::RAGSemanticChunkingTest::test_heading_path_and_entity_metadata_reach_every_length_part -v

# 安静模式（只显示失败）
python -m pytest tests/ -q

# 显示详细输出
python -m pytest tests/ -vv

# 停止于第一个失败
python -m pytest tests/ -x

# 运行失败的测试
python -m pytest tests/ --lf

# 并行运行（需要 pytest-xdist）
python -m pytest tests/ -n auto
```

---

## 测试文件分类

`wild-server/tests/` 目录按功能领域划分为 9 个子包，每个子包下有独立 `README.md` 介绍用途与运行方法：

```text
tests/
├── agent/        核心流程测试（Agent 图执行、路由、结果交付）
├── components/   组件生成测试（组件蓝图、状态合并、架构规划等）
├── rag/          RAG 检索测试（语义分片、索引同步、检索缓存、查询规划）
├── blueprint/    Blueprint 处理测试（归一化、文本提取、材质验证）
├── validators/   验证器测试（P0/P1/P2 优化、空间验证、验证缓存）
├── repair/       修复工具测试（回调定向修复、合并精度、骨架恢复）
├── network/      网络和会话测试（WebSocket、会话轮次、生成任务服务）
├── assets/       材质和资产测试（材质调优、PBR 资产、模型客户端兼容）
├── misc/         其他工具测试（诊断、就绪、推理流、Prompt 组合等）
├── artifacts/    测试资产目录（.wild 样例文件，不参与收集）
└── README.md     顶层说明（本文件）
```

### 🎯 agent/ 核心流程测试（3个）
- `test_agent_graph_execution.py` - Agent 图执行
- `test_agent_graph_routing.py` - Agent 路由
- `test_agent_delivery.py` - 结果交付

### 🧩 components/ 组件生成测试（6个）
- `test_component_blueprint.py` - 组件蓝图
- `test_component_state_reducer.py` - 状态合并
- `test_component_validation_recheck.py` - 验证重检
- `test_architecture_plan.py` - 架构规划
- `test_facade_recipe.py` - 立面配方
- `test_material_plan.py` - 材质规划

### 📚 rag/ RAG 检索测试（4个）
- `test_rag_semantic_chunking.py` - 语义分片
- `test_rag_index_sync.py` - 索引同步
- `test_rag_retrieval_cache.py` - 检索缓存
- `test_query_planner.py` - 查询规划

### 📝 blueprint/ Blueprint 处理测试（3个）
- `test_blueprint_normalizer.py` - Blueprint 归一化
- `test_blueprint_text_extraction.py` - 文本提取
- `test_blueprint_material_validation.py` - 材质验证

### ✅ validators/ 验证器测试（6个）
- `test_p0_implementation.py` - P0 优化（结构自检、查询改写）
- `test_p1_p2_implementation.py` - P1/P2 优化（事实/工具/推理自检）
- `test_spatial_validation.py` - 空间验证
- `test_spatial_invariants.py` - 空间不变量
- `test_validation_cache.py` - 验证缓存
- `test_validation_pipeline_repairs.py` - 验证管道修复

### 🔧 repair/ 修复工具测试（4个）
- `test_callback_targeted_repair.py` - 回调定向修复
- `test_targeted_repair_tools.py` - 定向修复工具
- `test_merge_precision.py` - 合并精度
- `test_skeleton_blueprint_recovery.py` - 骨架恢复

### 🌐 network/ 网络和会话测试（4个）
- `test_ws_agent_disconnect.py` - WebSocket 断线
- `test_session_turns.py` - 会话轮次
- `test_generation_job_service.py` - 生成任务服务
- `test_generation_commit.py` - 生成提交

### 🎨 assets/ 材质和资产测试（3个）
- `test_material_tuning.py` - 材质调优
- `test_pbr_assets.py` - PBR 资产
- `test_model_client_compat.py` - 模型客户端兼容性

### 📊 misc/ 其他测试（8个 + 1 个辅助脚本）
- `test_diagnostics.py` - 诊断工具
- `test_readiness.py` - 就绪检查
- `test_reasoning_stream.py` - 推理流
- `test_prompt_composition.py` - Prompt 组合
- `test_scene_patch_generation.py` - 场景补丁生成
- `test_ip_geolocation.py` - IP 地理定位
- `test_deployment_preflight.py` - 部署预检
- `test_langgraph_checkpoint_resume.py` - LangGraph 断点恢复
- `show_langgraph_graph.py` - LangGraph 图展示辅助脚本（非测试）

---

## 详细测试说明

### 1. test_agent_graph_execution.py
**作用**：测试 LangGraph Agent 执行流程

**测试内容**：
- Agent 图节点执行顺序
- 状态传递和更新
- 错误处理和恢复

**关键测试**：
- `test_simple_generation_flow` - 简单生成流程
- `test_validation_and_repair_loop` - 验证和修复循环
- `test_state_persistence` - 状态持久化

**使用场景**：验证 Agent 核心执行逻辑

---

### 2. test_agent_graph_routing.py
**作用**：测试 Agent 图路由决策

**测试内容**：
- 意图分类路由
- 条件分支选择
- 循环退出条件

**关键测试**：
- `test_building_generation_route` - 建筑生成路由
- `test_chat_route` - 聊天路由
- `test_patch_generation_route` - 补丁生成路由
- `test_validation_loop_routing` - 验证循环路由

**使用场景**：验证路由逻辑正确性

---

### 3. test_agent_delivery.py
**作用**：测试 Agent 结果交付机制

**测试内容**：
- 流式输出格式
- 增量更新
- 错误消息传递

**关键测试**：
- `test_streaming_blueprint_delivery` - 流式蓝图交付
- `test_thinking_panel_updates` - 思考面板更新
- `test_error_delivery` - 错误交付

**使用场景**：验证前端交互体验

---

### 4. test_rag_semantic_chunking.py
**作用**：测试知识库语义分片功能

**测试内容**：
- Markdown 标题分片
- 实体 metadata 继承
- 长度回退策略
- JSON/表格结构完整性

**关键测试**：
```python
test_heading_path_and_entity_metadata_reach_every_length_part()
# 验证：
# - 每个分片都包含完整的标题路径
# - entity metadata 正确继承到子片段
# - parent_chunk_id 一致性

test_length_fallback_keeps_json_and_table_structurally_complete()
# 验证：
# - JSON 代码块不被截断
# - 表格结构保持完整
# - 回退策略正确触发

test_readme_is_inferred_as_index_scope()
# 验证：
# - README.md 自动标记为 index 类型
# - doc_scope 正确设置

test_empty_container_heading_is_not_indexed()
# 验证：
# - 空容器标题（如"二、公共建筑"）不进入检索索引

test_body_hash_ignores_repeated_knowledge_path_prefix()
# 验证：
# - 跨文件去重逻辑
# - content_hash vs body_hash

test_retrieve_combines_namespace_scope_and_business_filters()
# 验证：
# - 检索时 namespace / doc_scope / status / authority 与业务过滤组合

test_context_limit_keeps_retrieved_chunks_atomic()
# 验证：
# - 上下文长度上限按分片边界截断，不切开 JSON 代码块
```

**使用场景**：
- 验证知识库分片质量
- 确保 RAG 检索效果
- 调试分片配置

**运行方法**：
```bash
python -m pytest tests/rag/test_rag_semantic_chunking.py -v
```

---

### 5. test_rag_index_sync.py
**作用**：测试 Chroma 索引增量同步与检索排序

**测试内容**：
- 权威性加权排序
- 多查询批量检索
- 相邻父分片上下文扩展
- 增量同步（跳过未变更、更新 metadata、替换变更分片、清理删除文档）

**关键测试**：
- `test_supported_maintainer_chunk_can_outrank_nearby_experimental_chunk` - 权威性加权排序
- `test_retrieve_many_keeps_one_result_per_query` - 多查询各返回一个结果
- `test_retrieve_many_expands_adjacent_parent_parts` - 相邻父分片扩展
- `test_unchanged_chunks_skip_embedding_upsert` - 未变更分片跳过 embedding
- `test_metadata_change_updates_without_reembedding` - metadata 变更不重新 embedding
- `test_changed_chunk_deletes_old_id_and_upserts_new_id` - 变更分片删除旧 ID 并写入新 ID
- `test_removed_document_deletes_stale_chunks` - 删除文档清理旧分片

**使用场景**：验证知识库同步机制

**运行方法**：
```bash
python -m pytest tests/rag/test_rag_index_sync.py -v
```

---

### 6. test_rag_retrieval_cache.py
**作用**：测试 RAG 检索缓存键生成稳定性

**测试内容**：
- 相同输入缓存键稳定
- filter / per_query 变化导致缓存键变化
- 知识库版本变化导致缓存键变化

**关键测试**：
- `test_cache_key_is_stable_for_identical_input` - 相同输入缓存键稳定
- `test_cache_key_changes_with_filter` - filter 变化键变化
- `test_cache_key_changes_with_per_query` - per_query 变化键变化
- `test_cache_key_changes_with_knowledge_base_revision` - 知识库版本变化键变化

**使用场景**：验证缓存命中正确性，避免脏缓存

---

### 7. test_query_planner.py
**作用**：测试查询规划和改写

**测试内容**：
- 别名识别和扩展
- Metadata 过滤构建
- 查询改写逻辑

**关键测试**：
- `test_build_plan_resolves_commercial_alias_without_inventing_facts` - 别名解析
- `test_explicit_filter_wins_over_inferred_component_type` - 显式过滤优先
- `test_loader_retrieve_many_with_metadata_filter` - Metadata 过滤
- `test_index_enrichment_removed_in_refactor` - 重构验证

**使用场景**：验证查询规划正确性

---

### 8. test_blueprint_normalizer.py
**作用**：测试 Blueprint 归一化器

**测试内容**：
- 未知字段剥离
- 坐标漂移修复
- 默认值填充
- Schema 验证

**关键测试**：
- `test_strip_unknown_fields` - 未知字段剥离
- `test_fix_coordinate_drift` - 坐标漂移修复
- `test_fill_default_values` - 默认值填充
- `test_fix_opening_fit_negative_width` - 负宽度修复

**使用场景**：
- 修复前后端 schema 不一致
- 降低 Blueprint 解析失败率

**运行方法**：
```bash
python -m pytest tests/blueprint/test_blueprint_normalizer.py -v
```

---

### 9. test_p0_implementation.py
**作用**：测试 P0 优化方案（快速见效）

**测试内容**：
- **结构自检**：验证 JSON 格式和 schema 合规性
- **查询改写**：优化 RAG 检索查询
- **领域配置**：外部化领域知识

**关键测试**：
```python
test_structure_validator_detects_json_errors()
# 验证：识别 JSON 格式错误

test_structure_validator_detects_schema_violations()
# 验证：识别 schema 违规

test_query_rewriter_expands_technical_terms()
# 验证：技术术语扩展

test_domain_config_loads_successfully()
# 验证：领域配置加载
```

**使用场景**：
- 验证 P0 优化效果
- 测试结构验证逻辑
- 确认查询改写质量

**运行方法**：
```bash
python -m pytest tests/validators/test_p0_implementation.py -v
```

---

### 10. test_p1_p2_implementation.py
**作用**：测试 P1/P2 优化方案（系统优化）

**测试内容**：
- **P1 - 事实自检**：验证实体参数范围
- **P1 - 混合检索**：向量 + BM25 检索
- **P2 - 工具自检**：诊断工具调用错误
- **P2 - 推理自检**：检测推理矛盾

**关键测试**：
```python
# 事实自检
test_validate_entity_pass() - 合法实体验证
test_validate_entity_range_violation() - 范围违规检测
test_auto_correct_clamp() - 自动修正

# 混合检索
test_hybrid_retriever_initialization() - 混合检索器初始化
test_get_stats() - 统计信息

# 工具自检
test_diagnose_tool_error() - 工具错误诊断

# 推理自检
test_validate_reasoning_consistent() - 推理一致性验证
test_validate_reasoning_inconsistent() - 推理矛盾检测
```

**使用场景**：
- 验证高级优化功能
- 测试自检和自修复能力

**运行方法**：
```bash
python -m pytest tests/validators/test_p1_p2_implementation.py -v
```

---

### 11. test_spatial_validation.py
**作用**：测试空间几何验证

**测试内容**：
- 组件重叠检测
- 边界溢出检测
- 父子关系验证
- 最小尺寸检查

**关键测试**：
- `test_detect_wall_overlap` - 墙体重叠检测
- `test_detect_out_of_bounds_component` - 边界溢出检测
- `test_validate_parent_child_relationship` - 父子关系验证

**使用场景**：确保生成结果空间合理性

---

### 12. test_ws_agent_disconnect.py
**作用**：测试 WebSocket 断线重连

**测试内容**：
- 连接断开检测
- 自动重连机制
- 消息队列恢复
- 状态同步

**关键测试**：
- `test_reconnect_on_disconnect` - 断线重连
- `test_message_queue_recovery` - 消息恢复
- `test_heartbeat_mechanism` - 心跳机制

**使用场景**：验证网络稳定性

---

### 13. test_session_turns.py
**作用**：测试会话轮次管理

**测试内容**：
- 多轮对话状态
- 上下文累积
- 会话持久化

**关键测试**：
- `test_multi_turn_context` - 多轮上下文
- `test_session_persistence` - 会话持久化
- `test_turn_history_limit` - 历史限制

**使用场景**：验证对话连续性

---

### 14. test_material_tuning.py
**作用**：测试材质参数调优

**测试内容**：
- PBR 材质参数验证
- 颜色值归一化
- 材质冲突检测

**关键测试**：
- `test_pbr_parameter_validation` - PBR 参数验证
- `test_color_normalization` - 颜色归一化
- `test_material_conflict_detection` - 冲突检测

**使用场景**：确保材质参数合理性

---

### 15. show_langgraph_graph.py
**作用**：可视化 LangGraph 流程图

**功能**：
- 生成 Agent 图的可视化
- 导出为 HTML/PNG
- 方便理解执行流程

**使用方法**：
```bash
python tests/misc/show_langgraph_graph.py
```

**输出**：在 `storage/` 目录生成可视化文件

---

## 🧰 RAG 分片检查脚本

除 pytest 测试文件外，`wild-server/scripts/` 下提供两个 RAG 分片检查脚本，用于直接观察知识库 Markdown 文件的分片效果，辅助验证分片策略与调试检索问题。

### inspect_knowledge_chunks.py（分片信息检查）

**用途**：调用 `app/spec/loader.py` 中的 `MarkdownChunker`，对单个文件或整个目录执行分片，将分片结果以表格或明细形式打印到控制台。

**运行方式**（uv 环境激活后）：

```bash
cd wild-server
.\.venv\Scripts\activate        # Windows PowerShell
$env:PYTHONPATH="."             # 让脚本可以 import app.spec.loader
python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --table
```

或使用 uv run（免手动激活）：

```bash
$env:PYTHONPATH="."
uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --table
```

**常用参数**：`--namespace`（默认 test）、`--chunk-size`（默认 900）、`--chunk-overlap`（默认 150）、`--table`（表格输出）、`--show-content`（显示完整内容）、`--limit N`（限制处理文件数）、`--no-summary`（跳过统计摘要）、`--output <file>`（自定义 Markdown 报告路径，默认 `scripts/reports/inspect_chunks_<时间戳>.md`）、`--log-output <file>`（自定义控制台日志路径，默认 `scripts/reports/chunks_console_<时间戳>.txt`）、`--no-log-output`（关闭控制台日志保存，默认启用）。

**输出内容**：分片信息表（序号 / 文件 / 实体 / 类型 / 长度）、标题路径列表、长度统计（最小 / 最大 / 平均 / 中位数）、按文件 / 实体 / 文档类型分组统计。

**文件输出**（默认启用）：控制台全部输出通过 Tee 双写逐行保存到 `scripts/reports/chunks_console_<时间戳>.txt`，同时生成 Markdown 检查报告 `scripts/reports/inspect_chunks_<时间戳>.md`（分片信息表 + 标题路径 + 统计分析），目录不存在自动创建；可用 `--output` / `--log-output` 自定义路径、`--no-log-output` 关闭日志保存。

### inspect_chunks_demo.py（分片展示报告，本次新增）

**用途**：在控制台打印每个分片的来源、数量、字符数、内容摘要与合法性检查结果，同时将同样的展示信息写入 Markdown 报告文件，便于直观分享分片效果；控制台输出默认同时保存为独立日志文件，避免终端滚动展示不全。

**运行方式**（uv 环境激活后）：

```bash
cd wild-server
.\.venv\Scripts\activate        # Windows PowerShell
$env:PYTHONPATH="."
python scripts/rag/inspect_chunks_demo.py storage/knowledge_base/building_types/residential/villas.md
```

**常用参数**：`--chunk-size` / `--chunk-overlap`（分片配置）、`--limit N`（目录模式限制文件数）、`--output <file>`（自定义报告输出路径，默认 `scripts/reports/chunks_report_<时间戳>.md`）、`--show-full`（分片内容全文展示，默认截断摘要）。

**控制台日志保存**（默认启用）：
- 运行时的全部控制台输出（每个分片详细信息 + 统计汇总）通过 Tee 双写逐行保存到独立日志文件，默认 `scripts/reports/chunks_console_<时间戳>.txt`，与 Markdown 报告互不干扰
- `--log-output <file>`：自定义日志保存路径
- `--no-log-output`：关闭控制台日志保存（仅控制台展示 + Markdown 报告）

**输出内容**：
- 控制台：每个分片的 ID、来源、标题路径、实体、类型、长度、状态、权威性、合法性（✅/❌）、内容摘要，以及按分组展示的补充 metadata 字段（仅显示实际存在的字段）；结尾输出统计汇总（分片总数、长度分布、按实体 / 文档类型分组、合法性检查结果）；全部内容同时写入控制台日志文件
- Markdown 报告文件：统计概览、按实体分布、合法性检查结果、分片明细表格、每个分片的详细内容（补充 metadata 字段按分组完整列出，缺失显示 `-`）

补充 metadata 字段覆盖 `MarkdownChunker` 写入的全部字段，按分组展示：
- **定位/溯源**：`path`、`_source`、`source_file`、`_extension`、`_file_name`、`declared_source`
- **分片结构**：`namespace`、`heading_path`、`parent_chunk_id`、`part_index`、`chunk_index`
- **内容校验**：`body_hash`、`content_hash`
- **时间**：`mtime`（时间戳自动转为可读时间）
- **文档分类**：`doc_scope`、`knowledge_layer`、`entity_type`、`topic`、`wild_version`、`keywords`、`building_category`、`entity_aliases`、`constraint_tags`、`role_tags`

说明：列表类字段（如 `keywords`）以 `; ` 连接展示；单条 metadata 可能只包含部分字段，缺失字段在控制台不显示、在 Markdown 报告中显示为 `-`，不会报错。

**示例输出文件**：`wild-server/scripts/chunks_report_20260818_170643.md`（13 个分片，全部通过合法性检查）

---

## 🎯 测试策略

### 单元测试
- **目标**：测试单个函数或类
- **示例**：`test_blueprint_normalizer.py`
- **特点**：快速、隔离、Mock 依赖

### 集成测试
- **目标**：测试模块间交互
- **示例**：`test_agent_graph_execution.py`
- **特点**：完整流程、真实数据

### 端到端测试
- **目标**：测试完整用户场景
- **示例**：`test_session_turns.py`
- **特点**：接近生产、耗时较长

---

## 📊 测试覆盖率

查看测试覆盖率：

```bash
# 安装 pytest-cov
pip install pytest-cov

# 生成覆盖率报告
python -m pytest tests/ --cov=app --cov-report=html

# 查看报告
# 浏览器打开 htmlcov/index.html
```

---

## 🐛 调试测试

### 1. 打印调试信息
```bash
python -m pytest tests/<子包>/test_xxx.py -v -s
```

### 2. 进入调试器
```python
def test_something():
    import pdb; pdb.set_trace()
    # 测试代码
```

### 3. 只运行失败的测试
```bash
python -m pytest tests/ --lf
```

### 4. 查看详细堆栈
```bash
python -m pytest tests/ --tb=long
```

---

## 📝 编写新测试

### 测试文件命名
- 文件名：`test_<feature>.py`
- 类名：`<Feature>Test`
- 方法名：`test_<specific_behavior>`

### 测试结构
```python
import unittest
from app.module import FeatureClass

class FeatureTest(unittest.TestCase):
    def setUp(self):
        """每个测试前的准备"""
        self.feature = FeatureClass()
    
    def tearDown(self):
        """每个测试后的清理"""
        pass
    
    def test_basic_functionality(self):
        """测试基本功能"""
        result = self.feature.do_something()
        self.assertEqual(result, expected_value)
    
    def test_error_handling(self):
        """测试错误处理"""
        with self.assertRaises(ValueError):
            self.feature.invalid_operation()

if __name__ == "__main__":
    unittest.main()
```

### 测试最佳实践
1. **一个测试只验证一个行为**
2. **使用描述性的测试名称**
3. **保持测试独立性**（不依赖执行顺序）
4. **使用 Mock 隔离外部依赖**
5. **测试边界条件和错误情况**

---

## 🚀 持续集成

测试在以下场景自动运行：
- **本地开发**：手动运行 `python -m pytest`
- **Jenkins CI**：每次代码提交
- **部署前**：自动验证

Jenkins 测试配置：
```groovy
sh 'uv run --frozen --with pytest python -m pytest tests -q'
```

---

## 📚 相关文档

- **[工具目录](tools/README.md)** - 开发工具和脚本
- **[开发指南](./DEVELOPMENT.md)** - 开发环境和工作流
- **[架构文档](./ARCHITECTURE.md)** - 系统架构设计

---

更新时间：2026-08-18
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
