# WildAgent 代码 vs 设计 一致性审计（Bug 检测视角）

> 审计日期：2026-08-06
> 目标：不谈性能，只验证"你的完整设计思路能不能被当前代码落实"，即找实现缺口与 bug。
> 范围：wild-server（后端）+ wild-web（前端）
> 方法：对照 `架构设计方案.md` / `项目进展总结.md` / `agent.md`，逐文件核对实现。

---

## 总判

主链路**基本接通**：WebSocket 协议、agent_service 双格式检测、15+步校验流水线、18 个空间工具、RAG 加载器、scenes REST、前端 applyPatch/picking/wild-compiler 都真实存在并接线。

但有几处"设计意图 ≠ 实现"的偏差，集中在 **致命错误拦截不一致、删除的引用级联、重建失败不回滚、协议契约文档不实、确认/拒绝 UI 形同虚设**。下面是分前后端的清单。

---

## 后端 wild-server

### 🔴 高优先（影响"完整设计能否跑通"）

**B1. 完整 Blueprint 的致命 ❌ 错误未被拦截就下发前端**
- `ws_agent.py:686-744`：当 `result.blueprint is not None` 时，即便 `run_validation_pipeline` 报出碰撞/结构类致命 ❌（如 `validate_collision` 顶点爆炸），代码只 `logger.warning(...)` 然后照样 `send_json({"type":"blueprint_generated", ...})`。
- 对照：`patch_proposal` 路径（`ws_agent.py:758-764`）对 `result.error` 是**拦截**的。两条路径策略不一致。
- 后果：前端 `loadBlueprint` 会用一个已知损坏的蓝图替换场景，违反"校验失败应拦截 / 用户保留最终决策权"的设计原则。
- 建议：Blueprint 路径与 Patch 路径统一拦截策略——致命 ❌ 不下发，改为 `error` 消息 + 可定位诊断。

**B2. 文档自相矛盾：RAG 到底做没做？（代码事实：已做）**
- `架构设计方案.md`（第 1156/1164/1236 行）称当前实现是 `RAGSpecLoader`（Chroma 向量检索、启动建索引、真实 embedding 调用）。
- `项目进展总结.md`（82/93/279 行）称"RAG 索引向量库 🚧 下一优先级 / 最紧迫任务"，"规范文档加载器 ✅ FileSpecLoader"。
- 代码真相（已核实）：`config.py` `RAGConfig.enabled=True`、`.env` `RAG__ENABLED=true` + 真实 DashScope embedding 配置；`agent_service._create_spec_loader()` 默认 `RAGSpecLoader`；`loader.py` 构造即 `sync_index()` 建 Chroma、`create_embedding_function` 返回真实 `OpenAICompatibleEmbeddingFunction`。**RAG 已是默认且真实生效**。
- 这是文档层面的 BLOCKER（会让维护者误判架构现状），应立即更新 `项目进展总结.md`。

### 🟡 中优先

**B3. `blueprint_generated` 协议契约不实（缺内联 `blueprint` 字段）**
- `ws_agent.py:28` 注释声明该消息含 `blueprint` 字段，实际 `:543-547` / `:732-738` 只发 `filename + file_url`，需前端再 `GET /api/scenes/{filename}` 拉取。
- 功能可用，但文档声明不实，前端若按"内联 blueprint"实现会接不到。

**B4. 校验流水线对畸形数值坐标无类型保护**
- `spatial_tools.py:217` `validate_opening_coords` 直接 `along_dist = from_vec[0]` 后比较，若 LLM 给字符串/数组坐标会抛 `TypeError`，该异常在 `run_step` 中未捕获，冒泡后以 `error` 终止整次请求（非优雅降级）。
- 建议：工具入口对坐标/尺寸做 `isinstance(Number)` 防御。

**B5. 工具数量文档过时（16 vs 实际 18）**
- 实际 `@tool` 共 18 个：1 查询 + 10 检测 + 7 修正（含 `validate_element_dimensions`、`fix_element_elevations`）。`项目进展总结.md` 仍写"16"。更新即可。

**B6. `extract_patch_from_text` 是死代码（未被接线）**
- `blueprint_parser.py:63-88` 定义，但全仓无任何调用；agent_service 的 Patch 检测走通用 `extract_blueprint_from_text` + `"operations" in json_data`。功能等价，但该函数未来若强化校验，主链路不会受益。

### ⚪ 低 / 架构风险

- **B7. `fix_*` 原地修改在 LangGraph 节点路径可能失效**：主链路（`agent_service`）传同一 dict，原地修改正确；但 `graph.py` + 未来 validate 节点若 `deepcopy` 后再调 fix，修正会丢失。Phase 3 接入时需单独验证。
- **B8. RAG 静默降级**：embedding 接口不可达时 `sync_index` 抛异常被 `except` 吞掉，静默退回 `FileSpecLoader`，无告警日志。属运维隐患。
- **B9. `fix_element_dimensions` 的 `floor`/`stair` 修正规则永不执行**（循环只特判 `wall/beam/roof`），无害死配置。
- `config.py`/`model_client.py` 用 `ReasoningChatOpenAI(ChatOpenAI)` + `base_url`（非文档写的 `init_chat_model`），实现**更正确**，仅文档不符。

---

## 前端 wild-web

### 🔴 高优先

**F1. `remove_element` 不级联清理引用 → "删墙"类操作直接失败**
- `scenePatch.ts:47-49` 只 `filter` 掉该元素本身，不清理引用它的 `opening` 等子节点。
- `sceneValidator.ts:136-147` 对悬空 `opening.parentWall` 报 `level:'error'`，而 `sceneStore.applyPatch` 对 error 直接 `return false`（整个 patch 被拒）。
- 后果：Agent 提一个"删除挂了门窗的墙"的 patch，因悬空 opening 报 error → 整 patch 被拒，连"删墙"都做不了。既无级联删除，也无"先删子再删父"编排。真实功能缺口。
- 建议：`remove_element` 同步删除 `parentWall/constraint target` 指向该 id 的引用元素。

**F2. 重建失败被静默吞掉，不 gate 提交**
- `sceneStore.ts:107-109` 在 `reconstruct()` **之前**就 `blueprint = newBlueprint; revision++`；而 `reconstruct()` 内部 `try/catch` 只 `console.error` 不抛出（`sceneStore.ts:141-158`）。
- 后果：即便重建抛异常、画布变空（`reconstructed.value=null`），`applyPatch` 仍 `history.push` 并返回 `true`。文档称"重建 smoke test 作为成功门槛"，实际重建结果**不 gate 提交**。一个产生非法几何的 patch 被判"成功"。
- 建议：先重建成功再提交，或重建失败回滚 blueprint/revision 并向调用方报错。

### 🟡 中优先

**F3. `vertex_overflow` 占位网格材质泄漏**
- `renderEntity.ts:39` 创建红色线框占位 `MeshStandardMaterial`，但**没设 `userData.ownsMaterial=true`**；清理旧对象时（`renderEntity.ts:453-467`）仅 `ownsMaterial` 的才 dispose。每次带超限网格的重建都泄漏一个材质。
- 修复：占位 mesh 补 `userData.ownsMaterial = true`。

**F4. 组合构件编译失败被降级为 warning，不阻断 patch**
- `sceneValidator.ts:123-133` 把 `compilation.diagnostics`（组件编译 error）强制降级 warning。Agent 推含非法组件的 patch 仍提交，重建时该组件缺失，画布"少一块"无提示。属"优雅降级"但与"校验拦截非法修改"预期有偏差。

**F5. 确认/拒绝语义形同虚设 + 增量编辑不自动 PUT**
- `requires_confirmation` 在类型/创建时定义，**全代码库从未读取**；`AIChatPanel` 对所有带 patch 的消息一律显示"应用修改"，不区分是否需要确认。
- `agentStore.confirmPatch()/rejectPatch()` 无组件调用；`pendingPatch` 是孤儿状态；**无"拒绝"按钮**。
- 增量编辑应用后**不自动 PUT** 回后端（`syncBlueprintToBackend` 仅"保存"按钮触发）。这与 `项目进展总结.md:90,188` 的"自动 PUT 同步"矛盾，但与 `架构设计方案.md:2124` 的"显式保存才 PUT"一致——文档自相矛盾，代码实现的是后者。

**F6. 不解析 `agent_reply` 内嵌 ```json 并自动应用**
- 实际完整 Blueprint 走 `blueprint_generated`（file_url）→ HTTP GET → loadBlueprint 路径；`agent_reply` 处理器只 `addAgentMessage(content)`。功能 OK，但"解析回复内 json 自动应用"这一说法未实现。

### ⚪ 低 / 健康度

- **F7. 拾取已实现、Gizmo 部分实现**：`picking.ts` 不存在，拾取逻辑内联在 `CanvasViewport.vue:425-470`，点击选中可用且正确回溯组合构件映射；`TransformControls` 仅对单个 `draggable` 组件显示（无通用多选/旋转/缩放）。文档称"picking/gizmo 未做"已过时。
- **F8. TypeScript 健康**：未发现会导致 `vue-tsc` 硬失败的证据；风险点是渲染层 `materialParams: any[]`（`renderEntity.ts`）与多处 `as any` 使关键边界失去类型安全；`sceneStore.ts:25` 深路径导入 `../wild-core/src/primitive/parser` 有耦合风险。

---

## 结论

| 维度 | 结论 |
|---|---|
| 你的完整设计主链路 | ✅ 接通（WS、双格式、15+步流水线、18 工具、RAG、scenes、前端 applyPatch/picking/compiler 均在） |
| 需要修的"设计≠实现" | 🔴 B1 致命错误拦截不一致、F1 删墙引用级联、F2 重建失败不回滚 |
| 文档可信度 | ⚠️ 两份主文档对 RAG/工具数/自动 PUT 描述互相矛盾，需先对齐文档再排期 |
| 是否"当前代码保证实现完整思路" | 大体能，但上面 🔴 三处会让某些设计承诺（校验拦截、安全删除、重建即门槛）在实际运行中落空 |

**建议优先级**：先统一文档（B2）→ 修 B1/F1/F2 三个会让设计承诺落空的实现缺口 → 再补 F3/F4/F5 的健壮性与 UX 语义。
