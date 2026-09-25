# 门禁与验证操作手册

> `MEMORY.md` 只留硬约束、体积受限，所以把**命令与排查细节**挪到这里。
> 做验证/门禁相关的事之前读这份。

## 一、常用命令（退出码即结果）

```bash
cd wild-server
./.venv/Scripts/python.exe ../scripts/audit_keyword_calls.py       # 静态关键字参数门禁
./.venv/Scripts/python.exe -c "from app.agent.graph import build_generation_graph; build_generation_graph()"
./.venv/Scripts/python.exe -m pytest tests/agent tests/components -q

# 蓝图数据合法性（11 校验器，含 7e 反向屋顶覆盖 + KB 红线）
./.venv/Scripts/python.exe ../.workbuddy/diag/verify_wild_blueprint.py <蓝图>

# 真实编译重建 + 逐元素世界 AABB（必须应用 rotation）—— 须在 wild-web 下跑
cd ../wild-web
node ../.workbuddy/diag/check_blueprint_render.mjs <蓝图>

# 五层能力口径对齐（schema / 引擎 / 生成侧派发 / 缺口声明 / KB 能力分片）
./.venv/Scripts/python.exe ../.workbuddy/diag/audit_capability_parity.py
# plan 链的专属门禁（图拓扑 + 计划循环 + 条目级 e2e + 合并作用域）
./.venv/Scripts/python.exe -m pytest tests/agent/test_plan_graph.py tests/plan -q
./.venv/Scripts/python.exe -m pytest tests/agent/test_plan_chain_e2e.py -q
./.venv/Scripts/python.exe -m pytest tests/agent/test_merge_batch_scope.py -q
# 判据：`expand_plan` 展开序列 = generate/merge 交替 + 收尾 merge + validate；
#       批次 merge 只并入不删改；收尾 merge 才判"产物没落地"

# 光照/环境/后期链路唯一事实源（静态，退出码即结果）
node ../.workbuddy/diag/audit_lighting_single_source.mjs

# 查看器光照运行时体检（真浏览器；须先构建单文件产物）
node ../.workbuddy/diag/audit_viewer_lighting_runtime.mjs

# 屋顶覆盖诊断正例/反例回归
cd wild-web && node ../.workbuddy/diag/audit_roof_coverage_diagnostic.mjs

# 加/改 WILD 契约字段（含嵌套字段如 door.interaction.mode）的六道门禁
./.venv/Scripts/python.exe ../.workbuddy/diag/verify_wild_blueprint.py <蓝图>     # A 空间流水线
# B 顶层字段白名单（A 覆盖不到；注意后端有两份白名单，见 MEMORY.md）
./.venv/Scripts/python.exe -c "
import sys, json; sys.path.insert(0,'.')
from app.utils.blueprint_parser import validate_blueprint_schema
print(validate_blueprint_schema(json.load(open('<蓝图>', encoding='utf-8'))) or 'PASS')"
# F 嵌套枚举只有这条卡得住（jsonschema 严格模式）
./.venv/Scripts/python.exe -c "
import sys, copy, json; sys.path.insert(0,'.')
from app.utils.blueprint_normalizer import normalize_blueprint_for_delivery
bp = json.load(open('<蓝图>', encoding='utf-8'))
_, rep = normalize_blueprint_for_delivery(copy.deepcopy(bp))
print(rep.summary(), '| errors:', rep.schema_errors or 'PASS')"
cd ../wild-core && node node_modules/typescript/bin/tsc -p tsconfig.json          # 引擎类型
cd ../wild-web
node ../.workbuddy/diag/check_blueprint_render.mjs <蓝图>                          # C 真实重建
node scripts/check-component-compiler.mjs                                          # D 构件编译器
# G 行为类字段（开合/升降/循环）再加一步：真实场景里量动作，别只验数据
node ../.workbuddy/diag/probe_lift_behavior.mjs <蓝图>

# H 重构/删代码后（改名、删赋值、抽函数、拆模块）—— 抓"运行期 NameError"
#   纯 AST、不 import 目标模块 → 任意 python3 都能跑，不必用项目 venv
cd <仓库根> && <python3> .workbuddy/diag/check_undefined_names.py wild-server/app wild-server/tests wild-server/scripts

# 知识库改动后（正文变了必须重建索引才生效）
./.venv/Scripts/python.exe scripts/rag/lint_wild_rag_docs.py storage/knowledge_base/knowledge/components  # CI 级，0 errors
./.venv/Scripts/python.exe ../.workbuddy/diag/check_kb.py
./.venv/Scripts/python.exe -m pytest tests/rag -q
./.venv/Scripts/python.exe ../.workbuddy/diag/resync_knowledge_index.py
```

⚠️ **门禁现状（2026-09-25 复核：前端三关全绿）**：
- `check-rendering-pipeline.mjs` **已转绿**。曾有的"存量红"（`actual: wild-surface:default-surface-v3 / expected: ...-v2`）
  已查明是**门禁过期**而非代码错：`e2ba4f7 优化渲染引擎` 同一次改动真实改了 shader 本体
  （mineral 族各向异性抹痕 + `relief 0.012→0.016`），v3 是**有意**提升
  （shader 源码变了 `customProgramCacheKey` 必须变，否则 Three.js 复用旧编译产物）
  → 已把 `:242/:266/:278` 三处期望值补齐。**同类原则：门禁里的期望值是"能力契约"，
  改参数/加构件必须同批更新；能派生的就别写死。**
- `check-component-compiler.mjs` 尾部**故意**打 `COMPONENT_COMPILE_FAILED` 负例 → 看退出码。
- `verify_wild_blueprint.py` 退出码 1 可能是 `⚠️ 需要注意` 而非 error，读最后那行 `— 结果：`。

⚠️ `pytest tests` **全量能跑通**（2026-09-25 实测 946 passed / 1 xfailed，~10s）。
旧结论"全量必崩 → 按目录跑"（下一行）**已作废**，保留仅为对照。⚠️ 必须**非沙箱**：
沙箱内 `tests/rag/test_rag_background_sync.py` 5 F。

⚠️ ~~`pytest tests` **全量必崩** → 按目录跑~~（**已作废，勿采信**）。plan 链改造已删掉旧计划层的测试文件（`test_execution_plan.py` / `test_plan_mode_acceptance.py` / `test_web_research_gate.py` / `test_material_kind_requirement.py` / `test_requirements_floor_count_fix.py`），现在按 `tests/{agent,plan,components,repair,rag,network,api}` 跑即为全量相关集。
⚠️ `lantu/**` 不在 `tsconfig.app.json` 的 `include` 里 → 改查看器不走类型检查，需另行校验。

## 二、7e 反向屋顶覆盖（`validate_roof_top_coverage`）

`wild-server` 的 `spatial_tools.py`。四条判据，改屋顶前必看：

1. 只查**结构性墙**（顶−底 ≥1.8m 且 `thickness` ≥0.1m）；
2. 屋顶基底**不低于**墙顶即算覆盖（**只设下界，不设上界**——重檐/穿斗是正常的，悬空高度归
   `validate_roof_coverage` 管）；
3. 缺 `position` 的屋顶按 `resolver.ts::resolveRoofBoundary` 复原（承托墙包围盒居中 + `bbox+1.0`）；
4. 曲线墙沿真实曲率采样、采样点取等分格**中心**，重檐含 `eaveOutset`。

只报 ⚠️ **不阻断**（能力缺失只标记）。回归 `tests/validators/test_roof_top_coverage.py`（11 例）
+ 变异测试 `mutate_roof_top_coverage.py`。

## 三、三道静态验证的共同盲区

全量导入、`build_generation_graph()`（只编译）、`test_agent_graph_execution.py`（全桩）
**都看不到节点内部错误**。改节点后必须补"只打桩模型与检索、其余走真实路径"的用例 ——
范例 `tests/agent/test_architecture_node_smoke.py`。

## 四、校验器全绿 ≠ 引擎能重建

分工：
- `verify_wild_blueprint.py` 管**数据合法性**
- `check_blueprint_render.mjs` 管**真实链路**（逐元素世界 AABB；**必须应用 rotation**）
- `audit_capability_parity.py` 管**五层口径一致**（schema / 引擎 / 生成侧派发 / 缺口声明 / KB 能力分片）

已发教训：阳台门悬空 20cm 时三道校验器全绿。

## 五、真浏览器出图

```bash
# ① 起查看器 dev server（vite 在 wild-web/node_modules，不在仓库根）
cd wild-web/lantu/viewer && node ../../node_modules/vite/bin/vite.js --port 5180 --strictPort &

# ② 多机位出图
cd wild-web && node ../.workbuddy/diag/shot_lantu_viewer_cdp.mjs pool front aerial iso

# 也可直接对单文件产物出图
URL_BASE="file:///E:/AgentProject/WildAgent/wild-web/lantu/viewer/dist-standalone/index.html" \
  PREFIX=standalone node ../.workbuddy/diag/shot_lantu_viewer_cdp.mjs pool front
```

环境变量：`EXP` / `W` / `H` / `DSF` / `PREFIX` / `OUT` / `CDP_PORT` / `URL_BASE`。

🔴 **不要用 `chrome --screenshot + --virtual-time-budget`**：靠猜时机，会截到未加载空帧；
此时相机是写死初值、与 `?cam` 无关，**不同视角截出字节完全相同的图**（`pool` 与 `aerial` md5 一致），
极易误读成"URL 参数没生效"。必须轮询 `window.__wildViewer.ready()`。

## 六、单文件查看器

```bash
cd wild-web/lantu/viewer
node ../../node_modules/vite/bin/vite.js build --config vite.config.standalone.mjs
# → dist-standalone/index.html（蓝图 + JS + CSS 全内联，约 706 kB）

node .workbuddy/diag/probe_page_errors.mjs \
  "file:///E:/AgentProject/WildAgent/wild-web/lantu/viewer/dist-standalone/index.html"
# 期望：加载失败 0 · 控制台错误 0 · phase=ready · canvases=1
```

换蓝图：`BP_FILE=../other.wild BP_LABEL='某某'` 再跑一次（`BP_FILE` 相对 `wild-web/lantu/`）。

⚠️ 内联正则匹配的是**相对**路径 `src="\./assets/…"`。若把 `base` 改成 `'/'` 会失配 →
资源目录被删但 JS 没内联 → 产出 31 kB **空壳 HTML**（面板文字仍在，极易漏看）。
自检：产物 ≥ 600 kB 且日志有 `[standalone] 单文件产物：…`。

## 七、其它诊断脚本

| 脚本 | 回答的问题 |
|---|---|
| `audit_wall_openings.mjs <蓝图>` | 宿主墙**到底有没有被开洞**（按立面三角形总面积对比理论值） |
| `probe_material_binding.mjs <蓝图>` | 每个网格绑的是哪个材质；核实 `materialRef` ↔ `materialParams` 的平行关系 |
| `probe_page_errors.mjs <url>` | 页面在真浏览器里的控制台错误 / 网络失败（判断"打不开"还是"渲染不出来"） |
| `make_furniture_probe.py` | 生成带 `furniture` 的蓝图副本，实测引擎家具重建能力 |
| `audit_lighting_single_source.mjs` | 🔴 光源/PMREM/`scene.environment`/合成器是否只存在于 `src/renderer/`（引擎目录外出现即退出码 1）；并断言两个消费方都接上了三个运行时。**变异测试已验**（放个 `new THREE.AmbientLight` 到 `lantu/` 会红） |
| `audit_viewer_lighting_runtime.mjs` | 真浏览器读 `__wildViewer.lighting()`：`hasEnvironmentMap` 必须 true、`ambientLightCount` 必须 0、光源种类必须恰为 `DirectionalLight+HemisphereLight`、阴影必须开启 |
| `shot_lantu_viewer_cdp.mjs` | 出图；`EXTRA="time=night&env=meadow"` 透传额外查询参数（固定复现时段/环境档）。🔴 **默认不再传 `exp`** —— 原来默认强传 `?exp=1.05`，导致"量到的从来不是预设曝光"，正是这个掩盖了黄昏/夜晚预设偏暗。验证交付状态**不要**传 `exp` |
| `audit_exposure_calibration.mjs` | 🔴 **曝光标定门禁**：真浏览器出图 + 断言（过曝比 ≤2% / 亮度带 / 天空亮度 148~214 / 天空 B−R ≥18），覆盖 day·sunset·night + 最亮的 desert 档。**变异测试已验**（day exposure 退回 1.08 → over 33.6%、天空 rgb(229,237,242)，退出码 1） |
| `sweep_exposure_calibration.mjs` | 单会话批量扫 `曝光 × 光强 × 天空参数`（`COMBOS_JSON` 传组合）。**必须单会话**：每次 reload 都要重跑重建+PMREM |
| `probe_url_errors.mjs <url>` | 打开 URL 打印 console/未捕获异常/资源失败 —— 出图脚本只报 `phase=no-handle` 时靠它定位 |
| `lib/pngStats.mjs` | 零依赖 PNG 解码（`zlib` inflate + 反滤波）+ 亮度/过曝/细节能量/分位数 + 分区域 `rgb`·`std`·`detail` + 裁剪并排落盘 |
| `lib/regions.mjs` / `lib/rgbcheck.mjs` / `lib/mkview.mjs` | 分区域量化（`STATS=detail`）/ 区域 RGB 抽查 / 小尺寸并排对比图 |
| `render_preview.mjs` | CPU 软件光栅化出 PNG —— **只做几何体检**（不做透明/阴影，观感不可信） |
| `wild-server/scripts/rag/lint_wild_rag_docs.py <paths…>` | RAG 文档风格/围栏/metadata Lint。🔴 **必须显式传路径**（不带 `paths` 只报 usage 错、退出码仍是 0，别误当通过）。🔴 **真实路径在 `wild-server/scripts/rag/`，不是 `.workbuddy/diag/`**（旧记忆写错）。对照基线时注意：`redundant_path_metadata` **只在文件处于真实路径、`config.yaml` 能匹配时才触发**，把文件拷到 `/tmp` 跑会假性少报 + 多报 `missing_metadata` |
| `wild-server/scripts/rag/check_kb.py`（或 `.workbuddy/diag/check_kb.py` 副本） | KB 结构 / metadata / **5 组过滤对**命中数 / `required_documents` 一致性；末尾打 `PASS`，并给出「参与生成检索的文档 N / 仅导航 M」 |

> 🔴 **出图的两个坑**：① `file://` 下必须加 `--allow-file-access-from-files`（否则 ES module 被 CORS 拦，
> 表现为"句柄建不出来"或"canvas 全黑"两种假象）；② **查看器 dev server 会自己死掉**（表现为 502），
> 批量出图前先 `curl`。稳定路径 = 单文件产物 + `file://`（与 dev server 出图结果逐位一致）。

## 八、知识库写作与文档归档约定（从 `MEMORY.md` 迁出）

- **`knowledge/` vs `rules/` 判据** = 「违反了能不能被机器判定」→ 能则 `rules/`，否则 `knowledge/`。
- **围栏分工（CI 会查）**：` ```json ` = 模型可整段照抄、**必须严格合法**；` ```jsonc ` = 带注释/省略号的教学示意与反例。
  `recipes.py:43` 用正则抓 ` ```json `；`lint_wild_rag_docs.py:499` 只严格校验 ` ```json `。
- **新增/删除文档**必须同步 `wild-server/storage/knowledge_base/config.yaml` 的 `required_documents`（**只允许 `.md`**）；
  `config.yaml` 的 `mapping_rules` 才让「目录=分类」生效（合并序 defaults → mapping_rules → frontmatter）。
- **新文档归档**：不要往 `docs/` 根目录堆，直接进专题目录（渲染引擎统一放 `docs/渲染引擎优化/`），
  并在 `docs/README.md` + `docs/项目索引.md` 登记。`docs-dev/` = 历史归档，不作为实现依据。
- 只放在 `lantu/`、`docs/` 的文档 **agent 检索不到**，要影响 agent 行为必须进 KB 并登记 + 重建索引。

## 九、一次性清理脚本的收尾门禁（2026-09-21 新增）

"regex 删行 / 按行过滤"的一次性脚本（如 `wild-web/scripts/clean-agent-ui{,-2}.mjs`）**不会报错，
只会静默留下半截语句**。一天内实测踩到三类：

| 陷阱 | 症状 |
|---|---|
| `[\s\S]*?` 想匹配到"最近的 `)\n`" | 删 `computed` 只删掉**头三行**（`.reverse()` 结尾就是 `)`），把 `.find(...)` + `)` 留成孤儿 |
| `dropFunction` 正则写死 `\nfunction NAME\(` | 只匹配**顶层**函数；store setup 里的是 2 空格缩进的 `  function NAME(` → 一个没删掉，只删了引用方 |
| `/\*\* 注释[\s\S]*?\n\}\)\n/` 删注释 | 从注释一直吃到后面的 `})\n`，把**还在用的** `const x = computed(...)` 整块吞掉 |

收尾顺序固定（三层：语法 → 类型分布 → 逐文件修）：

```bash
cd wild-web
node scripts/syntax-check.mjs        # ① 真解析器闸门，只报语法，不报类型
node node_modules/vue-tsc/bin/vue-tsc.js -b --force > "$TMP/tsc.txt" 2>&1   # ② 🔴 必须落盘
sed 's/(.*//' "$TMP/tsc.txt" | sort | uniq -c | sort -rn                    # ③ 🔴 按文件分组，别看 head
```

- 🔴 **别用 `head -N` 截断 tsc 输出**：实测 56 个错只露出 45 个，剩下的看起来像"已经修完"。
- 🔴 **判"这条删除是有意的吗"用 `git show HEAD:<path>`**：既拿到被误删声明的**原文**，也确认哪些删除是**有意**的
  （有意删掉的声明不要顺手恢复，要顺着意图把引用方也清掉）。
- `scripts/syntax-check.mjs`（约 60 行）：`.vue` 走 `@vue/compiler-sfc` 的 `parse()`+`compileTemplate()`，
  `.ts` 走 `typescript` 的 `parseDiagnostics`。**负例已验证**（尾部塞一个 `<div` → `Unexpected EOF in tag`，退出码 1）。
  通用版在 `legacy-code-cleanup-audit` 技能的 `assets/syntax-check.mjs`。grep 证明不了语法完整性，只有解析器能。

## 十、`lift`（向上开启）为什么要钳到墙顶净空（2026-09-22 修「超模」）

现象：`door.interaction.mode="lift"` 的门在 `initiallyOpen` 状态下**整块飘在屋面之上**。
根因：门扇是**刚体平板**，引擎既不剪裁也不折卷。`openDistance` 缺省取洞口高度（2.5m），
3.6m 墙 + 2.5m 门 → 门顶到 5.0m，高出墙顶 1.4m，那部分没有任何东西能遮。

修法（`wild-core/src/compiler/components/attachedToWall.ts::createOpeningInteraction`）：

```ts
const wallTop  = Math.max(frame.wall.from[1], frame.wall.to[1])   // WallParams 无 height 字段
const headroom = Math.max(0, wallTop - (bottomY + height))
behavior.openOffset = [0, Math.min(interaction.openDistance ?? height, headroom), 0]
```

- 🔴 **钳位之所以够用，靠的是"墙体自带遮罩"**：门扇写在**墙中线**（`normalOffset = from[2] = 0`），
  叶板厚 ~0.06m ≪ 墙厚 0.24m → 升起后落在"洞口上方那块实心墙"高度带里的部分**被墙自己吃掉**，
  视觉上等价于卷帘门「从下往上收、门帘变短」。所以钳到墙顶 ≠ 牺牲效果，而是**让遮罩刚好完整**。
- 🔴 **这个前提有依赖**：只有当 `normalOffset ≈ 0` 且 `墙厚 > 叶厚`时成立。全仓 `wild-web/lantu/*.wild`
  实测 **41 樘门 normalOffset 全是 0**，故当前成立；但**别在文档/提示词里鼓励给门写非零法向偏移**，
  否则升起的那半截会露在立面上变成"墙上贴了块板"。
- 净空不足 → 门只升起一截（`Δy = headroom < height`），洞口下半透空；净空充足（矮门配高墙）→ 整扇让开。
  净空 0（洞口顶=墙顶）→ `Δy = 0`，门看起来仍关着。这三种都是对的，不要"修"成硬抬。
- ⚠️ **同 `overhang` 那个坑同型：一处夹取就够，但只有一处**。验收/文档若要引用抬起量，
  **必须读编译后的 `openOffset`**，不能拿蓝图里的 `openDistance` 当实际位移（会差一个 `min`）。

回归这条的固定动作（缺一不可）：

```bash
cd wild-core && npx tsc --noEmit -p tsconfig.json                 # 钳位改动的类型闸门
cd ../wild-web && node scripts/check-component-compiler.mjs       # 叶板厚度门禁仍在（看退出码）
python ../.workbuddy/diag/make_lift_door_probe.py                 # 重新生成探针（含"净空不足/充足"两例）
node ../.workbuddy/diag/probe_lift_behavior.mjs lantu/probe_lift_door.wild   # 16 条断言：门扇顶 ≤ 墙顶
# 真图 A/B（这一步才是"超模"的最终判据）：
cd lantu/viewer && BP_FILE=probe_lift_door.wild node ../../node_modules/vite/bin/vite.js build --config vite.config.standalone.mjs
URL_BASE="file:///E:/AgentProject/WildAgent/wild-web/lantu/viewer/dist-standalone/index.html" PREFIX=liftfix \
  node ../../../.workbuddy/diag/shot_lantu_viewer_cdp.mjs front iso aerial
git checkout -- wild-web/lantu/viewer/dist-standalone/index.html  # 🔴 收尾必须还原（被 git 跟踪）
```

📌 探针里 `front` 机位是**正对正立面**的对照位：修复前该图上方会浮出一块灰色板，修复后该区域干净。
把这条当 A/B 判据，比只看 iso 快得多（`docs/renders/lift-real/` vs `docs/renders/liftfix/`）。

### 10.1 「细部看不看得出来」必须做**受控跨构图**实验（`leafRows` 分节）

同一个 `leafRows` 在两天里得到过两个相反结论（"读不出" / "数得出 4 道线"），原因不是代码变了，
而是**构图变了**：门在画面里占 330px vs 占 1000px。所以凡"某个细部可见吗"的问题，
**必须把构图当控制变量**，且用**唯一变量**：同尺寸、同姿态、只改待测参数。

```bash
cd wild-server
./.venv/Scripts/python.exe ../.workbuddy/diag/make_slat_seam_probe.py                      # MODE=wide，3 樘并排（模拟整栋构图）
MODE=close ROWS=2 OUT=probe_slat_close_r2.wild ./.venv/Scripts/python.exe ../.workbuddy/diag/make_slat_seam_probe.py
MODE=close ROWS=8 OUT=probe_slat_close_r8.wild ./.venv/Scripts/python.exe ../.workbuddy/diag/make_slat_seam_probe.py
# 各自 BP_FILE=<对应蓝图> 构建 dist-standalone → shot_lantu_viewer_cdp.mjs front
```

📌 **别用肉眼数，也别用单列像素判**：材质程序纹理本身就有 4~8 灰阶的随机起伏，
单列采样会被噪声淹没（实测 `rows=2` 也能"数出" 6 道假线）。
正确做法是**按行跨门宽取均值**（噪声被平均掉、水平缝被保留），再找局部暗于邻域的段。
实测该法能干净区分：`rows=8` → 15 处暗线（成对出现，对心间距 ≈93px ≈ 7 处分节）；
`rows=2` → 只剩 3 处与 `rows=8` **同位置**的线（那是场景光影特征，不是分节）。
⇒ **判据是"线数随 `rows` 变"**，不是"有没有线"。对比度仅 5~13/255 灰阶，属"存在但很淡"。

## 十一、`wild-server` 重构后必查「运行期 NameError」（2026-09-22 用户报"意图分类之后直接报错"）

症状：用户发一句生成请求 → 意图分类通过 → 进 `architecture` 节点 → `name 'plan_feedback' is not defined`。
根因：**计划层退场时删掉了 `plan_feedback = (...)` 的赋值，却留下 `if plan_feedback:`**。

这类缺陷（"删了赋值/import，留下引用"）**四道既有关口全都拦不住**：

| 关口 | 为什么看不到 |
|---|---|
| `python -c "import 模块"` / 全量导入扫描 | 不是导入错误，模块与函数体都能 import |
| `build_generation_graph()` | 只编译图，从不执行节点函数体 |
| `pytest tests/agent`（含 `test_architecture_node_smoke.py`） | 🔴 **该块被 `if on_reasoning_delta:` 守卫，而测试从不绑定 reasoning 回调 → `ContextVar` 返回 None → 整块被跳过** |
| `audit_keyword_calls.py` | 只查调用实参能否 `bind()`，不查名字是否存在 |

🔴 **判据 = `check_undefined_names.py` 必须 0 处**（纯 AST，任意 python3 可跑，见 §一 的 H）。本次实测它一次扫出**两处**同类：
`architecture/workflow.py:106` 的 `plan_feedback`（用户遇到的）与
`component_workflow.py:143` 的 `component_rules_source`（定义在 `components.py:53`，本文件漏 import；被更早的崩溃挡住了，属"下一个必炸"）。

🔴 **补测试时必须绑定 runtime 回调**，否则新写的用例同样进不去那个分支：

```python
from app.agent.runtime import bind_reasoning_callback, reset_reasoning_callback
token = bind_reasoning_callback(collect)   # ← 不写这行，整块被跳过，NameError 照样隐身
try: ... finally: reset_reasoning_callback(token)
```

已固化为 `tests/agent/test_architecture_node_smoke.py`（新增 2 条，绑定回调后钉住两种提示文案）与
`tests/components/test_component_generator_smoke.py`（新增 3 条，含 fallback/knowledge 两分支）。

🔴 **新用例必须做负例验证**：把缺陷注入回去 → 期望**恰好新增的那几条红、原有用例仍绿**（后者实证盲区）。
实测 `plan_feedback` 注入后：新增 2 条 FAILED、原有 2 条 PASSED。代价 ~2 秒，信息量最大。
⚠️ 注入锚点按**真实行尾**匹配（本仓源码是 CRLF，`byte.count(b'\r\n')` 才是真相），
且注入前 `assert` 命中恰好 1 次 —— 否则会"静默没注入"，测试通过被误读成"用例无效"（本轮踩过两次）。

🔴 **负例验证要连「调用点」一起注**：只注**规则函数/辅助函数**的返回值仍会全绿 —
`rotation` 单位迁移本轮实测：把 `component_workflow.py` 里的 `_coerce_fragment_rotations(fragments)`
注成 `0`，`test_rotation_units.py` **40 条一条不红**。⇒ 规则写对 ≠ 有人调用
（"能力已实现却无人派发"的测试版）。修法=再补一条**走真实节点函数体**的用例
（`test_component_generator_smoke.py::test_furniture_generator_migrates_degree_rotations`），
注回去后**恰好这一条红、其余 4 条绿**。

📌 `wild-server` 当前基线：`pytest tests` → **946 passed, 1 xfailed**（约 10s，2026-09-25）；
唯一 xfail 是 `test_architecture_quota_consistency.py::test_schematic_high_rise_fallback_satisfies_design_contract`（`_fallback_plan` 配额 84 vs 实际 69 槽位）。
`audit_keyword_calls.py` → 405 调用点 / 0 问题。

## 十二、曝光与光照（S1，从 `MEMORY.md` 迁出）

- **唯一事实源** = `TIME_PRESETS` + `ENVIRONMENT_PRESETS` + 天气；`worldLookRuntime` 默认 profile
  的光强倍率必须全为 1，否则编辑器比查看器亮 3~8%，"两界面同一套光照"不成立。
- **标定必须"走预设、不传 `?exp=`"**：出图脚本曾默认传 `exp=1.05`，长期掩盖预设不准。
  门禁 `audit_exposure_calibration.mjs` 是**区间**断言（不是等值）。
- ⚪ three **0.160.1** 无 `scene.environmentIntensity`（r163 才有）→ IBL 强度只能调 `envMapIntensity`
  与天空辐射量。**three `Sky` 的输出是任意尺度辐射量**：提高 `rayleigh` 会让天空**更白**，不是更蓝。
- 🟡 白墙（albedo≈0.93）在阳光下压在 ACES 高光段平坦区 → 材质微变化 ±6% 只剩几个灰阶。
  "去塑料感"性价比排序：**几何细部 > 材质不匀 > 贴图**。

## 十三、真模型探针的三个坑 + 通用几何通道的空输出（2026-09-23/24）

`probe_object_chain_live.py` / `probe_architecture_chain_live.py` 都踩过这三点：

1. **链路会停在 `design_review` 的 `interrupt()`** —— 这是正常停靠点，不是失败；
   不恢复就只能验到"审图前"，会把"等审批"误读成"产物为空"。必须
   `await graph.ainvoke(Command(resume={"action": "confirm"}), config)` 继续，并允许连续多次。
2. **交付物读 `final_blueprint`**（`merged_blueprint` 只是收尾合并的中间态）；
   `kind` 在 `design_document["decisions"]["kind"]`。
3. **条目转 `skipped` 后 `run.evidence` 会被改写** —— 原始失败原因**只剩在**
   `component_diagnostics[{kind}_gen/_val]` 里（含 `fragment_count` / `validation_passed` /
   `error` / `rag_hits`）。

⚠️ **通用几何通道（物件链）的模型输出偶发为空**：实测 3 次里 1 次 `fragment_count: 0`。
此时链路**如实报错**（条目重试 → `abandoned` → design_brief 缺口 error），
**既不是缺陷也不是静默替换**，重跑即过。

⚠️ **模型通道也可能是外部阻塞**：2026-09-24 实测 `api.xiaomimimo.com`（`mimo-v2.5`）
返回 `402 Insufficient account balance` → 组件条目全部 `aborted`，探针 FAIL。
判别方法：看日志里 `tool_loop ... 工具型调用失败: Error code: 402` 与
`[xxx_gen] LLM 完成: 0 字符` —— **0 字符 + 毫秒级耗时 = 服务端拒绝**，不是模型"不会做"。
此时几何类结论改用**不花模型钱**的确定性路径（`probe_core_orientation.py` 用
`_fallback_plan` + `build_deterministic_skeleton`；`probe_elevator_fixer_on_real_skeleton.py`）。

