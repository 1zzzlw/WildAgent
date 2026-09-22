# WildAgent 项目长期记忆

> 只留硬约束；命令/判据/排查细节见同目录 `GATES.md`，当日细节见 `YYYY-MM-DD.md`。超限会从尾部截断 → 要紧的放最前。

**协作方式**：**先方案、后落地**；🔴 跟着他的思路走、不引导（不每轮问"下一步做哪个"，需决策的事一句话点出）；输出偏表格+`file:line`+🔴🟡⚪。他的红线就是红线（如"能力缺失只标记不阻断"）。上一条说错了，第一句就更正。

## 一、知识库 `wild-server/storage/knowledge_base/`
- 🔴 schema 两副本须字节一致：`wild-core/schema.json` ↔ `storage/.../schema.json`。不建 v2。
- 🔴 **检索契约=5 组硬编码过滤对**（改 metadata 会查空）：`blueprint_spec`+`protocol`｜`component`+`capability`｜`recipe`+`relation`｜`recipe`+`entity_name=supported_assembly_relations`｜`component`+`topic=parameters`。
- frontmatter 用 `_parse_metadata_lines`（**非 YAML**），`source` 已废；增删文档同步 `config.yaml::required_documents`。
- 🔴 KB 内矛盾条目，模型挑 authority 更高/更像硬约束的那份（已致 L 形侧翼无屋顶）→ 改"能做/不能做"表前先 grep 全库有无相反的话。
- 🔴 向量只含标题+正文 → 改完 md 必须重建索引；`lantu/`、`docs/` 的文档 agent 看不到，要影响 agent 必须进 KB。

## 二、蓝图坐标语义（写错就悬空/穿透）
- **墙** `from[1]`=墙底、`to[1]`=墙顶（有 `height` 用它），转角两墙共用同端点（容差 0.01m）。**楼板** `from[1]`=板底、`thickness` 向上。**门窗** `from=[沿墙距离, 开口底世界Y, 法向偏移]`，底部 Y 须在宿主墙内。
- **屋顶** `position[1]`=承托墙顶（gap>0.15 判悬空），`span/depth`≈承托墙跨+0~2m，`roofType` 只 6 值。
- 🔴 构件 `from[1]` 语义不统一：`balcony`=板顶、`canopy`=板中心 → 用世界包围盒实测。**楼梯**端点须命中楼板标高或墙顶、在 ±0.25m 内；碰撞 AABB 按 `width/2` 双侧膨胀。

## 三、门禁与验证
> 🔴 命令/判据/盲区/出图/单文件构建全在 `GATES.md`，动手前先读。`verify_wild_blueprint.py`=数据合法性；`check_blueprint_render.mjs`=真实链路；`audit_capability_parity.py`=四层口径。⚠️ 校验器全绿 ≠ 引擎能重建。

## 四、仓库布局与渲染链路
- 🔴 `wild-core` 独立包（`file:../wild-core`），**仓库根禁放 `package.json`**；`wild-web/src/wild-{core,compiler}` 已不存在；`vite.config.ts` 须写 `server.fs.allow:['..']`。
- 🔴 渲染链路=`wild-web/src/renderer/`；**绝不在查看器自实现材质/网格/光照**。
- 🔴 `reconstructWildEntity` 契约：`mesh.materialRef`=材质名**字符串**；`materialParams` 与 `meshes` **等长平行数组**。**含洞的墙仍是 1 mesh** → 网格数不能证明没开洞（量立面面积）。
- 🔴 观感问题一律用真图判（本机有硬件 WebGL）；单文件查看器 `dist-standalone/index.html` 双击即看；`file://` 出图须加 `--allow-file-access-from-files`。
- ✅ **光照/环境/后期链路已收进 `src/renderer/`**（S0）：`environmentRuntime`/`lightingRuntime`/`postProcessingRuntime`；引擎目录外禁光源/PMREM/`scene.environment`/合成器。
- **A/B/C**：A=纯渲染几何、B=渲染私有 `_` 直接做；**C=WILD 契约参数须事前获批**。🔴 禁止按 `roofType`/构件类型写专属分支加能力 → 抽成通用算子。

## 五、曝光与光照（S1，2026-09-21）
- 🔴 曝光/光强**唯一事实源**=`TIME_PRESETS`+`ENVIRONMENT_PRESETS`+天气；`worldLookRuntime` 默认 profile 的光强倍率必须全为 1（否则编辑器比查看器亮 3~8%，"两界面同一套光照"不成立）。
- 🔴 标定必须"**走预设、不传 `?exp=`**"：出图脚本曾默认传 `exp=1.05`，长期掩盖预设不准。门禁 `audit_exposure_calibration.mjs`（**区间**断言，非等值）。
- 🔴 **`vite build` 通过 ≠ 源码没问题**：打包器会提升顶层 `let`，**掩盖 TDZ**（查看器曾因此整体不执行）。改查看器必须走 dev server 或 `probe_url_errors.mjs` 验一次。
- ⚪ three **0.160.1** 无 `scene.environmentIntensity`（r163 才有）→ IBL 强度只能调 `envMapIntensity` 与天空辐射量。three `Sky` 输出是任意尺度辐射量；**提高 `rayleigh` 会让天空更白，不是更蓝**。
- 🟡 白墙（albedo≈0.93）在阳光下压在 ACES 高光段平坦区 → 材质微变化 ±6% 只剩几个灰阶。"去塑料感"性价比排序：**几何细部 > 材质不匀 > 贴图**。

## 六、协作与判定硬约束
- 🔴 **有两个同源克隆，工作树已分叉**：`E:/work/WildAgent`（活跃开发：agent UI 去"计划模式"、`wild-server/app/agent/dynamic/` 设计图纸链路）与 `E:/AgentProject/WildAgent`（**旧链** planning+`generation/assembly_workflow.py`、渲染引擎 S0/S1/S2、**lantu 蓝图查看器在 `wild-web/lantu/`**）。两者 HEAD 同为 `4bc9645`、同 remote，但**未提交改动互不可见** → 动手前先问清在哪个树，别默认 cwd。🔴 **生成蓝图放 `E:/AgentProject/wild-web/lantu/`**（`E:/work` 无 lantu 查看器，别放那）。
- 🔴 **跨树移植渲染优化只能"值级"移植，不能整目录搬**：AgentProject 的引擎基于 `wild-core` **包抽取**（`import ... from 'wild-core/materials'`，根级 `wild-core/` 包）；而 `E:/work` 仍是**内部目录布局**（`../wild-core/src/materials`），没有根级 `wild-core` 包。整目录搬 renderer 会 40+ 个 `Cannot find module 'wild-core/*'`。S1 是纯数值改动（`defaultWorldLook.ts` 三时段曝光/白天光强/天空 + `worldLookRuntime.ts` 三倍率归 1），可直接值级移植，不碰 import。编辑器消费点在 `CanvasViewport.vue:1201-1246`（`preset.exposure×exposureScale`、`preset.directionalIntensity`）。
- 跑 wild-server 一律 `wild-server/.venv/Scripts/python.exe`；`pytest tests` 全量必崩→按目录跑。
- 🔴 同一文件不要同一批发两个 Edit（CRLF 丢更新）；追加中文别用 heredoc。
- 🔴 **能力缺失只标记、不阻断**（缺能力→`unsupported`+warn；媒介不一致→`needs_review`+warn；计划对象不合法/模型终态错误→`error`）。`severity` 是唯一阻断杠杆。
- 🔴 `_compile_acceptance` 是**按序命中的 if 链**，具体分支排更泛的前面。roof 数量硬编码：仅 `_PER_VOLUME_ROOF_TYPES` 且顶层 ≥2 体量可切。
- 🔴 **"能力已实现却无人派发"是独立缺陷** → 对齐四个注册点（schema / 引擎 primitive registry / `COMPONENT_REGISTRY`+`skeleton.py` / `_UNSUPPORTED_COMPONENT_ALIASES`），脚本 `audit_capability_parity.py`；**审计脚本不得写例外白名单**。
- 🔴 改闸门/提示词顺序红线（`动态节点设计规划.md` §1.5）：**能力落地前不许先放宽判定**；室内=房间层 P2 未实现，闸门与 `prompts/planning.py:193` 须同批改。
- ⚪ `app/agent/dynamic/` 已整体删除且从未入库（只活在 `__pycache__`）；已备份，**非实现依据**。
- 🔴 同一参数被两处夹取就分叉：`overhang` 计划侧 0~2m（`planning.py:614`）vs 几何侧 `max(0.15,min(0.8,…))`（`facade.py:205`）→ 验收读计划值。
