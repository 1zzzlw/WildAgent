# RAG 启动同步阻塞 — 勘察报告（只读，未改任何源码）

范围：wild-server（Windows，`uv` 环境，.venv 内 uvicorn 0.51.0 / chromadb 1.5.9）。以下行号均按当前文件。

## a) 启动阻塞的因果链

1. 入口导入链：`uvicorn/fastapi` 加载 `main:app` → `main.py:17` import `app.api.ws_agent` → `ws_agent.py:76` import `agent_service` → `agent_service.py:1586` 模块级 `agent_service = AgentService()` 立即执行（main.py:27 只是复用同一缓存模块，进程内仅一次）。
2. `AgentService.__init__`（agent_service.py:1000-1047）第 1 步即 `_create_spec_loader()`（1002 行）。
3. `_create_spec_loader`（1069-1132）：`config.rag.enabled` 为真（1071）→ 构造真实 embedding 函数（1077-1082，密钥/模型/地址取自 `config.embedding`）→ `get_rag_spec_paths()` 扫描 `storage/knowledge_base`（agent_service.py:88/94-96，loader.py:56-70）→ `RAGSpecLoader(...)`（1084-1094），未传 `auto_sync` → 取默认 `True`（loader.py:914）。
4. `RAGSpecLoader.__init__` 末尾 `if auto_sync: self.sync_index()`（loader.py:943-945）——**构造时同步阻塞整个 import**。
5. `sync_index()`（loader.py:1073-1258）串行执行：`_get_collection()` 打开/建集合（1077）→ 切分全部 markdown（1079）→ 与已存 ID 求差（1083-1112）→ 每 10 块一批循环（1116/1167-1207）调 `embed_and_upsert`（1146-1158）→ `OpenAICompatibleEmbeddingFunction.embed_documents`（loader.py:249/316-317）→ 每批一次 HTTP embeddings.create。
6. 超时参数硬编码：`OpenAICompatibleEmbeddingFunction.__init__` 默认 `timeout=30.0, max_retries=0`（loader.py:257-259），惰性客户端把 timeout/max_retries 传给 openai SDK（303-308）。`create_embedding_function`（1878-1900）与 `build_from_config`（323-330）都**不消费 `config.embedding.timeout`**（config.py:29 的 300s 默认只服务 chat），SDK 层无重试。
7. 数百块 ÷ 每批 10 = 数十批；每批若超时各等 30s。批次全串行、无总时间预算，单次启动 5~15 分钟即由此而来；期间服务端 import 未完成、无法对外服务。
8. 连续 3 批主循环超时（loader.py:1192-1194 raise）→ 异常穿透 `__init__` → 被 `agent_service.py:1114-1130` 捕获 → 永久降级 `FileSpecLoader`（1132 行，`_dynamic_prompt` 随之 False，agent_service.py:1003）。
9. `/health/ready`（main.py:97-128）在同步完成/降级前不可用（503）。

## b) 现有“抗超时”措施及其缺陷

措施（loader.py sync_index 内）：
- 超时批先“延后”，继续后续批（deferred_batches，1165/1184-1195）；
- 主循环连续 3 批超时才整体中止（consecutive_timeouts，1166/1192-1194）；
- 结束后对延后批单次重试（1212-1232）；重试仍超时仅累计 failed_chunks、保留待同步（1217-1226，不 raise）；
- agent_service 捕获异常降级并记 warning/error 与 rag_warning（agent_service.py:1114-1130）。

缺陷：
1. 超时/重试均不可配：30s 写死、SDK `max_retries=0`，配置层无入口（.env/.env.example 仅 EMBEDDING__NAME/API_KEY/BASE_URL，.env 7-10 行 / example 9-12 行；RAG 段 17-25 / 19-29 行无超时项）。
2. 无总时间/总批预算：只要服务“偶发成功”，consecutive_timeouts 被重置（1202），同步可无限拉长，正是 5~15 分钟的场景。
3. 中止即全毁：主循环 ≥3 次超时直接 raise，即使前面已成功写入大部分批次，agent_service 仍整体降级 File，已建的部分索引被弃用；与“重试失败只保留待同步、继续用部分索引”（1216-1226）语义不一致。
4. 无并发/后台：loader 无任何 threading/asyncio 支持（模块 imports 见 loader.py:19-43），同步在模块 import 路径上同步执行，无法先起服务再同步。
5. 无进程/运行间去重：每次 worker 启动都重算 diff；上次中断遗留的 pending 块按设计“下次启动自动重试”（1253）；配合 reload 每改一个 .py 就重启并重跑，造成重复网络同步。
6. 双进程风险：见 c)5 与第 e 点——当入口本身执行 main.py（其 `__main__` 段 main.py:131-139 自带 `uvicorn.run(reload=True)`）时，父进程已导入 main（同步一次），又 spawn 子进程再导入（再同步一次）。

## c) 最小改动方案清单（仅设计，未实施）

1. **构造不做全量同步**：`auto_sync` 默认改 False（loader.py:914），首次 `load/retrieve` 前 lazy 同步，或只做轻量 count/metadata 检查。影响：agent_service.py:1069-1132 日志流、/health/ready 语义、脚本 `scripts/rag/check_sync_status.py:10`（依赖导入即同步）。
2. **同步移出模块导入**：AgentService 单例（agent_service.py:1586）改为 lazy/首次访问构建，或经 FastAPI lifespan（main.py:31-49）在监听后再触发；可后台线程+跨进程文件锁（锁文件置于 persist_dir）。影响面大：ws_agent.py:76、config_api.py:99-101、全部 nodes 与 readiness 都引用该单例。
3. **超时/预算可配**：把 `config.embedding.timeout`/新增 max_retries 接入 create_embedding_function（loader.py:1878-1900）并保留 SDK 默认重试；sync_index 加总时间预算与最大批次数，超预算立即收尾（保留已写入批次，不 raise）。
4. **中止语义改为“部分可用”**：3 连超时不再 raise 弃用全索引（1192-1194），改为记录 pending 结束；仅当集合空/打开失败才允许 agent_service 降级。
5. **去重双进程同步**：sync 前置进程文件锁（拿到锁才同步，拿不到则跳过/等待）；若入口是 main.py 自带 reload（main.py:131-139），建议文档改用 `uvicorn main:app --reload`（父进程不导入 app，见下）或去掉 `__main__` 里的 reload=True。
6. **RAG 就绪后热切换**：`spec_loader` 被 agent_service.spec_loader.load/load_many 直接调用，涉及 app/agent/nodes/：architecture_node.py:61、base_component_node.py:129、chat_node.py:70、execution_plan_node.py:62、callback_node.py:99、floor_layout_node.py:223、floor_plan_design_node.py:57、floor_space_analysis_node.py:182、floor_openings_node.py:107、skeleton_node.py:100，以及 ws_agent.py:1873(query_structured)。热切换需同时替换 spec_loader 并刷新 `_dynamic_prompt`/静态 agent（1003/1041-1045），且 readiness 以类名+sync 统计判定（main.py:109-116）——建议先做 1/3/4，热切换作为后续。
7. **配置项**：EMBEDDING__TIMEOUT / EMBEDDING__MAX_RETRIES、RAG__SYNC_TIME_BUDGET_SEC、RAG__AUTO_SYNC（config.py 的 RAGConfig 加字段，.env.example 补注释行）。`config.embedding.timeout` 已存在（config.py:29/138），仅需 loader 接线。

## d) 受改动影响的测试（grep 核实）

- `tests/rag/test_rag_index_sync.py`（核心）：直接断言 sync_index 的延后/重试/进度/中止语义（43-297 行），改超时策略、中止阈值、重试次数会破坏多数用例；测试用 `object.__new__` 构造，不受 __init__ 默认值影响。
- `tests/rag/test_rag_retrieval_cache.py:14-21`：真实 `RAGSpecLoader(...)` 且已传 `auto_sync=False`、`:memory:`——若去掉/改名 auto_sync 参数会破。
- `tests/rag/test_query_planner.py`、`test_rag_runtime_controls.py`、`test_rerank.py`、`test_rag_trace.py`、`test_rag_semantic_chunking.py`：以 `object.__new__` mock 构造，改动 load/load_many/retrieve 签名才受影响。
- `tests/misc/test_readiness.py:5` import main → 走完整导入链（当前即触发真实单例）；`_ReadyRAGSpecLoader.__name__="RAGSpecLoader"` 按类名判定（23-24），lazy 化后 patch 点可能变。
- 凡导入 agent_service 模块者：`tests/agent/test_agent_service_model_reload.py:3-4`、`tests/misc/test_prompt_composition.py:5`、`test_scene_patch_generation.py:5`、`test_reasoning_stream.py:7`、`tests/network/test_ws_agent_disconnect.py:8/18`、`test_ws_agent_floor_validate.py:6`、`tests/assets/*`、`tests/validators/*` 等——若取消模块级单例或改 lazy，需同步调整这些 patch（`agent_service.agent_service`、`spec_loader.load_many` 等，如 test_callback_targeted_repair.py:87-261）。
- 注意：上述任一测试在本地跑 pytest 时（cwd=wild-server，读真实 .env，RAG__ENABLED=true 且含真实 key）首次导入即会真实执行一次 sync_index（网络依赖、慢），改动 1/2 会显著改善测试导入成本。

## e) reloader 二次导入与 Chroma 并发（依据已安装代码）

- 已装 uvicorn 0.51：`uvicorn/main.py:603-616` 中 reload 分支在父进程**不执行** `config.load_app()`（608-609 else 分支才加载），由 `ChangeReload` spawn 单一子进程（`.venv/.../uvicorn/supervisors/basereload.py:83-84`），子进程经 `_subprocess.py:51/54-80` 才真正 import 应用。故 `uvicorn main:app --reload` / `fastapi dev` 每轮只有 worker 一次 import；**父进程导入 main 仅发生在入口本身就是 main.py**（`python main.py`，main.py:131-139）。仓库文档统一为 `uvicorn main:app --reload`（根 README.md:30），未见 `uv run dev` 别名定义，需用户侧核实其实际命令。
- Chroma：`_get_collection`（loader.py:1780-1817）`PersistentClient(path=persist_dir)`（1791）未传 Settings → 使用默认（chromadb config.py:227 `anonymized_telemetry=True`）；同一 persist_dir（默认 storage/chroma，config.py:66，相对路径由 agent_service.py:1073-1075 解析到 wild-server 根）被父子两个进程同时打开时，**应用层无任何跨进程锁**；且 index_signature 变化会 `delete_collection` 重建（loader.py:1805-1814），与另一进程的写入并发即破坏性竞态。改方案 5 时应一并处理。

## f) 结论优先级建议

先做 c)1+3+4（改动集中在 loader.py 与 .env/.env.example，破坏面最小），再做 c)2/5（涉及启动架构与测试），热切换 c)6 最后评估。
