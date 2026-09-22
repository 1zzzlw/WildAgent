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

# 四层能力口径对齐
C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe \
  ../.workbuddy/diag/audit_capability_parity.py

# 光照/环境/后期链路唯一事实源（静态，退出码即结果）
node ../.workbuddy/diag/audit_lighting_single_source.mjs

# 查看器光照运行时体检（真浏览器；须先构建单文件产物）
node ../.workbuddy/diag/audit_viewer_lighting_runtime.mjs

# 屋顶覆盖诊断正例/反例回归
cd wild-web && node ../.workbuddy/diag/audit_roof_coverage_diagnostic.mjs
```

⚠️ `pytest tests` **全量必崩** → 按目录跑（预存失败：`test_execution_plan.py` 的层数约束用例）。
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
- `audit_capability_parity.py` 管**四层口径一致**（schema / 引擎 / 生成侧 / 验收侧）

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
