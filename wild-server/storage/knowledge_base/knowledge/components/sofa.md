---
doc_type: component
knowledge_role: capability
doc_scope: generation
knowledge_layer: wild_schema
entity_type: component
entity_name: sofa
topic: composition
status: supported
authority: engine
primary_terms:
  - 沙发
  - 三人沙发
  - 双人沙发
  - 组合沙发
  - sofa
synonyms: []
applies_to:
  - 沙发
  - 三人沙发
  - 双人沙发
  - 组合沙发
---

# 沙发表达（furniture 原生 subtype + primitive 组合）

适用条件：**用户或已批准方案显式点名**沙发（客厅沙发、三人位、组合沙发等）时才按本文档表达。
"装修""温馨""室内"这类氛围词不触发本文档。家具属于 `geometry.elements`，不是 `geometry.components`
组合构件，不挂 `parentWall`，直接给世界坐标放置。

引擎事实：`furniture` 的 `subtype` 枚举含 `sofa`（原生实现，`wild-core` 的 `furniture.ts::buildSofa`），
直接写 `subtype: "sofa"` 即按沙发几何生成——**不再降级为椅形**。服务端归一器
（`app/utils/blueprint_parser.py` 的 `_FURNITURE_SUBTYPE_ALIASES`）另把常见叫法
`couch` 收敛为 `sofa`。共通坐标约定（以引擎代码为准）：**`furniture` 的 `position` 是底部锚点**
（局部网格 y 从 0 到 height 整体平移到 position，落地摆放 y = 楼板标高）；**`primitive` 的
`position` 是几何中心**（盒体/圆柱顶点以原点为中心，落地盒 y = 底标高 + height/2）。

## 快捷方式：furniture 原生 subtype

<!-- rag-meta
entity_type: furniture
entity_name: sofa_furniture
topic: composition
primary_terms:
  - 沙发
  - 三人沙发
synonyms: []
-->

把沙发写成一个 `furniture` 元素、`subtype: "sofa"`，引擎按原生沙发几何生成：
底座 + 整宽靠背 + 左右两个扶手 + 坐垫，共 7 个盒体。坐垫**恒为 3 块**（引擎硬编码，
不随宽度变化，每块宽 = 内宽/3 × 0.94）。各零件尺寸由固定比例推出，改 `dimensions` 整体联动。

以下是 `geometry.elements` 数组中的一个片段，不是完整 `.wild` 文件：

```json
{
  "type": "furniture",
  "id": "sofa_living_1",
  "subtype": "sofa",
  "position": [5.0, 0.0, 2.0],
  "dimensions": { "width": 2.52, "depth": 0.85, "height": 0.72 },
  "material": "fabric_grey"
}
```

**语义**：有扶手、有坐垫分块，靠背朝 -z（`position` 为底部锚点，`y` 给楼板标高即落地）。
坐垫高度按 `height` 比例给出，不再固定为 0.45 × height。需要 L 型转角、异形软包或
独立控制每块坐垫时，改用下面的 primitive 组合。

## 精细方式：primitive 盒体组合

<!-- rag-meta
entity_type: furniture
entity_name: sofa_primitive
topic: composition
primary_terms:
  - 组合沙发
  - 布艺沙发
synonyms: []
-->

需要 L 型转角、贵妃位或对每块坐垫单独控制尺寸/材质时，用多个 `primitive` 盒体拼装：
底座、靠背、双扶手为固定四件，坐垫按座位数再拆分块。下例对应一张 2.52 × 0.85 × 0.72（总高）
的三人沙发，座高约 0.42，靠背朝 -z。

以下是 `geometry.elements` 数组中的一组片段，不是完整 `.wild` 文件：

```json
[
  { "type": "primitive", "shape": "box", "id": "sofa_1_base",  "position": [5.0, 0.125, 2.0],    "dimensions": [2.52, 0.25, 0.85],  "material": "fabric_grey" },
  { "type": "primitive", "shape": "box", "id": "sofa_1_back",  "position": [5.0, 0.485, 1.7],    "dimensions": [2.52, 0.47, 0.25],  "material": "fabric_grey" },
  { "type": "primitive", "shape": "box", "id": "sofa_1_arm_l", "position": [3.865, 0.275, 2.0],  "dimensions": [0.25, 0.55, 0.85],  "material": "fabric_grey" },
  { "type": "primitive", "shape": "box", "id": "sofa_1_arm_r", "position": [6.135, 0.275, 2.0],  "dimensions": [0.25, 0.55, 0.85],  "material": "fabric_grey" }
]
```

- 各盒尺寸、座高、扶手宽度、坐垫块数都是**自由变量**，由本次方案决定；示例数值仅解释
  字段含义（来源：用户提供的沙发 CAD 图，总宽 2520 / 深 850 / 总高 720 / 坐高 420）。
- `dimensions` 是 WILD 1.1 的 `[width, height, depth]` 顺序；靠背朝向由靠背盒相对底座的
  z 偏移决定，需要朝别处时调整各盒 z 偏移的符号，不要整体只改一处。
- 每个盒体是独立元素，材质可分别指定（如坐垫换色）；组合沙发（L 型）按同规则增加一组
  转角盒体，不引入新字段。

## 能力边界汇总

- ✅ 快捷表达：`furniture` + `subtype: "sofa"`（原生沙发：底座 + 靠背 + 双扶手 + 坐垫分块）。
- ✅ 精细表达：`primitive` 盒体组合（L 型转角、贵妃位、逐块坐垫均可拼装）。
- ✅ 别名：`couch` 由服务端归一器收敛为 `sofa`。
- ❌ 软包圆角、绗缝、织物褶皱：无字段，引擎只有方盒几何；抱枕可用小盒体 `primitive` 近似。
- ❌ 坐姿交互 / 可坐语义：沙发是静态几何，与 `furniture` 其他 subtype 一致。
- 相关限制详见《引擎能力边界》的 furniture 行与"家具抽屉/柜门"条目。
