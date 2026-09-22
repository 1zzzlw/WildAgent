---
doc_type: recipe
knowledge_role: relation
doc_scope: generation
knowledge_layer: constraint
entity_type: assembly
entity_name: supported_assembly_relations
topic: assembly
wild_version: "1.1"
status: supported
authority: engine
primary_terms:
  - 构件组装关系
  - assembly relation
  - resolver
  - 引用顺序
  - 墙体与开口
  - 墙挂组件
  - 墙角闭合
  - 柱与梁吸附
  - 楼板与屋顶补全
synonyms: []
---

# 构件组装关系约束

> 基于 WILD v1.1 引擎实现的实际组装能力  
> 来源：`wild-core/resolver.ts`、`wild-compiler/index.ts`、组件编译器

本文档只记录**引擎当前能够执行**的组装关系。未实现的设计不变量应移至 backlog。

---

## 1. 引用顺序约束

### 规则

- `geometry.components` 中的组件可以引用 `geometry.elements` 中的任何元素
- **不要求父元素在数组中先出现**（编译器会全局查找）
- 引用目标必须存在、id 必须唯一、类型必须匹配
- **禁止组件之间相互引用**（不能把另一个组件的产物当父元素）

### 示例

```jsonc
{
  "geometry": {
    "elements": [
      {"type": "wall", "id": "wall_1", ...}
    ],
    "components": [
      {
        "type": "window",
        "id": "win_1",
        "parentWall": "wall_1"  // ✅ 引用 elements 中的 wall
      }
    ]
  }
}
```

---

## 2. 墙体与开口

### 规则

- `opening.parentWall` **必须**引用已存在的 `wall.id`
- 直墙：`opening.from[0]` = 沿墙距离，`from[1]` = 底部世界 Y
- 弧墙：`from[0]` = 弧长，`from[1]` = 相对墙底偏移
- 引擎自动计算洞口位置并执行布尔减法

### 约束检查

```python
def validate_opening(opening, walls):
    parent = find_wall_by_id(opening["parentWall"], walls)
    if not parent:
        raise ReferenceError(f"parentWall '{opening['parentWall']}' not found")
    
    wall_length = calculate_wall_length(parent)
    opening_right = opening["from"][0] + opening["width"]
    
    if opening_right > wall_length:
        raise ValueError(f"Opening exceeds wall length: {opening_right} > {wall_length}")
```

---

## 3. 门窗与墙挂组件

### 3.1 形成开口的组件

**适用类型**：`door`、`window`、`bay_window`

**规则**：

- **必须**通过 `parentWall` 引用 `wall`
- 自动在父墙上生成开口
- **仅支持**直线墙或单段圆弧墙
- `from` 解释为 `[沿墙距离, 世界Y, 法向偏移]`

**约束**：

- 组件宽度必须在墙水平范围内
- 带 `height` 的组件必须在墙垂直范围内
- `frameDepth` 不能超过墙 `thickness`

### 3.2 不形成开口的墙挂组件

**适用类型**：`canopy`、`balcony`

**规则**：

- **必须**引用 `parentWall`（确定位置和朝向）
- 不在墙上开洞，悬挑在外
- 梁柱连接不自动推导为结构节点

### 3.3 约束检查示例

```python
def validate_wall_attached(component, walls):
    parent = find_wall_by_id(component["parentWall"], walls)
    if not parent:
        raise ReferenceError(f"parentWall not found")
    
    # 检查宽度
    wall_length = calculate_wall_length(parent)
    if component["from"][0] + component["width"] > wall_length:
        raise ValueError("Component exceeds wall horizontal range")
    
    # 检查深度（如果是门窗）
    if component["type"] in ["door", "window"]:
        if component.get("frameDepth", 0) > parent["thickness"]:
            raise ValueError(f"frameDepth {component['frameDepth']} exceeds wall thickness {parent['thickness']}")
```

---

## 4. 墙角闭合

### 规则

- 两面墙端点 XZ 距离 < 0.01m 时，自动闭合
- 端点 XZ 取平均，Y 各自保留
- 直角墙角：每面墙延伸对方厚度的一半

### 生成时必须遵守

- 两面墙在转角处相接时，**必须写完全相同的端点坐标，不能使用近似值**。
  引擎的闭合容差只有 0.01m，靠"差不多"的坐标会让墙在转角处裂开或错位。
- 该规则可被 `validate_wall_junctions` 判定，属于硬约束而非建议。

### 限制

- **仅处理端点相交**
- 不自动解决 T 形中接
- 不自动解决任意交叉墙

### 实现依据

`resolveWallJoints` 函数

---

## 5. 柱与梁吸附

### 规则

- 梁端在 XZ 平面接近柱顶
- 距离 < `column.bottomRadius + 0.05`
- 自动对齐梁端 XYZ 到柱顶

### 限制

- 仅处理 `beam` 类型
- 不支持 `truss`（当前未实现）

### 实现依据

`resolveBeamSupports` 函数

---

## 6. 楼板与屋顶自动补全

### 6.1 楼板补全

**触发条件**：

- 蓝图完全没有 `floor`
- 至少有三面墙

**行为**：

- 按墙体 XZ 包围盒生成矩形楼板
- 厚度 0.2m
- **如果已有任意楼板，不再补全**

### 6.2 屋顶边界扩展

**触发条件**：

- 至少有三面墙

**行为**：

- 按有效高墙扩大 `roof.span`、`roof.depth`
- `roof.position` 缺失时，居中放到最高墙顶
- 显式位置不会被覆盖

### 限制

- 其他标高关系需显式给出
- 引擎不完成结构设计推导

---

## 7. 表面挂接组件

### 7.1 栏杆 (railing)

- 通过世界坐标 `path` 生成立柱与横杆
- 提供 `parentFloor` 时，使用楼板局部坐标

### 7.2 坡道 (ramp)

- 通过 `from`、`to` 生成斜面
- 可选生成栏杆
- `parentFloor` 是可选参考，非必填

### 7.3 檐口 (cornice)

- 通过 `path` + `profile` 扫掠
- `parentRoof` 挂接到屋面坐标（当前支持有限）

### 7.4 烟囱 (chimney)

- 可通过 `parentRoof` 确定基点
- **当前不执行布尔穿透**
- 不自动生成防水节点

### 7.5 灯光 (light)

- 使用世界坐标 `position`
- **不要求任何父元素**

---

## 8. 模板与排布

### 8.1 模板实例 (instances)

- 引用 `geometry.templates`
- 支持 `position`、`rotation`、`scale` 变换
- 支持材质覆盖 (`materialOverride`)

### 8.2 表面排布 (placements)

- 引用模板，按网格批量生成
- **当前仅支持** `gable` 屋顶的 `left`/`right` 面
- 墙面、楼板、其他屋顶类型的排布**尚未实现**

---

## 约束检查清单

生成 WILD 前，必须检查：

- [ ] 所有 `parentWall` 引用的 wall 是否存在？
- [ ] 所有 `parentFloor` 引用的 floor 是否存在？
- [ ] 所有 `parentRoof` 引用的 roof 是否存在？
- [ ] 门窗是否超出父墙水平/垂直范围？
- [ ] 门窗 `frameDepth` 是否超过墙 `thickness`？
- [ ] 所有 id 是否唯一？
- [ ] 组件是否试图引用另一个组件的产物？

违反任何约束都会导致编译失败或渲染错误。

---

## 实现来源

本文档基于以下代码：

- `wild-core/src/primitive/resolver.ts`
- `wild-core/wild-core/src/compiler/index.ts`
- `wild-core/src/primitive/componentRegistry.ts`
- 各组件的 `builder.ts` 和 `compiler.ts`

约束规则与代码实现保持同步。
