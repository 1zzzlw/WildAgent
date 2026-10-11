# plan 构件示例入库记录

2026-10-10。按用户列出的35个plan名称，生成34个最小WILD场景，新增6份活动构件知识文档。“实墙”和“实体墙”共用同一个示例。

使用 [wild-component-example](../../../.codex/skills/wild-component-example/SKILL.md) 搜索与转换，再使用 [wild-knowledge-ingest](../../../.codex/skills/wild-knowledge-ingest/SKILL.md) 完成分类、元数据、清单、真实分片、增量同步和plan召回。用户已明确授权本批直接入库。

## 状态和使用方法

这些示例已通过当前Schema、实际plan校验器、当前wild-core编译和网格重建，但没有完成浏览器渲染及用户外观验收。活动条目标为 `status: experimental`、`authority: schema`，不标 `verified_example`。Schema权威只说明字段契约，不代表建筑规范或来源产品精确还原。

`samples/*.wild` 可以独立导入现有WILD查看器或编辑器。知识文档中的JSON是局部 `elements/components/materials` 片段：前两项并入蓝图的 `geometry`，材质并入顶层 `materials`。合并时调整id、宿主引用和安装坐标，不重复添加示例宿主。所有示例尺寸、配色、数量及造型取值均为项目自行选择；本批没有用户指定的具体尺寸。

## 覆盖清单

| plan 名称 | 独立示例 | 活动知识文件 |
| --- | --- | --- |
| building_body | [building-body.wild](samples/building-body.wild) | [envelope-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/envelope-detail-examples.md) |
| 实墙基座 | [solid-base.wild](samples/solid-base.wild) | [envelope-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/envelope-detail-examples.md) |
| 落地窗 | [floor-window.wild](samples/floor-window.wild) | [glazing-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/glazing-detail-examples.md) |
| 主入口门斗 | [entrance-vestibule.wild](samples/entrance-vestibule.wild) | [entrance-door-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/entrance-door-examples.md) |
| 实墙 | [solid-wall.wild](samples/solid-wall.wild) | [envelope-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/envelope-detail-examples.md) |
| 凸窗 | [bay-window.wild](samples/bay-window.wild) | [glazing-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/glazing-detail-examples.md) |
| 阳台栏板 | [balcony-panel.wild](samples/balcony-panel.wild) | [balcony-equipment-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/balcony-equipment-examples.md) |
| 通高窗 | [double-height-window.wild](samples/double-height-window.wild) | [glazing-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/glazing-detail-examples.md) |
| 装饰壁柱 | [decorative-pilaster.wild](samples/decorative-pilaster.wild) | [roof-facade-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/roof-facade-detail-examples.md) |
| 庭院门 | [garden-gate.wild](samples/garden-gate.wild) | [entrance-door-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/entrance-door-examples.md) |
| 大面积玻璃移门 | [glass-sliding-door.wild](samples/glass-sliding-door.wild) | [entrance-door-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/entrance-door-examples.md) |
| 实体墙 | [solid-wall.wild](samples/solid-wall.wild) | [envelope-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/envelope-detail-examples.md) |
| 设备平台 | [equipment-platform.wild](samples/equipment-platform.wild) | [balcony-equipment-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/balcony-equipment-examples.md) |
| 露台栏杆 | [terrace-railing.wild](samples/terrace-railing.wild) | [balcony-equipment-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/balcony-equipment-examples.md) |
| 开启扇 | [operable-sash.wild](samples/operable-sash.wild) | [glazing-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/glazing-detail-examples.md) |
| 固定玻璃 | [fixed-glazing.wild](samples/fixed-glazing.wild) | [glazing-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/glazing-detail-examples.md) |
| 装饰檐口 | [decorative-cornice.wild](samples/decorative-cornice.wild) | [roof-facade-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/roof-facade-detail-examples.md) |
| 侧门 | [side-door.wild](samples/side-door.wild) | [entrance-door-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/entrance-door-examples.md) |
| 小窗 | [small-window.wild](samples/small-window.wild) | [glazing-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/glazing-detail-examples.md) |
| 车库门 | [sectional-garage-door.wild](samples/sectional-garage-door.wild) | [entrance-door-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/entrance-door-examples.md) |
| 通风百叶 | [ventilation-louvre.wild](samples/ventilation-louvre.wild) | [ventilation-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/ventilation-detail-examples.md) |
| 空调机位 | [ac-position.wild](samples/ac-position.wild) | [balcony-equipment-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/balcony-equipment-examples.md) |
| 女儿墙 | [parapet.wild](samples/parapet.wild) | [roof-facade-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/roof-facade-detail-examples.md) |
| 屋檐下悬 | [eave-soffit.wild](samples/eave-soffit.wild) | [roof-facade-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/roof-facade-detail-examples.md) |
| 储藏间门 | [storage-door.wild](samples/storage-door.wild) | [entrance-door-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/entrance-door-examples.md) |
| 高窗 | [high-window.wild](samples/high-window.wild) | [glazing-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/glazing-detail-examples.md) |
| 庭院围墙接口 | [garden-wall-junction.wild](samples/garden-wall-junction.wild) | [envelope-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/envelope-detail-examples.md) |
| 老虎窗 | [gable-dormer.wild](samples/gable-dormer.wild) | [roof-facade-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/roof-facade-detail-examples.md) |
| 排风口 | [exhaust-outlet.wild](samples/exhaust-outlet.wild) | [ventilation-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/ventilation-detail-examples.md) |
| 雨棚构造 | [framed-awning.wild](samples/framed-awning.wild) | [roof-facade-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/roof-facade-detail-examples.md) |
| roof | [hip-roof.wild](samples/hip-roof.wild) | [roof-facade-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/roof-facade-detail-examples.md) |
| 罗马柱 | [roman-column.wild](samples/roman-column.wild) | [roof-facade-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/roof-facade-detail-examples.md) |
| 铁艺栏杆 | [ornamental-iron-railing.wild](samples/ornamental-iron-railing.wild) | [balcony-equipment-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/balcony-equipment-examples.md) |
| 景观矮墙 | [landscape-low-wall.wild](samples/landscape-low-wall.wild) | [envelope-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/envelope-detail-examples.md) |
| 落地窗组 | [floor-window-group.wild](samples/floor-window-group.wild) | [glazing-detail-examples.md](../../../wild-server/storage/knowledge_base/knowledge/components/glazing-detail-examples.md) |

## 来源与处置

| 参考 | 查看位置 | 图像证据 |
| --- | --- | --- |
| [CMHA 砌体基础详图](https://www.cmha.org/resource/tek-05-03a/) | 官方网页文字与基础节点资料 | 官方网页入口，未按产品图精确复刻 |
| [Allan Block 墙顶与端部](https://allanblock.com/installation/commercial-installation/finishing-retaining-walls) | 官方网页；不移植该产品的砌块尺寸 | 官方网页入口，未按产品图精确复刻 |
| [Andersen 门窗建筑资料](https://www.andersenwindows.com/for-professionals/architect/architectural-tools) | 官方技术资料入口；示例的尺寸和组合由项目另选 | 官方网页入口，未按产品图精确复刻 |
| [Andersen 凸窗组装图](https://www.andersenwindows.com/-/media/Project/AndersenCorporation/AndersenWindows/AndersenWindows/files/technical-docs/installation-guide/installationguide-0005132.pdf) | PDF 第2页，分件图 | [本地图](references/andersen-bay-page-2.png) |
| [Hörmann 分节车库门](https://www.hoermann.com/fileadmin/_country/kataloge/pdf/86_912-Sectional_Garage_Doors_-0518-EN-UK.pdf) | PDF 第89页，轨道类型图 | [本地图](references/hoermann-garage-page-89.png) |
| [Melton 檐口图纸](https://meltonclassics.com/products/cornices/fiberglass-cornices/designs/) | MC-1 详图PDF第1页，剖面和立面 | [本地图](references/melton-cornice-page-1.png) |
| [Melton 壁柱与门套](https://www.meltonclassics.com/files/melton-urethane-entry-systems.pdf) | PDF 第10页（印刷页28），壁柱立面与剖面 | [本地图](references/melton-entry-page-10.png) |
| [Melton Roman Ionic 柱式](https://meltonclassics.com/products/architectural-columns/fiberglass-composite-columns/designs/) | Roman Ionic 栏及693.gif柱式图 | [本地图](references/melton-roman-ionic.png) |
| [RHEINZINK 屋面节点](https://www.rheinzink.com/products/architectural-details/) | 官方建筑节点入口；覆盖形状由本次样例另选 | 官方网页入口，未按产品图精确复刻 |
| [RHEINZINK 老虎窗](https://www.rheinzink.com/products/architectural-details/dormer/) | 官方照片，前部围护、侧壁和主屋面接口 | [本地图](references/rheinzink-dormer.jpg) |
| [Canopia Aquila 雨棚](https://canopia.com/app/uploads/2022/03/600483_Palram-Canopia_Door-Awnings_Aquila_1x2_3x7_Assembly-Instructions.pdf) | PDF 第28页分件图、第32页装配图；PMMA材料见第37页 | [本地图](references/canopia-awning-page-32.png) |
| [TROX WG 百叶](https://www.troxuk.co.uk/external-weather-louvres/wg-3a5581e60ae1533b) | 官方正面与侧剖面图 | [本地图](references/trox-wg-section.png) |
| [Daikin 外机安装图](https://www.daikin.eu/content/dam/document-library/installation-manuals/ac/split/RXP-L%2CARXP-L%2CRXF-A_3PDA512025-2_Installation%20Manual_Danish.pdf) | PDF 第7页，墙支架、底座与外机连接图 | [本地图](references/daikin-bracket-page-7.png) |
| [Q-railing 栏杆 CAD](https://q-railing.com/pl-pl/uslugi/materialy-do-pobrania/rysunki-cad/) | 官方 CAD 资料入口，未宣称复刻具体CAD产品 | 官方网页入口，未按产品图精确复刻 |
| [King Metals 双端卷花](https://www.kingmetals.com/ECItemMainPage.aspx?ItemId=ITM-10273550) | 官方双端卷花产品图 | [本地图](references/king-scroll.webp) |

[source-claims.json](source-claims.json) 记录来源声明、参考层级、处置、目标文档、WILD字段位置、代码核验位置和自由变量。[catalog.json](catalog.json) 保存转换结果和每项安装说明。PDF页码按文件页序，从1开始。原始PDF、图片和记录留在本目录，不参与活动知识检索。

网络资料只提供分件、轮廓及接口参考；WILD JSON是按当前项目契约重新编写的实现。未采用的产品认证、经验尺寸、载荷和整栋布局没有进入活动规则。

## 当前近似与待检查部分

- 凸窗为当前原生箱形表达，没有精确复刻来源30°/45°侧窗。
- 开启扇使用 `window.interaction`；编译器当前生成左右两扇。
- 车库门保留分节外观，lift为整板抬升，未实现逐节沿弯轨运动。
- 老虎窗提供独立双坡样例；装入整栋时必须另外分块或处理主屋面接口。本批没有证明整栋安装效果。
- 百叶有真实固定倾斜叶片几何；排风口短管为实心圆筒外观，没有通风仿真或空心管道连通验证。
- 雨棚的透明外观使用glass材质，来源产品为PMMA，五金和曲率作了简化。罗马柱和铁艺卷花也保留了各自简化说明。

## 验证证据

- [core-validation.json](core-validation.json)：34/34通过。对当前TS源码作临时转译，实际执行 `parseBlueprint`、`compileBlueprintComponents`、`reconstructEntity`；网格和包围盒有限，编译错误与警告均为0。未做浏览器渲染或全前端类型检查。
- [backend-validation.json](backend-validation.json)：34/34通过真实 `implementation_errors`，包括字段、尺寸、引用、开口坐标和开口适配校验。
- [ingestion-validation.json](ingestion-validation.json)：34个活动JSON与已编译样例一致；每项存在带正确metadata的JSON分片；35项用实际 `search_knowledge_impl` 检索，都取得对应的完整JSON。
- [structure-validation.log](structure-validation.log)：活动清单42份，缺失0、未登记0，结构与5组过滤入口通过。
- [new-chunk-preview.json](new-chunk-preview.json)：新增6份文档产生90个分片，0错误，11条长原子代码块提示。保留完整构件、宿主和材质，没有拆断JSON或放宽全局限制。
- [rag-contract-tests.log](rag-contract-tests.log)：相关RAG和search工具回归22项通过。
- [after-lint.json](after-lint.json)：全库0错误、139条提示；原基线125条，本批增加14条长度提示。全库预览还存在旧README元数据示例泄漏提示，未扩大本次修改范围；新增文档预览没有错误。
- [skill-validation.log](skill-validation.log)：更新后的skill格式通过检查。

plan工具改为调用已有的 `include_base=False`，避免重复基础协议挤掉本次构件JSON；没有增加检索机制或提高上下文预算。移除本次多构件文档中会抢占检索的重复概述，并修正旧窗变体资料中百叶和开启扇的过时能力说明。

## 环境说明

普通终端子进程曾遇到Windows网络初始化故障，已通过可用的Node REPL子进程完成真实Python校验、测试、当前配置嵌入、索引同步和检索。索引使用当前真实embedding，不使用HashEmbedding，不清空集合。辅助进程仅关闭自身的后台自动同步，未修改项目.env。

内置浏览器返回 `Browser is not available: iab`，所以没有生成WILD外观截图；参考图纸页已实际渲染并查看，不能等同于WILD外观通过。

35项检索是在按当前文件新建的实际loader实例中验证的。长时间运行的旧后端若没有自动重载，需要重启一次以刷新新增知识来源白名单和进程内检索缓存；不需清空索引。本次没有重启用户服务或运行整栋建筑生成。

## 后续命名统一

本批条目已补充中英文同义词，并统一为中文正式标题。plan 分类、界面名称、architecture 提示词和 RAG 查询共用现有注册信息及知识小节元数据。例如“落地窗 / floor-to-ceiling window / floorWindow”均使用 `floor_window`，显示“落地窗”，按 `window` 知识族检索；“实墙 / 实体墙 / Solid Wall”均使用 `solid_wall`。原图纸的设计值和实例引用保留。

[命名回归](naming-tests.log) 共135项通过；[真实别名检索](naming-alias-retrieval.json) 的12个输入均取得对应完整JSON。详细约定与改动见 [执行记录第11节](../../../docs/10月10日优化/执行记录.md#11-plan-构件名称与-rag-检索统一)。
