---
knowledge_layer: architecture
entity_type: facade
entity_name: glass_curtain_wall_family
topic: definition
status: experimental
authority: domain_reference
source: components/glass-curtain-walls.md
primary_terms:
  - 玻璃幕墙
  - 竖梃
  - 横挺
synonyms:
  - glass curtain wall
  - curtain wall
  - glass facade
---

# 玻璃幕墙构件体系与当前引擎映射

> 来源：用户提供的《玻璃幕墙组合配方与规则》。本文件保留幕墙的定义、角色、适用场景和变体；跨构件的生成顺序与参数公式进入 `recipes/glass-curtain-wall-assembly.md`。玻璃幕墙是实验性组合体系，不是新的 WILD 原生类型。

## 玻璃幕墙定义与系统角色

<!-- rag-meta
entity_type: facade
entity_name: glass_curtain_wall_definition
topic: definition
status: experimental
authority: domain_reference
primary_terms:
  - 玻璃幕墙
  - 非承重外围护
  - 竖梃
  - 横挺
  - 玻璃面板
synonyms:
  - curtain wall
-->

玻璃幕墙是位于主体结构外侧的非承重外围护体系。其视觉组成至少包含竖向骨架、横向骨架、透明玻璃和层间背衬；骨架与面板把自重和环境作用传给主体，但 WILD 只表达几何与材质，不证明真实荷载路径、锚固、气密、水密、热工或防火性能。

- 主体结构：`column`、`beam`、`floor`，负责建筑骨架。
- 外围护宿主：`wall`，提供立面边界、层间背衬以及 `window.parentWall` 引用目标。
- 可见骨架：优先用 `window.verticalMullions` / `horizontalMullions`；高细节时用 `primitive` 的 `box`。
- 玻璃面板：优先由 `window` 生成；高细节时用薄 `primitive.box`。
- 幕墙门和可开启扇：继续使用 `door` / `window`，不能发明新的幕墙门窗类型。

## 玻璃幕墙当前引擎能力边界

<!-- rag-meta
entity_type: facade
entity_name: glass_curtain_wall_engine_boundary
topic: constraints
status: supported
authority: engine
primary_terms:
  - 无 curtain_wall
  - window mullions
  - primitive rotation
  - templates instances
  - parentWall
synonyms: []
-->

当前注册表没有 `curtain_wall`、`mullion` 或 `transom` 类型；这些词只能作为业务语义和实体名称，最终必须编译成现有元素/组件。

| 业务角色 | 当前 WILD 表达 | 能力状态 | 边界 |
|---|---|---|---|
| 整片立面宿主 | `wall` | supported | 墙高由 `from[1]` 与 `to[1]` 表达，没有独立 `wall.height` |
| 网格窗幕墙 | `window` + 竖横梃数量 | supported | 必须引用存在且尺寸可容纳的 `parentWall` |
| 显式竖梃/横挺 | `primitive.box` | supported | `rotation` 当前可用；复杂曲面仍需分段 |
| 玻璃面板 | `window` 或薄 `primitive.box` | supported | 仅视觉材质，不承担结构或热工计算 |
| 标准化重复 | `templates + instances` | supported | 模板值是基础 `GeometryElement`；不能直接把 `window` 组件放进模板字典 |
| 可开启行为 | `interaction` | supported | Core/Schema 中可选；当前 AI 组件生成合同仍要求门窗显式给出 |

来源中的三处旧结论已按源码纠正：`primitive.box.rotation` 已支持；`window.frameWidth` 已支持；`interaction` 不是 Core Schema 的必填字段。生成链为了稳定仍可继续显式输出 `interaction`。

## 玻璃幕墙材料角色

<!-- rag-meta
entity_type: material
entity_name: glass_curtain_wall_material_roles
topic: parameters
status: experimental
authority: domain_reference
primary_terms:
  - 幕墙玻璃
  - 金属框
  - materialClass glass
  - transmission
  - roughness
  - spandrel
synonyms: []
-->

幕墙至少使用三种分离的材料角色，避免骨架、玻璃和层间板共享同一材质后失去层次。

| 材料角色 | 建议字段方向 | 视觉目的 |
|---|---|---|
| 骨架金属 | 高 `metallic`、中低 `roughness` | 保持竖梃/横挺清晰 |
| 玻璃 | `materialClass: glass`、高 `transmission`、低 `roughness`、合理 `ior` | 表达透光与反射 |
| 层间背衬 | 不透明、中等粗糙度 | 区分通透区和楼板/层间区 |

材料名是引用 ID，不是能力类型；可使用全局材质库引用或蓝图内材质，但引用必须存在。玻璃透明只改变渲染观感，不会自动生成双层中空、Low-E、遮阳、结露或天气响应。

## 玻璃幕墙适用场景

<!-- rag-meta
entity_type: facade
entity_name: glass_curtain_wall_applicability
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 办公塔楼
  - 商业综合体
  - 航站楼
  - 高铁站
  - 酒店
  - 中庭
synonyms: []
-->

- `characteristic`：商务写字楼、超高层办公、玻璃幕墙商业综合体。
- `characteristic / conditional`：航站楼、高铁站、汽车或港口客运站的大厅立面。
- `conditional`：酒店、中庭、博物馆入口和观景面；只有来源或用户要求通透界面时使用。
- `optional`：普通低层住宅、低造价建筑；默认优先实体墙加常规窗。
- 不适合作为承重核心筒、地下围护、屋面、楼板或基础的替代物。

## 玻璃幕墙变体与可用映射

<!-- rag-meta
entity_type: facade
entity_name: glass_curtain_wall_variants
topic: composition
status: experimental
authority: domain_reference
primary_terms:
  - 明框
  - 隐框
  - 半隐框
  - 单元式
  - 点支式
  - 双层幕墙
  - 曲面幕墙
synonyms: []
-->

下列变体共享“骨架、玻璃、层间背衬分离”的基本合同；差异只体现在框的可见度、面板层数、连接件显式程度和曲面分段方式。选择变体时先满足建筑身份，再控制元素数量与透明叠层。默认只选择一种主变体；局部入口或转角可以使用第二种，但必须保持统一的楼层线和材料角色。

### 明框玻璃幕墙

骨架在玻璃外侧可见，适合需要清晰竖横向节奏的办公、交通大厅和工业化立面。优先使用 `window` 网格；需要明显框深时使用显式 `primitive.box` 骨架，并让玻璃沿立面法线略微后退。回退时可减少次级分格，但必须保留主要竖梃和楼层横线。

### 隐框与半隐框玻璃幕墙

隐框让玻璃前表面覆盖骨架，适合连续、平整的现代塔楼表皮；半隐框只保留一个方向的显式框，用于强调竖向或横向节奏。两者使用显式骨架方案更稳定，但只是几何层次近似，不表达结构胶与副框节点。若透明排序异常，先退回半隐框而不是叠加更多玻璃，并保留主要立面模数。

### 单元式玻璃幕墙

单元式幕墙以一层高或固定模数的窗单元重复，适合标准层连续复用。`window` 组件需要显式枚举或由生成代码批量展开；若使用 `templates + instances`，模板应保存展开后的基础元素，而不是直接保存组件。模数变化、入口层和避难层应拆成独立单元，不能强行套用标准层。

### 点支式与全玻璃幕墙

点支式或全玻璃幕墙适合入口大堂和中庭等需要弱化连续框的局部区域。使用薄玻璃 `primitive.box` 加少量 `primitive.sphere` 或小盒体表示点式连接；连接点随玻璃角部重复。驳接爪、玻璃肋与连接计算不属于当前能力，大面积使用时必须控制点件数量。

### 双层玻璃幕墙

双层幕墙使用两层分离玻璃几何与中间空腔表达，只有用户或建筑类型明确要求时才启用。两层必须保持稳定间距，并避免与楼板和入口互穿。自然通风、烟囱效应、遮阳控制和热工性能均不自动成立；没有明确需求时不要默认使用，避免无谓增加透明面和 draw call。

### 曲面玻璃幕墙

曲面幕墙适合入口、中庭或少量强调体量，不应默认覆盖整座建筑。单段弧形立面可尝试 `wall.curve` 配合窗组件；复杂弧面使用带 `rotation` 的 `primitive` 分段逼近。必须检查各段法线、拼缝和玻璃相交，不能把曲面能力写成连续 NURBS 或球壳支持。

## 玻璃幕墙禁止项与降级

<!-- rag-meta
entity_type: facade
entity_name: glass_curtain_wall_fallbacks
topic: fallback
status: supported
authority: engine
primary_terms:
  - curtain_wall 禁止
  - mullion 禁止
  - parentRoof 禁止
  - 幕墙降级
synonyms: []
-->

- 禁止输出 `type: curtain_wall`、`type: mullion` 或 `type: transom`。
- 禁止使用 `window.parentOpening`；当前组合窗直接引用 `parentWall`。
- 禁止把 `wall.height` 当作规范字段；墙高来自端点 Y 范围。
- 禁止把屋顶天窗写成 `window.parentRoof`；透明屋盖只能用 `roof` 材质或独立 `primitive` 近似。
- 快速回退至少保留“主体骨架 + 一道幕墙宿主 + 一片分格玻璃 + 入口”，不能退化成没有立面模数的透明方盒。
