# WildAgent 项目长期记忆

> 只留硬约束；命令/判据/排查细节见同目录 `GATES.md`，当日细节见 `YYYY-MM-DD.md`。超限从尾部截断 → 要紧的放最前。

**协作方式**：**先方案、后落地**；🔴 跟着他的思路走、不引导（需决策的事一句话点出）；输出偏表格+`file:line`+🔴🟡⚪。他的红线就是红线（"能力缺失只标记不阻断"）。上一条说错了，第一句就更正。

## 一、知识库 `wild-server/storage/knowledge_base/`
- 🔴 schema 两副本须字节一致：`wild-core/schema.json` ↔ `storage/.../schema.json`。不建 v2。
- 🔴 **检索契约=5 组硬编码过滤对**（改 metadata 会查空）：`blueprint_spec`+`protocol`｜`component`+`capability`｜`recipe`+`relation`｜`recipe`+`entity_name=supported_assembly_relations`｜`component`+`topic=parameters`。
- frontmatter 用 `_parse_metadata_lines`（**非 YAML**），`source` 已废；增删文档同步 `config.yaml::required_documents`。
- 🔴 KB 内矛盾条目，模型挑 authority 更高/更像硬约束的那份（已致 L 形侧翼无屋顶）→ 改"能做/不能做"表前先 grep 全库有无相反的话。
- 🔴 向量只含标题+正文 → 改完 md 必须重建索引（`resync_knowledge_index.py`）；`lantu/`、`docs/` 的文档 agent 看不到。
- 🔴 **KB 是"什么算合法"的第二实现**：改骨架/几何口径（尺寸来源、必填、交互入口与**左右键**、单层禁例）必须同批改 `knowledge/components/*.md` + `capability-boundaries.md`。

## 二、蓝图坐标语义（写错就悬空/穿透）
- **墙** `from[1]`=墙底、`to[1]`=墙顶（有 `height` 用它），转角两墙共用同端点（容差 0.01m）。**楼板** `from[1]`=板底、`thickness` 向上。**门窗** `from=[沿墙距离, 开口底世界Y, 法向偏移]`，底部 Y 须在宿主墙内。
- **屋顶** `position[1]`=承托墙顶（gap>0.15 判悬空），`span/depth`≈承托墙跨+0~2m，`roofType` 只 6 值。
- 🔴 构件 `from[1]` 语义不统一：`balcony`=板顶、`canopy`=板中心 → 用世界包围盒实测。**楼梯**端点须命中楼板标高或墙顶、±0.25m 内；碰撞 AABB 按 `width/2` 双侧膨胀。
- 🔴 **竖向构件只许落在"多楼层投影的公共矩形"内**（`spatial_geometry.shared_footprint`），不许用建筑包围盒：L/U 形用包围盒定位必然超模。
- 🔴 **竖向交通的朝向不得硬编码在某个轴上**：井道放在公共区**长轴的起点端**、楼梯在其外侧。候选梯面 = **长轴起点端那面墙**（长轴沿 z → 核心筒 `front`；沿 x → `left`）；**分隔墙垂直于候梯面**，且**只在双联井里存在**（单井加分隔墙会把 2.4m 面宽切成两格 0.9m，那扇居中的门正好压在墙上）。井道尺寸是**设备尺寸**（单井 2.4×2.6 / 双联 4.6×2.6），**不按建筑宽深缩放**。
- 🔴 门窗 `from[0]` = 沿宿主墙从 `from` 端点起的距离、指向**开口左边缘**（不是中心）；井道反推（`_resolve_core_shaft`）必须同时认**竖直**（`abs(tx-fx)<1e-6` → 切 x）与**水平**（`abs(tz-fz)<1e-6` → 切 z）两种分隔墙。

## 三、门禁与验证
> 🔴 命令/判据/盲区/出图/单文件构建全在 `GATES.md`，动手前先读。`verify_wild_blueprint.py`=数据合法性；`check_blueprint_render.mjs`=真实链路；`audit_capability_parity.py`=多层口径。⚠️ 校验器全绿 ≠ 引擎能重建。
> 🔴 **加 WILD 契约字段要改三处**，少一处线上报"包含不支持的字段"：`blueprint_parser.py::component_allowed`（**严格白名单**）、`spatial_tools.py` 枚举白名单、`schema.json` 两副本。`verify_wild_blueprint.py` 只跑 spatial_tools 那套 → **查不出白名单缺失**，须单独调 `validate_blueprint_schema()`。`components.py::optional_fields` 是死字段。
> 🔴 `wild-web/lantu/viewer/dist-standalone/index.html` 是**被 git 跟踪**的构建产物：出图临时换蓝图后必须 `git checkout --` 还原。
> 🔴 **改完生成链必须拿真模型跑一遍**：`tests/agent/test_plan_chain_e2e.py` 把 `material_planner`／`skeleton_generator` **整节点替换成桩件** → 节点内校验/白名单/预检**一行都不执行**。探针 `.workbuddy/diag/probe_{object,architecture}_chain_live.py`（退出码即结果）；三个探针坑与"通用几何通道偶发空输出"见 `GATES.md` §十三。
> 🔴 **注册表类的"同类异构"是静默杀手**：`COMPONENT_TOOLS` 契约是"取出函数直接调用"，`furniture` 曾是唯一存 `@tool` 装饰的 `StructuredTool` → `'StructuredTool' object is not callable`，家具**生成成功却每次校验都炸**→0 件家具，表面像"模型不会做家具"。凡"按类型取函数再调用"的表须逐项断言类型（`tests/agent/test_component_tools_registry.py`）。
> 🔴 **交付口径的规则不得用在生成中间态**：`validate_blueprint_schema(..., allow_empty_geometry=False)` 默认拒空蓝图，但**物件骨架按设计就是空容器**。修法=给校验器加**显式 opt-in**（不删规则、不在调用点过滤），回归测试同时钉"默认仍拒"+"opt-in 只放过这一条"。
> 🔴 **模型给的空数组不得覆盖用户点名词**：`planning.py::detail_packages` 曾完全采信模型的 `[]`，把 `fallback` 点名项清空 → `component_quota`／`required_components` 一起消失（"要家具却没家具"的真根因，**不是 RAG 没检索到**）。点名项须强制并入且**排最前**（末尾 `[:6]` 会截断）。
> 🔴 **新能力要"有派发通道"才算落地**：`elevator` 曾在 `_DETAIL_COMPONENT_QUOTAS` 与 `_default_detail_packages` 两处都缺 → 骨架有 `wall_core_*` 与门洞却无配额 → "有井无梯"。
> 🔴 **负例验证**：把缺陷注回去，期望"恰好新增用例红、原有用例仍绿"，验完彻底还原（grep 探针标记确认无残留）。
> 🔴 **模型通道不可用时，几何类改动仍要闭环**：`.workbuddy/diag/probe_core_orientation.py` 用**确定性回退计划**跑**真骨架生成器**（不花模型钱），查分隔墙⊥候梯面 / 井格 ≥1.8×1.8 / 门洞落在井格开间内 / 修复后轿厢 ≥1.3m 宽；`probe_elevator_fixer_on_real_skeleton.py --src=` 吃该骨架验修复器。**"手写输入全绿 ≠ 真骨架成立"**：本轮三个朝向缺陷全是在这两支探针里撞出来的，单测一条都没红。
> 🔴 **手写骨架输入是单测的最大盲区**：`_append_vertical_core` 这类"按朝向生成"的函数，参数化用例必须**两个轴向都覆盖**（长轴沿 x 与沿 z 各一例），否则硬编码轴永远不报错。

## 四、仓库布局与渲染链路
- 🔴 `wild-core` 独立包（`file:../wild-core`），**仓库根禁放 `package.json`**；`wild-web/src/wild-{core,compiler}` 已不存在；`vite.config.ts` 须写 `server.fs.allow:['..']`。
- 🔴 渲染链路=`wild-web/src/renderer/`；**绝不在查看器自实现材质/网格/光照**。
- 🔴 `reconstructWildEntity` 契约：`mesh.materialRef`=材质名**字符串**；`materialParams` 与 `meshes` **等长平行数组**。**含洞的墙仍是 1 mesh** → 网格数不能证明没开洞（量立面面积）。
- 🔴 观感问题一律用真图判（本机有硬件 WebGL）；单文件查看器 `dist-standalone/index.html` 双击即看；`file://` 出图须加 `--allow-file-access-from-files`。
- ✅ **光照/环境/后期已收进 `src/renderer/`**（S0）：`environmentRuntime`/`lightingRuntime`/`postProcessingRuntime`；引擎目录外禁光源/PMREM/`scene.environment`/合成器。
- **A/B/C**：A=纯渲染几何、B=渲染私有 `_` 直接做；**C=WILD 契约参数须事前获批**。🔴 禁止按 `roofType`/构件类型写专属分支加能力 → 抽成通用算子。
- 🔴 **后端字段白名单有两份，漏一份就静默丢字段**：`blueprint_parser.py::component_allowed`（**硬编码**，报"包含不支持的字段"）+ `blueprint_normalizer.get_component_allowed_fields()`（**从 `storage/knowledge_base/schema.json` 派生**，只静默 `剥离字段`）。
- 🔴 **嵌套契约字段（如 `door.interaction.*`）的枚举门在 `blueprint_normalizer._validate_against_schema`（jsonschema 严格）**：`validate_blueprint_schema()` **不查嵌套枚举**，`spatial_tools` 只查 door 的**必填**字段。改嵌套枚举只需动两份 `schema.json`。
- 🔴 **门窗开合有唯一运行时消费点**：`attachedToWall.ts::createOpeningInteraction` → `renderEntity.ts::setOpeningInteractionProgress`。**只有两分支**：`swing` 绕 Y 转、**其余一律走 `openOffset` 平移** ⇒ 新增平移类 mode（如 `lift`）只需编译器给 `openOffset` 赋值，**渲染侧零改动**。`openDistance` 按 mode 分叉、`lift` 位移被钳到墙顶净空 → `GATES.md` §十。
- 🔴 **`interaction` 的消费点只有编辑器视口** `CanvasViewport.vue:708 handleContextMenu`，且绑定在**右键**（左键留给选中高亮）；`lantu/viewer` 是**纯展示**（无 `Raycaster`/`pointerdown`）。说"电梯能按"须限定"编辑器 + 右键"。
- 🔴 **`door.leafRows` 几何真生成、线数正确，但 8mm 凸起只有 5~13/255 灰阶** → 可见性随门在画面里的大小变化。"一眼认出卷帘门"必须叠加深色/金属 `leafMaterial`；**不许为可见性放宽厚度门禁**（总厚 ∈ `(0.04, 0.08]`，见 `GATES.md` §10.1）。
- 🔴 **改 `wild-core` 几何/材质后必跑**：`check-wild-core.mjs` / `check-component-compiler.mjs` / `check-rendering-pipeline.mjs`。✅ **2026-09-25 三关全绿**（"`SHADER_VERSION` v3 vs 期望 v2 存量红"**已作废**：那是 `e2ba4f7` 有意升 v3+调 `relief` 0.016 时门禁没跟上，期望值已补齐）。
- 🔴 **联合类型新增成员后，所有收窄处必须显式列分支，禁止 `else` 兜底**：`InteractiveElementBehavior = opening|light|elevator` 加了 `elevator` 后，`renderEntity.ts:101` 的 `if(kind==='opening'){…}else{ 当灯初始化 }` 同时**编译报 TS2345**（`vue-tsc` 卡死 Jenkins）**且运行期错**（电梯读 `undefined` 的 `lightType/color`）。⇒ 加联合成员时把 `interaction.kind` 全部判定点 grep 一遍，逐个确认是 `===`。
- 🔴 **`scripts/check-*.mjs` 里硬编码的期望值是"能力契约"，加构件/改参数必须同批更新**：`e744eba` 加 `elevator` 漏改能力清单 → 门禁红。能派生的就别写死（类型数改成从 `getComponentCapabilities().length` 派生）。
- 🔴 **Jenkins 只跑三件事，`scripts/check-*.mjs` 不在其中**（红了不阻断部署）：`git archive HEAD` 上传 → 前端 `npm ci && npm run build`（= `vue-tsc -b && vite build`）→ 后端 `uv lock && pytest tests` → `docker build`（`wild-web/Dockerfile` 内部同样 `npm run build`）。⇒ **部署失败先看 `vue-tsc`**；`wild-core` 的 `exports` 指向 `.ts` 源码、`git archive` 不带未跟踪文件**不构成隐患**。

## 五、曝光与光照（S1）
- 🔴 曝光/光强**唯一事实源**=`TIME_PRESETS`+`ENVIRONMENT_PRESETS`+天气；`worldLookRuntime` 默认 profile 倍率必须全为 1；标定必须"**走预设、不传 `?exp=`**"（门禁 `audit_exposure_calibration.mjs` 是**区间**断言）。three 0.160.1 无 `scene.environmentIntensity`；`Sky` 的 `rayleigh` 调大让天空更白不是更蓝。
- 🔴 **`vite build` 通过 ≠ 源码没问题**：打包器提升顶层 `let`、**掩盖 TDZ**（查看器曾整体不执行）→ 改查看器必须走 dev server 或 `probe_url_errors.mjs`。🟡 白墙在 ACES 高光平坦区，"去塑料感"性价比：**几何细部 > 材质不匀 > 贴图**。详见 `GATES.md` §十二。

## 六、协作与判定硬约束
- 🔴 **两个同源克隆，工作树已分叉**：`E:/work/WildAgent`（活跃开发）与 `E:/AgentProject/WildAgent`（**旧链** + 渲染引擎 + **lantu 查看器在 `wild-web/lantu/`**）。HEAD 同为 `4bc9645`，但**未提交改动互不可见** → 动手前先问清在哪个树。
- 🔴 **跨树移植只能"值级"**：AgentProject 走 `wild-core` **包抽取**（`import ... from 'wild-core/materials'`），`E:/work` 仍是内部目录布局 → 整目录搬 renderer 会 40+ `Cannot find module 'wild-core/*'`。
- 跑 wild-server 一律 `wild-server/.venv/Scripts/python.exe`；`pytest tests` **全量能跑通**（2026-09-25 实测 946 passed / 1 xfailed，~10s），旧结论"全量必崩"**已作废**。⚠️ 必须非沙箱（沙箱内 `tests/rag/test_rag_background_sync.py` 5 F）。
- 🔴 **生成链双目标**：`DesignDecisions` 是 **`kind` 判别联合**（`architecture`｜`object`）；判定 `routing.detect_target_kind`，`api/ws_agent.py:639` 非 architecture 时 `building_type="asset"` → `object_design`。object 分支**结构上产不出** `massing/volumes/facades/roof`。竖切包 `app/agent/generation/objects/`。
- 🔴 **目标判定只能建在闭集侧**：只有"命中建筑类型闭集"（`is_architecture_request`）才判 `architecture`，其余一律 `object`。建筑类型是**闭集**、物件名是**开放集** ⇒ "不是已知物件 ⟹ 是建筑"永远不成立。🔴 **不许为任何物件名单独写规则**（用户红线：生成一个小人和生成一个桌子是同一个测试用例）。
- 🔴 **elements／components 分桶必须读 registry `is_element`，禁止硬编码类型名**（`utils/fragment_merger.py::_is_element_type`）。曾硬编码 `== "roof"` → `furniture` 被塞进 `components`，而 reconcile／校验只在 `elements` 找 → 家具"永远没落地"→ **无限重试到放弃**。
- 🔴 **归一化不是类型过滤器**：`_repair_elements` 曾无条件丢弃 `type=="body"` → 最终蓝图空。现为**迁移不丢弃**（字段值对齐 `wild-core/.../body.ts`）。
- 🔴 **"一个物件 = N 个零件"的通道只能设下限、不能设上限**（`design/resolver.py` 曾按 `count` 设 `component_quota[kind].max` → 4 零件花瓶被读成"4 个花瓶超上限"）。⇒ **凡"一个数被当两个单位用"，先问单位与被施加对象是否同一语义**。
- 🔴 **同一语义、不同单位 ⇒ 迁移；语义本身不合法 ⇒ 才交给校验器**：`rotation` 契约是**弧度 vec3**，模型常写度数标量 `180` / 度数数组 `[0,90,0]` → 校验器如实报错但**整批 8 个片段判死 → 0 件家具**。唯一规则函数 `app/utils/rotation.py`（`coerce_rotation`；**2π 分界** + 非零分量须为 15 的整数倍，认不出返回 `None` 不猜）挂**三处**：`component_workflow.py::_coerce_fragment_rotations`（**校验之前**，第 4.5 步）/ `blueprint_normalizer._repair_elements` / `objects/planning.py::normalize_primitive_part`。🔴 **只测辅助函数 = 假绿**：注掉调用点后 40 条仍全绿 ⇒ 必须有**走真实节点函数体**的用例钉"调用点存在"（`test_component_generator_smoke.py::test_furniture_generator_migrates_degree_rotations`）。
- 🔴 **`prompts/generation.py` A／E 段跨 kind 通用**；E 段 host 占位**数据驱动**（`_host_bound()` 读 registry `required_fields`），**不许写死 `parentWall`**。B 段逐条只放 `objects/skeleton.py::object_specs()`。
- 🔴 **`furniture` 不是能力缺口**（引擎 10 subtype 齐全）；缺的是**房间划分** → 映射 `floor_plan`。
- 🔴 **唯一剩余引擎侧能力缺口**：`balcony.ts:41` 自建内嵌 `RailingComponent`、**不透传 `infill*`** → 阳台玻璃栏板做不了。（"`furniture` 无 rotation" **已作废**：`rotation` 是契约字段 + `geometry/furniture.ts` 已实现，正面朝 +Z。）
- 🔴 同一文件不要同一批发两个 Edit（CRLF 丢更新）；🔴 **追加中文一律用 Edit，禁用 `cat >> file << EOF`**（会从第 2 行起覆盖且 `wc -l` 不变）。追加后 `grep -n "^## "` 核对。
- 🔴 **能力缺失只标记、不阻断**（缺能力→`unsupported`+warn；媒介不一致→`needs_review`+warn；计划对象不合法/模型终态错误→`error`）。`severity` 是唯一阻断杠杆。
- 🔴 `_compile_acceptance` 是**按序命中的 if 链**，具体分支排更泛的前面。roof 数量硬编码：仅 `_PER_VOLUME_ROOF_TYPES` 且顶层 ≥2 体量可切。
- 🔴 **"能力已实现却无人派发"是独立缺陷** → 对齐四个注册点（schema / 引擎 primitive registry / `COMPONENT_REGISTRY`+`skeleton.py` / `_UNSUPPORTED_COMPONENT_ALIASES`），脚本 `audit_capability_parity.py`；**审计脚本不得写例外白名单**。
- 🔴 闸门/提示词顺序红线：**能力落地前不许先放宽判定**；室内=房间层 P2 未实现，闸门与 `prompts/planning.py:193` 须同批改。
- ⚪ `app/agent/dynamic/` 已整体删除且从未入库（只活在 `__pycache__`），**非实现依据**。
- 🔴 同一参数被两处夹取就分叉：`overhang` 计划侧 0~2m（`planning.py:614`）vs 几何侧 `max(0.15,min(0.8,…))`（`facade.py:205`）→ 验收读计划值。
- 🔴 **重构删代码后必跑未定义名扫描**：`check_undefined_names.py`（纯 AST）；导入扫描/图编译/单测三关都拦不住运行期 `NameError`。节点冒烟另有盲区——`if on_reasoning_delta:` 类 runtime `ContextVar` 守卫，**测试必须 `bind_reasoning_callback` 才进得去**（`plan_feedback` 曾这么隐身）。
- 🔴 **单文件查看器出图要指定蓝图**：`lantu/viewer/vite.config.standalone.mjs` 吃 `BP_FILE=<wild-web/lantu/ 下的 .wild>`。出图后**必须**删临时 `.wild` 并 `git checkout -- wild-web/lantu/viewer/dist-standalone/index.html`。
