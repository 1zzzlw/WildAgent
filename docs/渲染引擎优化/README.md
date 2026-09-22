# 渲染引擎优化

本目录汇集 WildAgent 前端渲染链路（`wild-web` 视口 + `lantu/viewer` 查看器）的**诊断流程、改动分级规则、优化方向与实施记录**。

核心主张：**渲染效果问题绝大多数不需要新增参数**。WILD 蓝图是前端与后端共同依赖的契约，改它会连带知识库、提示词、后端校验和既有 `.wild` 文件；所以先把「参数边界」划清，再决定在哪一层动手。

## 文档索引

### 一、方法与规则（先读这两份）

1. [渲染问题诊断流程](渲染问题诊断流程.md)：三步定位法 —— ① 查蓝图参数是否合理（不合理 → Agent 侧）→ ② 跑几何验证（异常 → 几何引擎）→ ③ 看视觉表现（空心/闪烁/悬浮 → 渲染引擎；比例/位置 → Agent 侧）。
2. [渲染引擎优化指南](渲染引擎优化指南.md)：**A / B / C 改动分级**的定义与边界，以及 C 类改动必须走的六步全链（知识库 / 提示词 / 前端类型 / 后端校验 / 几何生成 / 验证）。任何"顺手优化"都要先对照这份文档定性。

### 二、方向与盘点

3. [渲染引擎优化方向](渲染引擎优化方向.md)：用代码证据划清参数边界、盘点现状、给出分层优化方向与落地顺序。

### 三、实施记录（主跟踪文档）

4. [渲染引擎优化实施计划](渲染引擎优化实施计划.md)：**P0 ~ P8 的实施记录**，含每项的现象、根因、踩坑、验证方式、验收清单，以及第四阶段的 B 类待办。这是本目录的主入口。

### 四、专题报告

5. [屋顶檐口修复报告](屋顶檐口修复报告.md)：双坡屋顶渲染为空心框架的诊断与修复（几何引擎侧，零参数改动）。
6. [前端渲染链路差异诊断报告](前端渲染链路差异诊断报告.md)：编辑器视口与独立查看器的链路差异盘点，按 🔴 真实缺陷 / 🟡 观感与健壮性 / ⚪ 细节优化三级分类。
7. [P5 面剔除评估报告](P5-面剔除评估报告.md)：C 类改动审批报告。原计划"开背面剔除省 50% 光栅化"，经全量蓝图审计后**被数据证伪并否决**（可剔除三角形仅 16.5%，`tiantan` 可见反面率 53.65%）。
8. [光影优化方案](光影优化方案.md)：**只针对光照与阴影链路**的 L1~L10 方案，外加建筑组件侧 G1~G4。含 7 个真实蓝图 × 3 时段的阴影相机覆盖复算、天气滑杆 PMREM 扇出实测、以及 three 0.160.1 源码级的死配置核查。无 C 类改动。已实施 L1~L5/L7/L9/L10 并全部通过回归（21/21 组合覆盖，审计 exit 0）。
9. [屋顶檐口定性报告](屋顶檐口定性报告.md)：用户反馈"屋顶简陋、没有屋檐厚度"的三层归因（渲染层无责 / `roof.ts` 能力缺口 / `.wild` 未使用既有 `cornice` 契约），含檐口厚度、出檐量、山墙端材质、板底形态的实测数据与三档修法对比预览。**档 2 已实施**（见实施计划 §九）。
10. [中式曲面屋顶三层归因与通用檐口方案](中式曲面屋顶三层归因与通用檐口方案.md)：档 A（承托墙判定）/ 档 B（曲面壳体绕序）/ 档 C（通用檐口算子）的方案与落地顺序。
11. [屋顶檐口通用化实施报告](屋顶檐口通用化实施报告.md)：**档 A/B/C 的实施记录与验收证据**（5 种屋顶类型覆盖、体积参照量推导、`-0` 键与环面 χ 两个判据坑、`buildFlat` 顺带修复、4 项既有问题的定性）。
12. [真浏览器出图链路与屋顶覆盖诊断修复](真浏览器出图链路与屋顶覆盖诊断修复.md)：**本机能做真实 WebGL 渲染（RTX 4060 / ANGLE-D3D11）** 的前提更正、CDP 出图链路、`RECONSTRUCTION_ROOF_COVERAGE` 多体量误报的判据修复与回归门禁；并指出 🔴 **光照/look 没有 `src/renderer/` 入口**（Sky+PMREM 内联在 `CanvasViewport.vue`）这一待拍板的架构缺口。§六 含**单文件查看器**（`vite.config.standalone.mjs`，`file://` 双击即看）与逐角投影取景。
13. [能力口径审计与照片还原精度差距](能力口径审计与照片还原精度差距.md)：用户提供《WILD 蓝图设计语言》并反馈"不够精细"后的归因。文档与 schema 一致但不在 KB；**主因是引擎已实现的能力没有生产者**（`furniture` 四处说能用、只有生成侧注册表与验收表说不能用，已实测证明引擎能建）；`overhang` 计划夹取 0~2m 与几何夹取 0.15~0.8m 分叉导致"出檐不小于 N"只在纸面成立。附 `audit_capability_parity.py` 四层口径审计门禁。**未改流水线代码**。
14. [渲染引擎现状评估与照片级路线](渲染引擎现状评估与照片级路线.md)：回答"引擎有没有问题 / 如何生成照片级图形"。结论 = **3 个真问题**（🔴 P0 IBL 无 `src/renderer/` 入口；🔴 P1 AO 只在前端组件；🟡 P1 材质表现力单一），并**明确区分"不是引擎问题"的项**（出檐浅/柱细/水面平属生成数据）。给出 **S0~S5 路线**：S0 把「环境→PMREM→`scene.environment`」+ composer/AO 提取到 `src/renderer/`（A 类，ROI 最高，同时消除"查看器自实现光照"的红线违规）。**只读代码，未做任何改动**。
15. [S0 实施报告：光照与环境链路收进引擎](S0实施报告：光照与环境链路收进引擎.md)：**S0 已落地**。新增 `environmentRuntime` / `lightingRuntime` / `postProcessingRuntime` 三个引擎运行时；编辑器视口净删约 230 行内联实现、查看器删除自建的 3 盏灯并接入引擎运行时（新增 `?time` / `?env`）。配两道门禁：静态（引擎目录外禁止光照实现）+ 运行时（真浏览器断言 IBL 已挂载、无自建环境光、光源骨架正确）。附前后真图对比与**残留问题**（白天偏白 ⇒ S1 标定）。
16. [字段数量不是精细度的瓶颈：169 份蓝图字段使用率实测](字段数量不是精细度的瓶颈：169份蓝图字段使用率实测.md)：回答"是不是字段太少 / 补字段会不会更精细"。**实测否定该假设**：`roof.tiers`/`tierHeight`/`eaveCurveHeight`/`curveProfile`/`eaveOutset`/`shrinkFactor`、`column.entasis`/`flutes`、`wall.curve` 等 15 个"细节字段"引擎都支持，但 **169 份蓝图使用次数为 0**；材质层的 `textures`/`normalScale`/`uvScale`/`surfaceFamily`/`procedural` 同样 **0% 使用**（抽样材质只写了 baseColor/roughness/metallic）。结论：断点在「KB → 模型 → 蓝图」这一段的生产者，不在字段数量。

17. [S1-S2 实施报告：曝光标定与矿物面抹灰特征](S1-S2实施报告：曝光标定与矿物面抹灰特征.md)：**S1 已落地**。把"发白/发闷/像塑料"翻译成三个可计算的量（过曝比 / 天空 B−R / 细节能量），据此重标三时段的曝光与光强：白天过曝比 **33.6% → 0%**、细节能量 **0.928 → 1.202**、天空 `rgb(239,243,245)`（纯白）→ `rgb(165,188,202)`（天蓝）。反直觉点：**提高 `rayleigh` 会让天空更白**（官方示例值直接套会把正午洗成灰白）。S2（矿物面抹灰）**机制落地但按实测不构成可见收益**，原因与证据如实记录；AO 半径经实测确认**不是杠杆**（凸体上没有可遮蔽处）。附四个顺路修掉的真 bug（其中一个是**只有 dev server 会暴露的 TDZ**，打包构建因变量提升而侥幸通过）。

## A / B / C 改动分级（速查）

| 级别 | 含义 | 要做的事 |
|---|---|---|
| **A 类** | 纯渲染实现，零参数改动（约 90% 场景） | 直接做 |
| **B 类** | 渲染私有字段（`_xxx` 下划线前缀），不进知识库 | 前端类型加可选字段，后端不动 |
| **C 类** | WILD 契约参数，影响知识库 / 提示词 / 后端校验 / 既有文件 | **先报告获批**，再走六步全链 |

优先级：**A 类 > B 类 > C 类**。

## 当前状态

| 项 | 内容 | 状态 |
|---|---|---|
| P0 | 阴影落地感（各环境档阴影不透明度 0.22~0.34 → 0.40~0.46） | ✅ |
| P1 | 统一取景（街角俯角 0.62 → 0.72，编辑器与查看器对齐） | ✅ |
| P2 | 表面凹凸层（米制高度场 + 无参数化凹凸，masonry 出砖缝/瓦垄） | ✅ 代码完成，观感待人工确认 |
| P3 | 抗锯齿（合成链路 MSAA 4x，WebGL1 与低帧率自动回落） | ✅ |
| P4 | SSAO 默认开启（核实后确认默认档本就开启，无需改动） | ✅ 无需改动 |
| P5 | 面剔除 | ❌ 已被数据证伪，不实施 |
| P6 | 世界法线着色修正（天气遮罩不再随相机旋转） | ✅ |
| P7 | 阴影脏标记原子化 | ✅ |
| P8 | 生成结果居中归一化（建筑落在网格中心） | ✅ |
| L1~L10 | 光影链路优化（夜晚主光方向 / 阴影相机覆盖与 far / PMREM 扇出 / SSAO 分辨率 / 死配置 / 夜间 Bloom / 贴花色 / 空气透视 / 拖动滞后 / normalBias） | ✅ L1~L5·L7·L9·L10 已实施；L6(b)、L8 暂缓 |
| E1~E5 | 檐口线脚（B 类几何增强）：自动封檐板 + 滴水线 + 博风板 + 山墙饰面；屋面与线脚拆成两块网格、两种材质 | ✅ 已实施并通过门禁 |
| **E6** | **檐口通用化（档 A/B/C 一次性实施）**：承托墙改按墙顶标高筛 + 曲面壳体绕序/法线 + 檐口改通用边界环扫掠；`buildRoof` 内部 roofType 分支 **3 → 0**、檐口覆盖 **2/6 → 6/6** | ✅ 见 [屋顶檐口通用化实施报告](屋顶檐口通用化实施报告.md) |
| G1~G4 | 内容侧光影空间（生成器不产灯光 / 法线硬边 / AO 通道 / 半透明投影） | ⏳ 未启动 |
| **S0** | 光照/环境/后期链路收进 `src/renderer/`（IBL 有引擎入口，消除"查看器自实现光照"红线违规） | ✅ 见 [S0 实施报告](S0实施报告：光照与环境链路收进引擎.md) |
| **S1** | **曝光/光照/天空标定**：三时段曝光与光强重标 + `rayleigh/turbidity` 重标（白天过曝 33.6% → 0%） | ✅ 见 [S1-S2 实施报告](S1-S2实施报告：曝光标定与矿物面抹灰特征.md) |
| **S2** | 程序化材质族补可见特征（矿物面抹灰 / 木纹板缝） | 🟡 机制已落地，**当前样本上实测不可辨**（白墙压在 ACES 高光段平坦区） |
| **S3** | 几何细部算子（洞口侧壁 reveal / 檐下顶棚 soffit / 板边收边） | ⏳ 未启动（本轮实测把它推到性价比首位） |
| **S5** | 贴图资产通路（C 类，需先获批蓝图字段） | ⏳ 未启动 |
| B 类 | ~~檐口线脚~~（已完成）/ 屋脊瓦 / 山墙通风口 / 勒脚 / 窗套 | ⏳ 部分完成 |

## 验证与诊断工具

全部位于 `.workbuddy/diag/`，均可在**无浏览器**环境下运行（用 vite `ssrLoadModule` 跑真实重建链路）；命令一律在 `wild-web` 下执行：

| 脚本 | 用途 |
|---|---|
| `verify-surface-relief.mjs` | 材质着色器补丁命中 + 高度场坡度/ASCII 图案 |
| `relief-preview.mjs` | 表面凹凸离线着色预览出 PNG，肉眼判读质感 |
| `verify-roof-solid.mjs` | 屋顶**逐连通分量**水密性 / χ=V-E+F=2 / 体积校验（屋面实体 + 檐口线脚各自断言） |
| `audit-eave.mjs` | **檐口门禁**：回退路径不变性 + 管线实测（线脚尺寸/材质/分量数/体积）+ 源码契约断言 + 全仓库 gable/hip 批量回归 |
| `audit-winding.mjs` | 全量网格拓扑审计（闭合性 / 绕序一致性 / 外法线）+ 可见反面率实测 |
| `audit-centering.mjs` | 生成结果居中诊断 + 归一化校验 |
| `audit-lighting.mjs` | **光影链路审计 + 回归门禁**：主光方向 / 阴影相机覆盖（U·V·far·near）复算 / 环境变更 PMREM 扇出 / RT 分辨率语义 / 光照预算 vs Bloom 阈值；并对源码做实现契约断言，退出码即门禁结果 |
| `material-family-report.mjs` | 材质名 × surfaceFamily × 实现的面积盘点 + UV 取值范围 |
| `check-rot.mjs` | 逐元素世界包围盒（**含 rotation**），核实几何落位 |
| `preview-eave.mjs` | 屋檐改造**前/后**对比预览出 PNG（before = 剥掉 `_eave`，after = 现管线） |
| `png-ascii.mjs` | PNG 反读成 ASCII 灰度图（供无法读图的环境判读渲染结果） |
| `check-coplanar.mjs` | Z-fighting 风险检测 |
| `depth-ascii.mjs` | ASCII 深度图 |
| `lib/solid-check.mjs` | 闭合实体校验库（水密 / 连通分量 / 逐分量 χ / 体积 / 包围盒） |
| `lib/eave-spec.mjs` | 檐口尺寸规则与解析体积的**门禁侧镜像实现**（与 `roof.ts` 同步，源码断言防漂移） |

### 2026-09-21 新增：真浏览器出图 + 定量判据

> ⚠️ 上面那句"均可在**无浏览器**环境下运行"从现在起只是"能跑"，不再是"只能这么跑"：
> **本机有硬件加速 WebGL**（NVIDIA RTX 4060 / ANGLE-D3D11），观感类问题请用真图判，别再用 CPU 复刻的近似图。

| 脚本 | 用途 |
|---|---|
| `shot_lantu_viewer_cdp.mjs` | 🔴 **真浏览器多机位出图（首选）**。CDP 轮询 `window.__wildViewer.ready()` 等重建真正完成再截；`chrome --screenshot + --virtual-time-budget` 会截到空帧且**不同视角字节相同**，勿用 |
| `audit_wall_openings.mjs` | 宿主墙**到底有没有被开洞**（按立面三角形总面积对比理论值），是**定量判据**不是目测 |
| `probe_material_binding.mjs` | 每个网格绑的是哪个材质；核实 `materialRef` ↔ `materialParams` 的平行关系 |
| `audit_roof_coverage_diagnostic.mjs` | 屋顶覆盖诊断的**正例 + 反例**回归（多体量分段不许报 / 真缺一块必须报） |
| `render_preview.mjs` | CPU 软件光栅化出 PNG —— **只留给几何体检**（不做透明/阴影，观感不可信） |

### 2026-09-21 新增：曝光标定与量化判据（S1）

> 起因：S0 把 IBL 接进引擎后白天过曝（33.6% 像素 ≥240、天空整片纯白），而**没有任何门禁发现它** ——
> 观感上只表现为"模型不够精细"。所以把当时靠人眼发现的三件事固化成断言。

| 脚本 | 用途 |
|---|---|
| `audit_exposure_calibration.mjs` | 🔴 **曝光标定门禁**：真浏览器出图 + 断言（过曝比 ≤2% / 亮度带 / 天空亮度 / 天空 B−R ≥18），覆盖 day·sunset·night 与**最亮的 desert 档**。⚠️ 断言的是**区间**不是等值：写死等值只会逼后来者"改断言而不是改参数" |
| `lib/pngStats.mjs` | **零依赖 PNG 解码**（Node `zlib` inflate + 反滤波）+ 亮度/过曝/细节能量/分位数 + 分区域 rgb·std·detail + 裁剪并排落盘。本机没有 PIL/sharp，而这类活儿必须靠数字收口（37% 像素打到 240+ 时，再亮 10% 与再亮 30% 看起来一样白） |
| `lib/regions.mjs` | 分区域量化（`STATS=detail` 出区域 std 与 detail）。判断"材质特征有没有生效"要看**区域内**的 std/detail，且**必须同曝光比** |
| `lib/rgbcheck.mjs` | 抽查指定区域的平均 RGB —— 判"天空是不是被打白"（B−R 趋近 0）用 |
| `lib/mkview.mjs` | 生成**小尺寸并排对比图**，供人眼判读（2400×1500 的原图既塞不进上下文也没法并排） |
| `sweep_exposure_calibration.mjs` | **单会话**批量扫 `曝光 × 光强 × 天空参数`。单会话是关键：每次 reload 都要重跑蓝图重建 + PMREM，30 个组合靠 reload 要等一分钟以上 |
| `probe_url_errors.mjs` | 打开 URL 并打印 console / 未捕获异常 / 资源失败。出图脚本只报 `phase=no-handle` 时靠它定位"模块为什么没跑起来" |

```bash
# 曝光标定门禁（默认打单文件产物 file://，不需要 dev server）
cd wild-web/lantu/viewer
node ../../node_modules/vite/bin/vite.js build --config vite.config.standalone.mjs
cd E:/AgentProject/WildAgent && node .workbuddy/diag/audit_exposure_calibration.mjs

# 扫参（找新时段的曝光/光强用）
COMBOS_JSON='[{"exposure":null,"key":1,"hemi":1}]' \
  node .workbuddy/diag/sweep_exposure_calibration.mjs day e
```

> ⚠️ **出图必须走 `file://` 或 dev server，两条路都行，但 `file://` 要加 `--allow-file-access-from-files`**：
> 少了这个开关，ES module 会被 CORS 拦掉，表现是"句柄建不出来"或"canvas 全黑"两种假象，
> 极易误判成渲染坏了。另外 `shot_lantu_viewer_cdp.mjs` 已不再默认强传 `?exp=1.05`
> （正是它让"预设曝光不准"长期没被发现）——验证"交付状态"请**不要**传 `exp`。
> 另一个坑：**查看器 dev server 会自己死掉**（表现为 502），批量出图前先 `curl` 一下。

### 2026-09-21 新增：能力口径审计

| 脚本 | 用途 |
|---|---|
| `.workbuddy/diag/audit_capability_parity.py` | **四层口径对齐**：schema 声明 / `wild-core` primitive 实现 / 生成侧生产者（组件注册表 + 骨架直出）/ 验收侧"不支持"表。抓"能力已实现却永远不派发"这类矛盾，退出码即结果（`--json` 出机器可读）。⚠️ 审计脚本**不要写白名单**：它的第一版把 `furniture` 放进白名单，于是"全绿"，而 `furniture` 恰恰是它该抓的 case |
| `.workbuddy/diag/make_furniture_probe.py` | 往蓝图副本插 8 个 `furniture` 元素（餐桌/椅/躺椅/落地灯），用于实测引擎侧的家具重建能力；不修改原蓝图 |
| `.workbuddy/diag/probe_furniture.wild` | 上者的产物；`check_blueprint_render.mjs` 结果 PASS |

```bash
# 真浏览器出图：先起查看器，再出图（URL_BASE 也可指向单文件产物，脚本会自己补查询串）
cd wild-web/lantu/viewer && node ../../node_modules/vite/bin/vite.js --port 5180 --strictPort &
cd wild-web && node ../.workbuddy/diag/shot_lantu_viewer_cdp.mjs pool front aerial
```

**单文件查看器（双击即看，可发给别人）**：

```bash
cd wild-web/lantu/viewer
node ../../node_modules/vite/bin/vite.js build --config vite.config.standalone.mjs
# → dist-standalone/index.html（蓝图 + JS + CSS 全内联，约 706 kB）

# 验证必须走 file://，不是 http：
node .workbuddy/diag/probe_page_errors.mjs \
  "file:///E:/AgentProject/WildAgent/wild-web/lantu/viewer/dist-standalone/index.html"
```

> `dist/index.html`（默认构建）引用绝对 `/assets/…`，`file://` 下会被 CORS 拦成白屏 ——
> 要发给人看只能用上面的 `dist-standalone/`。详见
> [真浏览器出图链路与屋顶覆盖诊断修复.md](真浏览器出图链路与屋顶覆盖诊断修复.md) §六。

回归命令：

```bash
cd wild-web
node ../.workbuddy/diag/verify-roof-solid.mjs
node ../.workbuddy/diag/audit-eave.mjs
node ../.workbuddy/diag/verify-surface-relief.mjs
node ../.workbuddy/diag/audit-winding.mjs
node ../.workbuddy/diag/audit-centering.mjs
node ../.workbuddy/diag/audit-lighting.mjs --drag=60
npm run check:core && npm run check:compiler && npm run check:rendering
npx vue-tsc -b
```

> ⚠️ `tsconfig.app.json` 的 `include` 只含 `src/**`，因此 `lantu/**`（查看器）**不在类型检查范围内**，改查看器需另行校验。

## 相关文档

- [项目索引](../项目索引.md)
- [WildAgent 架构说明](../ARCHITECTURE.md)
- 知识库 WILD 参数规范：`wild-server/storage/knowledge_base/BLUEPRINT-SPEC-MINIMAL.md`
