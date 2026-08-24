---
knowledge_layer: architecture
entity_type: facade
entity_name: glass_curtain_wall_assembly
topic: assembly
status: experimental
authority: domain_reference
source: recipes/glass-curtain-wall-assembly.md
primary_terms:
  - 玻璃幕墙组装
  - curtain wall assembly
  - window grid
  - primitive mullion
  - facade grid
synonyms: []
---

# 玻璃幕墙骨架—玻璃组装配方

> 本配方把幕墙业务语义收敛到两条可执行路径。方案 A 适合默认生成；方案 B 只在需要显式框深、点支或复杂表皮时使用。底层类型受支持，但“真实幕墙系统”仍是实验性视觉近似。

## 玻璃幕墙组装前置条件

<!-- rag-meta
entity_type: facade
entity_name: curtain_wall_preconditions
topic: constraints
status: supported
authority: engine
primary_terms:
  - parentWall
  - facade extent
  - floor level
  - material reference
  - 前置条件
synonyms: []
-->

1. 先完成 `column/beam/floor` 主体骨架和各层标高。
2. 明确幕墙立面范围、法线方向、层间不透明区和入口洞口。
3. 方案 A 必须先创建可引用的 `wall`；所有窗的沿墙距离、底标高、宽和高都必须落在宿主范围内。
4. 方案 B 必须先定义网格原点、格宽、层高、骨架深度、玻璃厚度和嵌缝。
5. 骨架、玻璃和层间背衬使用不同材质引用；引用必须存在于蓝图或全局材质库。

## 方案 A：墙体宿主加网格窗

<!-- rag-meta
entity_type: facade
entity_name: curtain_wall_window_grid_recipe
topic: assembly
status: experimental
authority: engine
primary_terms:
  - 方案A
  - wall window
  - verticalMullions
  - horizontalMullions
  - parentWall
synonyms: []
-->

方案 A 用 `wall + window` 表达整片或分层幕墙。窗编译器生成框、竖梃、横挺和玻璃，是默认的低成本路径。 它适合常规正交立面和标准层批量生成，能把宿主、开洞、框架与玻璃关系收敛到一个组件。入口层、转角和异形区仍应拆开处理，不能用一片超大窗覆盖全部立面。

### 方案 A 组装步骤

1. 按楼层或完整立面创建 `wall` 宿主；层间背衬可拆成独立墙段。
2. 在宿主上放置一个整片窗，或按“楼层 × 开间”显式放置多个窗。
3. 用 `verticalMullions` 与 `horizontalMullions` 建立次级网格；用 `frameWidth`、`frameDepth` 与 `glassDepth` 控制层次。
4. 将门和少量开启扇作为独立 `door/window` 放入预留区，不与固定玻璃重叠。
5. 校验窗边界、相邻窗间距、层间线、材质引用和宿主存在性。

### 方案 A 最小有效示例

以下是完整的小型 `.wild` 文件，用一片固定网格窗表达单层幕墙单元。

```json
{
  "meta": {"version":"1.1","type":"building","name":"玻璃幕墙单元"},
  "geometry": {
    "elements": [{"type":"wall","id":"cw_host","from":[0,0,0],"to":[3,3,0],"thickness":0.16}],
    "components": [{"type":"window","id":"cw_window","parentWall":"cw_host","from":[0.1,0.1,0],"width":2.8,"height":2.8,"frameWidth":0.06,"frameDepth":0.12,"glassDepth":0.012,"verticalMullions":1,"horizontalMullions":1,"interaction":{"mode":"swing","hingeSide":"left","openAngle":0}}]
  },
  "behaviors": {}
}
```

该最小示例使用默认材质以保持原子性；正式幕墙应按“骨架金属、玻璃、层间背衬”三种角色补充材质，并确保每个引用存在。

## 幕墙确定性生成参数（方案 A）

<!-- rag-meta
entity_type: facade
entity_name: curtain_wall_deterministic_parameters
topic: parameters
status: supported
authority: engine
primary_terms:
  - 确定性参数
  - pane module
  - 窗格模数
  - 竖梃缝
  - 窗台
  - mullion gap
  - sill
synonyms: []
-->

下面的 JSON 是方案 A 的确定性生成参数，由生成器在运行时直接解析（`app/agent/facade_recipe.py`）。修改这些数值会立即改变幕墙的窗格模数、竖梃缝、窗台高与层间缝，无需改动代码：

```json
{
  "pane_module": 1.4,
  "mullion_gap": 0.2,
  "min_window_width": 0.75,
  "sill_height": 0.5,
  "sill_ratio": 0.13,
  "top_clearance": 0.25
}
```

- `pane_module`：竖梃/横梃分格模数（米），窗格按此尺寸密铺。
- `mullion_gap`：相邻窗带之间的竖梃缝宽（米），窗宽 = 开间宽 − 该值。
- `min_window_width`：窗宽下限（米）。
- `sill_height`：窗台高上限（米）。
- `sill_ratio`：窗台高占层高的比例上限，与 `sill_height` 取较小值。
- `top_clearance`：窗顶到上层楼板线的余量（米）。

## 方案 B：显式骨架加玻璃面板

<!-- rag-meta
entity_type: facade
entity_name: curtain_wall_explicit_grid_recipe
topic: assembly
status: experimental
authority: engine
primary_terms:
  - 方案B
  - primitive box
  - 显式竖梃
  - 显式横挺
  - rotation
  - glass panel
synonyms: []
-->

方案 B 使用两组独立 `primitive`：一组表示竖梃/横挺，另一组表示玻璃。它能表达明显框深、隐框、半隐框、点支和斜向分段，但元素数量与 draw call 更高。 只有当方案 A 无法表达所需层次时才启用，并优先局部使用。生成器必须用统一网格公式计算所有骨架和面板，禁止逐块手调坐标形成不可维护的补丁。

### 方案 B 参数公式

设立面宽 `W`、高 `H`，列数 `C`、行数 `R`，嵌缝 `g`：

- 单格宽 `cellW = W / C`；单格高 `cellH = H / R`。
- 竖梃数量 `C + 1`；横挺数量 `R + 1`。
- 玻璃数量 `C × R`。
- 每片玻璃宽高为 `[cellW - 2g, cellH - 2g]`，中心位于对应单元格中心。
- 玻璃厚度应明显小于骨架深度；法线偏移决定明框、隐框或半隐框观感。

### 方案 B 组装步骤

1. 先生成全部竖梃和横挺，建立网格边界。
2. 再把玻璃面板放入单元格中心，四边保留一致嵌缝。
3. 斜立面通过 `primitive.rotation` 旋转整组元素；复杂曲面按共同法线分段。
4. 高重复骨架可用 `templates + instances` 复用 `primitive` 模板，并检查每个实例引用。
5. 入口、开启扇和层间背衬仍单独建模，不能让玻璃覆盖门洞或楼板线。

## 骨架—玻璃七条关系

<!-- rag-meta
entity_type: facade
entity_name: curtain_wall_grid_relations
topic: assembly
status: experimental
authority: domain_reference
primary_terms:
  - grid first
  - 共面
  - 层间分隔
  - 材质分离
  - 荷载路径
  - reveal
synonyms: []
-->

1. 网格优先：先确定骨架和分格，再求玻璃尺寸。
2. 玻璃内嵌：玻璃中心对齐单元格，四周留嵌缝，不越过骨架外轮廓。
3. 厚度分层：玻璃明显薄于骨架；避免两层完全共面引发闪烁。
4. 法线一致：同一立面单元的骨架与玻璃使用同一朝向；明框玻璃后退，隐框玻璃前移。
5. 层间分隔：楼板线/窗台线位置设置横向分隔和不透明层间区。
6. 材质分离：框、玻璃、背衬分别引用不同材料。
7. 宿主与承托：幕墙几何贴合 `floor/beam` 边界，但不把玻璃写成承重构件。

## 幕墙变体参数化选择

<!-- rag-meta
entity_type: facade
entity_name: curtain_wall_variant_selection
topic: parameters
status: experimental
authority: domain_reference
primary_terms:
  - 明框参数
  - 隐框参数
  - 单元式
  - 双层
  - 点支
  - 曲面
synonyms: []
-->

| 变体 | 首选路径 | 参数变化 | 性能代价 |
|---|---|---|---|
| 明框 | A 或 B | 框较深，玻璃后退 | 低到中 |
| 隐框 | B | 玻璃前移覆盖框 | 中 |
| 半隐框 | B | 仅一个方向框前置 | 中 |
| 单元式 | A | 固定模数按楼层/开间重复 | 低 |
| 点支式 | B | 减少连续框，增加少量点件 | 中到高 |
| 双层 | B | 两层玻璃和空腔 | 高 |
| 曲面/斜面 | A 或旋转 B | 按弧段/法线分段 | 中到高 |

## 玻璃幕墙验证清单

<!-- rag-meta
entity_type: facade
entity_name: curtain_wall_validation
topic: constraints
status: supported
authority: engine
primary_terms:
  - 幕墙验证
  - opening fit
  - parentWall
  - collision
  - material reference
  - z fighting
synonyms: []
-->

- 所有 ID 唯一；`parentWall` 存在。
- 每个窗的沿墙距离、底标高、宽和高均落在宿主范围内。
- 同墙门窗不重叠，入口预留不被固定玻璃覆盖。
- 玻璃与框存在可见深度差，避免完全共面闪烁。
- 楼层横线、中梃和层间背衬与实际楼层标高一致。
- 材质引用存在；玻璃材质与金属框材质分离。
- 方案 B 的实例引用、旋转、缩放和位置均可展开。
- 未出现 `curtain_wall`、`mullion`、`transom`、`window.parentOpening` 或 `window.parentRoof`。

## 玻璃幕墙失败与回退

<!-- rag-meta
entity_type: facade
entity_name: curtain_wall_recipe_fallback
topic: fallback
status: experimental
authority: engine
primary_terms:
  - 幕墙回退
  - 减少面板
  - 方案B转A
  - 保留立面模数
synonyms: []
-->

- 方案 B 元素过多或碰撞频繁：回退到方案 A 的 `wall + window`，保留分格数和材料角色。
- 曲面分段不稳定：回退为少量折线/弧段，不退成完全无模数的透明平面。
- 门窗超出宿主：先缩小或重排窗带，再减少列数；不要扩大墙体去掩盖体量错误。
- 透明排序或性能异常：减少重叠玻璃层和双层幕墙范围，保留主入口与主要立面的特征单元。
