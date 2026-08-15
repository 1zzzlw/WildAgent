# WildAgent 知识分类与路由

## 路径职责

| 目标 | `doc_type` | 用途 |
|---|---|---|
| `BLUEPRINT-SPEC-FULL.md` | `blueprint_spec` | 完整 WILD 字段、坐标、引用和约束 |
| `building_types/catalog/` | `building_type` | 模糊建筑名称的轻量默认入口 |
| `building_types/residential/` | `building_type` | 住宅、别墅、公寓、宿舍、酒店、院落 |
| `building_types/public/` | `building_type` | 教育、办公、文化、商业、体育、医疗、交通 |
| `building_types/industrial/` | `building_type` | 厂房、仓储、车间、工业上楼 |
| `building_types/agricultural/` | `building_type` | 温室、养殖、粮仓、农机建筑 |
| `components/` | `component` | 墙、门、窗、屋顶、柱梁、楼梯、家具、材料等构件族 |
| `recipes/` | `recipe` | 跨构件组装顺序、参数关系、矩阵和降级策略 |
| `patterns/` | `pattern` | 用户确认案例、项目偏好和不可普遍化的经验 |
| 各级 `README.md` | `index` | 人类导航，不作为普通生成知识 |

`BLUEPRINT-SPEC-MINIMAL.md` 是始终注入 Prompt 的铁律，不作为普通知识文档更新；修改它需要用户明确授权。

## 轻量目录与详细文档

`building_types/catalog/` 只保留：

- 默认语义；
- 常见变体名称；
- 最小构件集合；
- 最少可行版本；
- 指向详细知识的关键词。

详细尺寸、完整构件表、施工逻辑、多种复杂变体进入对应的 `building_types/<use>/` 文件。轻量目录不得复制详细文件的整段内容。

catalog 的“最小构件集合”只是检索入口与失败回退，不得被当作普通/精密模式的默认生成配方。详细建筑实体必须另有 `topic: composition` 的默认完整构成合同，保留身份特征、空间系统、主体骨架、外围护、开口/交通/附属组件、重复模数、依附搭接和降级映射。若详细文档尚不存在，catalog 必须标出缺口，不能用最小摘要冒充完整知识。

## 拆分与合并

拆分源文档，当它包含不同检索意图，例如：

- “中式门”进入 `components/doors.md`；
- “漏窗”进入 `components/windows.md`；
- “四合院默认配方”进入建筑类型或 catalog；
- “门窗与屋顶搭配矩阵”进入 `recipes/`。

合并到现有文件，当新内容只增加同一实体的变体、参数、约束或已验证示例。

新建文件，当主题长期稳定、能独立召回，并且加入现有文件会造成多个无关实体竞争同一标题层级。

原始长文中的共用体系按职责路由，但不得从建筑实体中消失：

- 建筑实体保留“该体系在本建筑中的角色、优先级、触发条件和省略后果”；
- `components/` 保留体系本身的定义与参数；
- `recipes/` 保留跨构件的组装顺序、关系和降级；
- 路由结果写入来源覆盖表，禁止只写“详见其他文档”而不保留建筑上下文。

## 事实重复与优先级

- 精确重复：保留一份，并保留更完整的来源。
- 同实体的短摘要与详细规则：catalog 留摘要，详细文件留规范内容。
- 参数冲突：按事实优先级判断；无法判断时保留冲突记录，不并入 supported 规则。
- WILD 版本不同：分块并写明 `wild_version`，禁止合并。
- `supported` 与 `proposed`：必须分块，正式生成只使用 supported。

## 关键词

每个文档和实体块都补充：

- 中文正式名与常见别名；
- 英文名；
- 当前存在的 WILD `type` 和字段名；
- 用户可能使用的风格名、建筑名和功能名。

关键词只帮助召回，不能证明字段受支持。
