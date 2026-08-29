---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 120c9aab85e3ed979ff6cbda3bbcb633_9a59b6389c4911f184de525400f8a581
    ReservedCode1: 6q7CIEXR268RAOt0gTtR1fgKmCJiUK5dql1hvhOMThWm3bT82SbMXv8USuTmh9GfKTUBb878qIbJLvtnVZpGz7Tde1hzmixiSZZKK+hXmA6ENpr+g+z57TXQHpPYzVirfAChNm7ZHqwOKtu67P8vrojAFs9UKI2YZ3RwZyfyn0E5ruuvCAhV3rovLo8=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 120c9aab85e3ed979ff6cbda3bbcb633_9a59b6389c4911f184de525400f8a581
    ReservedCode2: 6q7CIEXR268RAOt0gTtR1fgKmCJiUK5dql1hvhOMThWm3bT82SbMXv8USuTmh9GfKTUBb878qIbJLvtnVZpGz7Tde1hzmixiSZZKK+hXmA6ENpr+g+z57TXQHpPYzVirfAChNm7ZHqwOKtu67P8vrojAFs9UKI2YZ3RwZyfyn0E5ruuvCAhV3rovLo8=
---



# WildAgent 测试目录说明

`wild-server/tests/` 按功能领域划分为 9 个子包，每个子包包含独立的测试文件与 `README.md`：

```text
tests/
├── agent/        核心流程测试（Agent 图执行、路由、结果交付）
├── components/   组件生成测试（组件蓝图、状态合并、架构规划、立面/材质配方）
├── rag/          RAG 检索测试（语义分片、索引同步、检索缓存、查询规划）
├── blueprint/    Blueprint 处理测试（归一化、文本提取、材质验证）
├── validators/   验证器测试（P0/P1/P2 优化、空间验证、验证缓存）
├── repair/       修复工具测试（回调定向修复、合并精度、骨架恢复）
├── network/      网络和会话测试（WebSocket、会话轮次、生成任务服务）
├── assets/       材质和资产测试（材质调优、PBR 资产、模型客户端兼容）
├── misc/         其他工具测试（诊断、就绪、推理流、Prompt 组合等，含 show_langgraph_graph.py 辅助脚本）
├── artifacts/    测试资产目录（.wild 样例文件，不参与测试收集）
└── README.md     本文件
```

## 运行方式

在 `wild-server` 目录下（uv 环境）：

```bash
.\.venv\Scripts\activate
$env:PYTHONPATH="."
python -m pytest tests -q            # 全部测试
python -m pytest tests/rag -v        # 单独运行某个子包
python -m pytest tests/rag/test_rag_semantic_chunking.py -v   # 运行单个文件
```

## 测试文件清单（41 个测试文件 + 1 个辅助脚本）

> 各子包 README 含每个文件的**测试函数级覆盖点**与运行示例；本表给出文件级清单与用例数（以 2026-08-20 盘点为准）。

| 子包 | 文件 | 用例数 | 覆盖点一句话 |
|---|---|---|---|
| agent | `test_agent_delivery.py` | 5 | Agent 结果统一出口：校验覆盖、拒绝蓝图不落盘、文件引用、保存失败 |
| agent | `test_agent_graph_execution.py` | 3 | 真实编译图验证 generate/edit/chat 三条分支 |
| agent | `test_agent_graph_routing.py` | 12 | 意图路由：复杂度跳过、edit/generate 派发、fast path、构件建议配额 |
| assets | `test_material_tuning.py` | 11 | 材质调优安全协议、场景选择、优化意图收窄 |
| assets | `test_model_client_compat.py` | 4 | 模型客户端内容/推理字段兼容 |
| assets | `test_pbr_assets.py` | 9 | PBR 资产存储、manifest、上传/删除 API |
| blueprint | `test_blueprint_material_validation.py` | 14 | 材质与坐标归一化/拒绝规则 |
| blueprint | `test_blueprint_normalizer.py` | 6 | 蓝图归一化：去未知字段、墙体去重、幂等 |
| blueprint | `test_blueprint_text_extraction.py` | 9 | 蓝图/补丁文本提取与归一化 |
| components | `test_architecture_plan.py` | 39 | 架构规划：幕墙立面、高细节模式、U 形平面、洞口 |
| components | `test_component_blueprint.py` | 5 | 构件蓝图后端校验与场景补丁 |
| components | `test_component_state_reducer.py` | 1 | 并行组件节点写通用 State |
| components | `test_component_validation_recheck.py` | 8 | 构件修复重校验、阳台重定位 |
| components | `test_facade_recipe.py` | 4 | 立面配方参数从知识库加载/钳制 |
| components | `test_material_plan.py` | 17 | 材质计划：资产解析、程序化砖、幕墙中性立面 |
| misc | `show_langgraph_graph.py` | — | 辅助脚本：可视化当前 LangGraph 图（非测试） |
| misc | `test_deployment_preflight.py` | 5 | 部署预检离线/真实模式与冒烟响应文本选择 |
| misc | `test_diagnostics.py` | 7 | 诊断 Schema：指纹、校验快照、节点诊断 |
| misc | `test_ip_geolocation.py` | 4 | IP 掩码、代理头信任、库缺失回退 |
| misc | `test_langgraph_checkpoint_resume.py` | 1 | LangGraph 检查点恢复 |
| misc | `test_prompt_composition.py` | 7 | Prompt 组合：spec 注入、RAG 查询、metadata 过滤 |
| misc | `test_readiness.py` | 3 | 服务就绪检查 |
| misc | `test_reasoning_stream.py` | 3 | 推理流适配器：thinking 选项、推理内容保留 |
| misc | `test_scene_patch_generation.py` | 8 | 场景补丁生成：预检、坐标、推理内补丁优先 |
| network | `test_generation_commit.py` | 2 | 原子写入与幂等提交 |
| network | `test_generation_job_service.py` | 10 | 生成任务持久化、三类审核恢复、事件补发与状态竞争 |
| network | `test_session_turns.py` | 4 | Turn 服务端持久化与描述压缩 |
| network | `test_ws_agent_disconnect.py` | 17 | WS 断开场景与骨架失败原因保留 |
| rag | `test_query_planner.py` | 5 | 查询规划：别名解析、过滤优先、检索 many |
| rag | `test_rag_index_sync.py` | 7 | 索引同步：增量 upsert、parent 扩展、删除失效 |
| rag | `test_rag_retrieval_cache.py` | 4 | 检索缓存键稳定性 |
| rag | `test_rag_semantic_chunking.py` | 7 | 语义分片：知识路径、长度兜底、body_hash |
| repair | `test_callback_targeted_repair.py` | 5 | 回调定向修复路由 |
| repair | `test_merge_precision.py` | 9 | 合并空间归一化与硬约束 |
| repair | `test_skeleton_blueprint_recovery.py` | 3 | 骨架蓝图恢复 token 合并 |
| repair | `test_targeted_repair_tools.py` | 10 | 定向修复工具：动作解析、实体限制、错误收敛 |
| validators | `test_p0_implementation.py` | 9 | P0：结构校验、查询改写、域配置 |
| validators | `test_p1_p2_implementation.py` | 12 | P1/P2：事实/工具/推理自检、混合检索 |
| validators | `test_spatial_invariants.py` | 2 | 空间不变量：包围盒、墙框与楼层 |
| validators | `test_spatial_validation.py` | 21 | 空间验证：墙体重叠、洞口适配、屋顶贴合 |
| validators | `test_validation_cache.py` | 2 | merge→final_validate 校验结果复用 |
| validators | `test_validation_pipeline_repairs.py` | 2 | 校验管线修复：根因分类、材质别名先修复 |

> 用例数来自 `pytest --collect-only` 实测（2026-08-20），合计 **306 个可收集用例**；`show_langgraph_graph.py` 为辅助脚本，不参与 pytest 收集。

## 结果怎么看（pytest 输出解读）

运行 `python -m pytest tests -v`，关注：

- **`passed / failed / skipped / error` 四列**：`F` 为失败用例（红色），`s` 为跳过（无前置条件），`E` 为收集/夹具错误（通常是 import 或环境问题）。
- **失败定位**：失败摘要区 `FAILED tests/<子包>/<文件>.py::<测试函数> - <断言摘要>`，按 `文件::函数` 直接重跑单条：
  ```bash
  python -m pytest tests/rag/test_rag_semantic_chunking.py::RAGSemanticChunkingTest::test_body_hash_ignores_repeated_knowledge_path_prefix -v
  ```
- **预期结果**：常规环境下 9 个子包全部绿色通过（合计 306 个用例）。若出现批量失败，优先检查：① 是否在 `wild-server` 根目录且 `$env:PYTHONPATH="."`；② 是否激活 venv（`.\.venv\Scripts\activate`）；③ 网络/密钥类用例是否有对应 `.env` 配置。

## 约定

- 所有测试文件仅依赖 `app.*` 模块，包间无相互导入，无需 `__init__.py`。
- 移动测试文件时无需调整 import；请保持"一个功能包一个子目录"的组织方式。
- 完整测试说明见 [docs/TESTING_GUIDE.md](../../docs/TESTING_GUIDE.md)。
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
