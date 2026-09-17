---
doc_type: blueprint_spec
knowledge_role: protocol
doc_scope: generation
knowledge_layer: wild_schema
entity_type: schema
entity_name: scene_patch_protocol
topic: patch
wild_version: "1.1"
status: supported
authority: engine
primary_terms:
  - ScenePatch
  - 增量修改
  - operations
  - add_element
  - update_element
  - remove_element
  - add_component
  - upsert_material
  - tune_material
  - 坐标系统
synonyms: []
---

# ScenePatch 增量修改协议

> 定义如何修改现有 Blueprint 的操作规范  
> 来源：`scenePatch.ts`、`agent_service.py`

本协议用于 Agent 对现有场景进行增量修改，而不是重新生成整个 Blueprint。

---

## 1. 协议职责分工

### 1.1 Agent 职责

- ✅ 根据用户需求生成 `operations` 数组
- ✅ 提供人类可读的 `summary`
- ✅ 检查目标对象是否存在
- ✅ 确保修改后引用关系有效

### 1.2 服务端职责

- ✅ 提供当前 Blueprint 和选中对象 ID
- ✅ 补齐 `patch_id`、`base_revision`、`type`、`source` 等元数据
- ✅ 应用 patch 到 Blueprint
- ✅ 执行完整性校验（引用、约束）

### 1.3 Agent 不应该做的

- ❌ 输出完整 Blueprint（应输出增量操作）
- ❌ 猜测元数据字段（patch_id、source 等由服务端补齐）
- ❌ 修改非目标对象（除非维持引用必需）

---

## 2. 操作类型

### 2.1 元素操作

#### add_element - 添加元素

```json
{
  "op": "add_element",
  "element": {
    "type": "wall",
    "id": "wall_new",
    "from": [0, 0, 0],
    "to": [10, 3, 0],
    "thickness": 0.3,
    "material": "stone"
  }
}
```

**约束**：

- `element.id` 必须唯一（不与现有 id 冲突）
- `element.type` 必须是基础元素类型
- 所有必填字段必须提供

#### update_element - 更新元素

```json
{
  "op": "update_element",
  "id": "wall_front",
  "changes": {
    "thickness": 0.4,
    "material": "brick"
  }
}
```

**约束**：

- `id` 必须存在于当前 Blueprint
- `changes` 不能为空
- 不能修改 `id` 或 `type` 字段
- 修改后必须满足所有约束

#### remove_element - 删除元素

```json
{
  "op": "remove_element",
  "id": "wall_temp"
}
```

**约束**：

- `id` 必须存在
- 删除后不能留下无效引用（如门窗引用了这面墙）
- 如有依赖，需要同时删除或更新依赖对象

### 2.2 组件操作

#### add_component - 添加组件

```json
{
  "op": "add_component",
  "component": {
    "type": "door",
    "id": "door_main",
    "parentWall": "wall_front",
    "from": [4.5, 0, 0],
    "width": 1.2,
    "height": 2.4
  }
}
```

**约束**：

- `component.id` 必须唯一
- `component.type` 必须是已注册的组合构件
- 所有引用（如 `parentWall`）必须有效

#### update_component - 更新组件

```json
{
  "op": "update_component",
  "id": "door_main",
  "changes": {
    "width": 1.5,
    "from": [4.0, 0, 0]
  }
}
```

**约束**：

- `id` 必须存在于 `geometry.components`
- `changes` 不能为空
- 不能修改 `id` 或 `type`

#### remove_component - 删除组件

```json
{
  "op": "remove_component",
  "id": "window_temp"
}
```

**约束**：

- `id` 必须存在
- 只删除指定组件

### 2.3 材质操作

#### upsert_material - 添加或更新材质

```json
{
  "op": "upsert_material",
  "name": "aged_stone",
  "material": {
    "baseColor": [0.6, 0.58, 0.52],
    "roughness": 0.9,
    "metallic": 0.0,
    "albedo": 1.0,
    "lightingCondition": "D65_noon",
    "effects": [
      {
        "type": "weathering",
        "dustColor": [0.48, 0.45, 0.38],
        "dustOpacity": 0.6,
        "crackIntensity": 0.15,
        "colorFade": 0.2
      }
    ]
  }
}
```

**约束**：

- `name` 是材质库中的键
- `material` 必须符合材质规范
- 纹理资产引用必须有效

#### tune_material - 微调现有材质

```json
{
  "op": "tune_material",
  "id": "wall_front",
  "new_name": "wall_front_darker",
  "changes": {
    "baseColor": [0.5, 0.48, 0.45]
  }
}
```

**约束**：

- `id` 是目标构件的 id
- 从目标当前材质克隆，应用 `changes`
- 不能修改图片 URL 或资产清单（只能修改数值参数）

---

## 3. 坐标系统的正确处理

### ⚠️ 关键注意事项

WILD 使用 `[X, Y, Z]` 数组，其中 `Y` 是高度，但**不同字段使用不同的坐标系**。

### 3.1 世界坐标

**使用世界坐标的字段**：

- `wall.from` / `wall.to`
- `stair.from` / `stair.to`
- `roof.position`
- `column.base`
- `primitive.position`
- 其他未引用父元素的 `position` 字段

**含义**：

- `[X, Y, Z]` 是场景全局坐标
- `Y` 是高度（竖直方向）
- `X` 和 `Z` 是水平平面

**修改示例**：

```jsonc
// 将墙体整体上移 0.5m
{
  "op": "update_element",
  "id": "wall_front",
  "changes": {
    "from": [0, 0.5, 0],   // Y 增加 0.5
    "to": [10, 3.5, 0]     // Y 增加 0.5
  }
}
```

### 3.2 墙挂组件局部坐标

**使用局部坐标的字段**：

- `door.from`
- `window.from`
- `opening.from`
- `balcony.from`
- `canopy.from`

**含义**：

- `[沿父墙距离, 底部世界Y, 墙体法向偏移]`
- `from[0]`：沿墙方向的距离（从墙起点算）
- `from[1]`：底部的世界 Y 坐标（不是相对墙底）
- `from[2]`：沿墙体法向的偏移（通常为 0）

**⚠️ 特别注意**：`from[2]` 不是世界 Z 坐标！

**修改示例**：

```jsonc
// 将窗户沿墙向右移动 1m
{
  "op": "update_component",
  "id": "window_front_1",
  "changes": {
    "from": [4.5, 0.9, 0]  // from[0] 从 3.5 改为 4.5
  }
}

// 将窗户向上移动 0.5m
{
  "op": "update_component",
  "id": "window_front_1",
  "changes": {
    "from": [3.5, 1.4, 0]  // from[1] 从 0.9 改为 1.4
  }
}
```

### 3.3 常见错误

```jsonc
// ❌ 错误：把 from[2] 当成世界 Z
{
  "op": "update_component",
  "id": "window_1",
  "changes": {
    "from": [3, 1, 5]  // ❌ from[2]=5 会被理解为法向偏移 5m，不是世界 Z=5
  }
}

// ✅ 正确：修改墙挂组件的 Z，应该移动父墙
{
  "operations": [
    {
      "op": "update_element",
      "id": "wall_front",
      "changes": {
        "from": [0, 0, 5],
        "to": [10, 3, 5]
      }
    }
  ]
}
```

---

## 4. 引用完整性

### 4.1 添加引用前检查

```python
# 添加门窗前，检查父墙是否存在
def validate_add_door(door, blueprint):
    parent_wall_id = door["parentWall"]
    if not find_element_by_id(blueprint, parent_wall_id):
        raise ReferenceError(f"parentWall '{parent_wall_id}' not found")
```

### 4.2 删除元素前检查依赖

```python
# 删除墙体前，检查是否有门窗依赖
def validate_remove_wall(wall_id, blueprint):
    components = blueprint["geometry"]["components"]
    dependent = [c for c in components if c.get("parentWall") == wall_id]
    if dependent:
        raise DependencyError(
            f"Cannot remove wall '{wall_id}': {len(dependent)} components depend on it"
        )
```

### 4.3 更新引用时同步修改

```jsonc
// 如果修改墙体 id，需要更新所有依赖
{
  "operations": [
    {
      "op": "update_element",
      "id": "wall_old",
      "changes": {"id": "wall_new"}  // ❌ 不允许修改 id
    }
  ]
}

// 正确做法：先添加新墙，更新依赖，再删除旧墙
{
  "operations": [
    {"op": "add_element", "element": {..., "id": "wall_new"}},
    {"op": "update_component", "id": "door_1", "changes": {"parentWall": "wall_new"}},
    {"op": "update_component", "id": "window_1", "changes": {"parentWall": "wall_new"}},
    {"op": "remove_element", "id": "wall_old"}
  ]
}
```

---

## 5. 最小修改原则

### ✅ 正确做法

```jsonc
// 用户："把这扇门加宽 20cm"
{
  "operations": [
    {
      "op": "update_component",
      "id": "door_main",
      "changes": {
        "width": 1.4  // 只修改宽度
      }
    }
  ],
  "summary": "将 door_main 宽度从 1.2m 增加到 1.4m"
}
```

### ❌ 错误做法

```jsonc
// ❌ 不要输出完整对象
{
  "operations": [
    {
      "op": "update_component",
      "id": "door_main",
      "changes": {
        "type": "door",           // ❌ 不能修改 type
        "parentWall": "wall_1",   // ❌ 没必要重复
        "from": [4.5, 0, 0],      // ❌ 没必要重复
        "width": 1.4,             // ✅ 这是需要修改的
        "height": 2.4             // ❌ 没必要重复
      }
    }
  ]
}
```

---

## 6. 响应格式

### 标准响应

```json
{
  "operations": [
    {
      "op": "update_element",
      "id": "wall_front",
      "changes": {
        "thickness": 0.4
      }
    }
  ],
  "summary": "将 wall_front 厚度从 0.3m 增加到 0.4m"
}
```

### 不需要的字段（由服务端补齐）

```jsonc
{
  "type": "ScenePatch",         // ❌ Agent 不输出
  "patch_id": "uuid",           // ❌ 服务端生成
  "base_revision": "rev_123",   // ❌ 服务端提供
  "source": "agent",            // ❌ 服务端标记
  "mode": "incremental",        // ❌ 服务端确定
  "requires_confirmation": true // ❌ 服务端判断
}
```

---

## 7. 实现来源

- `wild-web/src/types/scenePatch.ts` - TypeScript 类型定义
- `wild-server/app/services/agent_service.py` - Python 实现
- `wild-server/app/services/blueprint_service.py` - Patch 应用逻辑

---

## 8. 使用检查清单

生成 ScenePatch 前：

- [ ] 确认目标对象存在于当前 Blueprint？
- [ ] 只修改必要的字段？
- [ ] 理解了字段的坐标系统（世界 vs 局部）？
- [ ] 检查了修改后的引用完整性？
- [ ] 删除操作检查了依赖关系？
- [ ] 提供了清晰的 summary？

违反任何规则都会导致 patch 应用失败。
