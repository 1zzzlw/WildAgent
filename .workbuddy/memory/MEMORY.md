# WildAgent 项目长期记忆

> 只记**跨会话仍需遵守**的硬约束。细节写当日 `YYYY-MM-DD.md`；已被取代的结论直接删除。

## 一、知识库（`wild-server/storage/knowledge_base/`，单版本）

- 🔴 不要再建 `knowledge_base_v2/`；`wild-web/wild-lang/` 是**只读备份**，绝不修改、不 diff 对错。
- 🔴 Schema 唯一事实源 = `storage/knowledge_base/schema.json`（`blueprint_normalizer.py::SCHEMA_PATH`）；
  前端 `wild-web/wild-lang/schema.json` 是字节一致副本 → **改 schema 必须同时改两处**。
- 目录 = `knowledge/{protocol,components}` + `rules/{implementation,conditional,design-choice}`。
  互斥判据：**"违反了能不能被机器判定"** → 能则 `rules/`，否则 `knowledge/`。
- 🔴 **检索契约 = 5 组硬编码过滤对**（改 metadata 会让查询查空）：协议=`blueprint_spec`+`protocol`｜
  能力=`component`+`capability`｜规则=`recipe`+`relation`｜点名=`recipe`+`entity_name=supported_assembly_relations`｜
  点名参=`component`+`topic=parameters`。代码 `policy.py:61-69`、`planning/workflow.py:60-65`、`agent_service.py:1185-1193`。
  **`config.yaml` 的 `mapping_rules` 才让"目录=分类"生效**（合并序 defaults → mapping_rules → frontmatter）。
- 白名单 15 键 = `MarkdownChunker._DOCUMENT_METADATA_FIELDS`（`loader.py:453-470`）。
  🔴 **`source` 已废**（不在白名单、loader 不读）→ 别为让脚本变绿加回来；溯源用 `authority` + `knowledge_revision`。
  `status`/`authority` 取值必须落在 `_retrieval_priority_score` 表内（`loader.py:181`）。
  frontmatter 用 `_parse_metadata_lines` 解析（**不是 YAML**）。增删文档必须同步 `config.yaml` 的
  `required_documents`（**只允许 `.md`**）。
- 🔴 **围栏 json / jsonc 分工（CI 会查）**：` ```json ` = 模型可整段照抄、**必须严格合法**；
  ` ```jsonc ` = 带注释/省略号的教学示意与反例。`recipes.py:43` 用正则抓 ` ```json `；`lint_wild_rag_docs.py:499` 只严格校验 ` ```json `。
- 🔴 **KB 内部一致性：互相矛盾的条目，模型会挑 `authority` 更高 / 格式更像硬约束的那份。**
  已发事故（2026-09-17）：`capability-boundaries.md` §3.5 写「❌ 复杂组合屋顶（需多个 roof 对象组合）」
  与 `generation-redlines.md:32`「多体量各生成一块屋顶」正面冲突 → 模型照前者，L 形别墅侧翼没屋顶。
  **已修**：§3.5 改成「✅ 多体量分段屋顶」+ jsonc 示例。→ **改"能做/不能做"表前，先 grep 全库有没有相反的话**；
  排查"模型看到规则却不照做"时，先打印该查询实际命中的**分片正文**（`check_rag_queries.py` + `MarkdownChunker.split_file`）。
- 🟡 **CI 门禁**（`Jenkinsfile:171`）：`deployment_preflight.py` + `test_knowledge_rules_v3.py`（19 项，linter **零 error** 断言）。
- **检索形态硬事实**：进向量文本 = `"> 知识路径：{heading}\n\n{正文}"`，`heading` = 祖先标题按 `" > "` 拼接
  → **目录名与文件名不进向量，只有"标题"影响召回**。`HashEmbeddingFunction` 是**词面匹配** → 检索断言问法要贴近目标标题用词。
- **改完 md 正文 → 必须重建索引才生效**（`resync_knowledge_index.py` 或启动时的 `sync_index`）。

## 二、蓝图坐标语义（引擎会当真，写错就悬空/穿透）

- **墙**：`from[1]`=墙底、`to[1]`=墙顶（另有 `height` 字段则改用它）。转角两面墙**共用完全相同的端点坐标**（容差 0.01m）。
- **楼板**：`from[1]`=板底，`thickness` 向上增厚。**屋顶**：`position[1]` **必须等于承托墙顶**（gap>0.15 判悬空）；
  `span/depth` ≈ 承托墙跨度 + 0~2m 出檐；`roofType` 只有 6 个合法值。
- **门窗/开口**：`from = [沿墙距离, 开口底部世界Y, 法向偏移]`，底部 Y 必须落在宿主墙竖向范围内。
- 🔴 **构件 `from[1]` 语义不统一**：`balcony` 是**板顶**（板向下增厚）；`canopy` 是**板中心** → 用世界包围盒实测，别类推。
- **楼梯**：端点必须命中某层楼板标高（`from[1]+thickness`）或墙顶，且落在**楼板自身标高 ±0.25m** 内
  → 地面板写 `from[1]=-0.2, thickness=0.2`（板顶正好 0.0）。碰撞校验的楼梯 AABB 是**方形**（按 `width/2` 双侧膨胀）
  → 直梯贴外墙会判"穿插"，端点离墙内皮 ≥ 半梯宽 + 0.05。

## 三、门禁与验证纪律

```bash
cd wild-server
./.venv/Scripts/python.exe ../scripts/audit_keyword_calls.py            # 静态门禁，退出码即结果
./.venv/Scripts/python.exe -c "from app.agent.graph import build_generation_graph; build_generation_graph()"
./.venv/Scripts/python.exe -m pytest tests/agent tests/components -q   # 基线
# 蓝图门禁（退出码即结果；③ 须在 wild-web 下跑）
./.venv/Scripts/python.exe ../.workbuddy/diag/verify_wild_blueprint.py <蓝图>   # 11 校验器(含 7e 反向覆盖) + KB 红线
node ../.workbuddy/diag/check_blueprint_render.mjs <蓝图>                       # 真实编译重建
# 可选：audit_roof_top_coverage.py = 逐体量环打印每环覆盖率（7e 报 ⚠️ 时定位用）
```

- 🔴 **反向屋顶覆盖已由流水线 7e 步强制**（`validate_roof_top_coverage`，`spatial_tools.py`）。判据四条，写蓝图/改它前必看：
  ① 只查结构性墙（`顶-底≥1.8m` 且 `thickness≥0.1`）；② 屋顶基底**不低于**墙顶即算覆盖（只设下界，**不设上界**，
  重檐/穿斗是正常的，悬空高度归 `validate_roof_coverage` 管）；③ 缺 `position` 的屋顶按 `resolver.ts::resolveRoofBoundary`
  复原（承托墙包围盒居中 + `bbox+1.0`）；④ 曲线墙沿真实曲率采样、采样点取等分格**中心**，重檐含 `eaveOutset`。
  → 只报 ⚠️ 不阻断（能力缺失只标记）。回归测试 `tests/validators/test_roof_top_coverage.py`（11 例）+ 变异测试 `mutate_roof_top_coverage.py`。
- ⚠️ **三道静态验证的共同盲区**：全量导入、`build_generation_graph()`（只编译）、`test_agent_graph_execution.py`（全桩）
  **都看不到节点内部错误** → 改节点后必须补"只打桩模型与检索、其余走真实路径"的用例（范例 `test_architecture_node_smoke.py`）。
- ⚠️ **校验器全绿 ≠ 引擎能重建**（阳台门悬空 20cm 的教训）→ 蓝图门禁分工：`verify_wild_blueprint.py` 管数据合法性，
  `check_blueprint_render.mjs` 管真实链路（逐元素世界 AABB；**必须应用 rotation**）。
- **重复即风险**：同一件事被两处解析时立刻找第二处（平面尺寸同时被 `profile.py::_requested_dimension` 与
  `requirements.py::_extract_plan_dimensions` 解析）→ 两侧各写各的就要有测试钉住一致性。

## 四、渲染引擎 / 查看器

- 改前必读 `docs/渲染引擎优化/渲染引擎优化指南.md`、`渲染问题诊断流程.md`。
- **A/B/C 分类**：A=纯渲染/几何（直接做）；B=渲染私有字段 `_`（直接做）；C=WILD 契约参数（**必须事前报告获批**）。
  优先级 `A > B > C`；C 类未批擅自落地会被要求回滚。
- **红线**：禁止按 `roofType`/构件类型写专属分支加能力 → 抽象成对所有类型成立的算子（檐口 = 屋面边界环扫掠）。
- 改动须配门禁脚本（`verify-*.mjs`/`audit-*.mjs`）+ 批量蓝图回归，不能只验单样本。
- 🔴 **绝不在 `lantu/viewer/` 自实现材质/网格构造** —— 必须走 `src/renderer/` 的 `wildCoreAdapter` + `BlueprintRenderInstance`。

## 五、计划验收与交付

- 🔴 **能力缺失只标记、不阻断**（用户原话："就让他正常生成就行……为什么要有阻断呢？"）。
  缺能力 → `unsupported`+`warning`；媒介不一致/主观 → `needs_review`+`warning`；**计划对象不合法** / **模型服务终态错误** → `error`。
  **判定准则：只有"数据本身坏了"才配终止一次生成。** `severity` 是唯一阻断杠杆（三处读它）。
  关键词判定表**按语义分表**（interior/site/presentation_medium），别堆进一个 `_contains_any`。
- 🔴 **`_compile_acceptance` 是按顺序命中的 if 链**，更具体的语义分支必须排更泛的前面。
  已踩两次：媒介降级排在量化抽取**之后**；材质排在构件分支**之前**。
- **方法论**：验收编译器的回归输入必须取自**真实运行的计划**（检查点的 `structured_requirements`），
  手写文本喂给四道验证全绿、线上崩的是 LLM 写的文本。
- **未决（需产品决策，别自作主张补）**：「不少于/不低于 N」不认（补它=新增阻断点）；数量词不绑定名词；
  **验收失败仍会丢弃 `final_blueprint`**；`车库` 暂不能从"缺能力"表移除；「建筑必须为两层」不再被识别为层数约束
  → 掉进 `phase_outcome` 兜底永远通过（`test_execution_plan.py::test_model_tasks_compile_to_stable_traceable_requirements` 红，预存）。

## 六、文档归档约定

- **不要往 `docs/` 根目录堆文档**，直接进专题目录；渲染引擎统一放 `docs/渲染引擎优化/`。
  新建专题目录同步登记 `docs/README.md` + `docs/项目索引.md`。
- `docs-dev/` = **历史归档**（不作为实现依据）→ 不要回改里面路径。
- **移动文档踩坑**：别漏正文里 `` `docs/xxx.md` `` 纯文本路径（链接检查器查不到）；搬完跑遍历 `](...)` 再 `resolve()`。
- `docs/` 树已知 47 条历史断链——不是新引入的，别误判。

## 七、环境硬约束与已知坑

- **跑 wild-server 的 Python 一律用 `wild-server/.venv/Scripts/python.exe`**（托管 Python 与 Anaconda 都缺依赖）。
- **门禁脚本在仓库根 `scripts/`**（不是 `wild-server/scripts/`），从 `wild-server` 调用写 `../scripts/…`。
- **`pytest tests` 全量跑必崩**（capture `I/O operation on closed file`）→ 按目录/文件跑；`tests/rag` 逐个文件跑。
  判断"某条失败是否我引入"：`git show :path > path` 还原 → 复跑 → 恢复。已知预存失败：`test_execution_plan.py` 层数约束那条。
- 🔴 **同一文件不要在同一批里发两个 Edit**：CRLF 文件会丢更新（后写覆盖先写）。
- **本机跑不了真实浏览器/WebGL**（Chrome headless exit 21）→ 渲染验证靠离线脚本（vite `ssrLoadModule`）。
  ⚠️ 技能 `wildagent-offline-geometry-diag` 引用的 `.mjs` 工具箱表**全仓已不存在** → 用前先确认文件在不在。
- **`wild-web` 下所有命令必须在 `wild-web` 目录执行**（否则 `node_modules` 解析不到）。
- **`lantu/**` 不在类型检查范围**（`tsconfig.app.json` 只含 `src/**`）→ 改 `lantu/viewer/main.ts` 单独用 transpile/vite build 校验。
- **复现线上失败不用猜**：`storage/sessions/langgraph_checkpoints.sqlite3` 的 `checkpoints` 表，`thread_id = "generation:<request_id>"`，
  用 `SqliteSaver` 解码（venv **没有 `msgpack`**，用 `ormsgpack`），只读打开；`merged_blueprint` 是 dict 而 `final_blueprint` 是 None → 蓝图已产出却被判死丢弃。详见 skill `wildagent-import-healthcheck`。

## 八、用户工作方式偏好

- **先方案、后落地**。
- 🔴 **跟着用户的思路走，不要引导**（原话"跟着我的思路走……你也不用引导我"）：不要每轮结尾问"下一步做哪个"；
  问题通常很简单，**直接答、简短、快节奏**；需决策的事**一句话点出**，不铺选项矩阵。
- 输出偏好**结构化**：表格、`file:line`、🔴🟡⚪ 三级优先级。代码审查视角 = "**完整思路能否实现**"。
  对 UI 视觉品质要求高；对**文件位置、命名残留**敏感 → 归类/命名/位置一次到位。
