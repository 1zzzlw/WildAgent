---
entity_name: scene_patch_protocol
topic: editing
status: supported
authority: engine
source: wild-server/app/services/agent_service.py; wild-web/src/types/scenePatch.ts
primary_terms:
  - ScenePatch
  - 修改蓝图
  - update_element
  - update_component
synonyms:
  - 场景修改
  - 增量编辑
---

# ScenePatch 增量修改协议

## 运行职责

当前 Blueprint、选中 ID 和用户要求由运行状态注入，不写进知识文档。模型先根据目标对象的 `type` 查明字段与坐标语义，再输出局部操作；服务端负责检查目标、操作名和应用后的完整 Blueprint，前端在用户确认后应用提案。

模型回复只包含 `operations` 与 `summary`。`type`、`patch_id`、`base_revision`、`source`、`mode` 和 `requires_confirmation` 由服务端发送提案时补齐。

## 操作与目标

| 操作 | 必要字段 | 约束 |
|---|---|---|
| `add_element` | `element` 完整对象 | ID 必须唯一，type 必须是基础元素 |
| `update_element` | 现有 `id`、非空 `changes` | 不能修改 `id` 或 `type` |
| `remove_element` | 现有 `id` | 删除后不能留下无效引用 |
| `add_component` | `component` 完整对象 | ID 必须唯一，type 必须是已注册组合构件 |
| `update_component` | 现有 `id`、非空 `changes` | 不能修改 `id` 或 `type` |
| `remove_component` | 现有 `id` | 只删除指定组件 |
| `upsert_material` | `name`、完整 `material` | 材质引用和纹理资产必须有效 |
| `tune_material` | 目标 `id`、`new_name`、受控 `changes` | 从目标当前材质克隆，不能修改图片 URL 或资产清单 |

只修改用户指定的目标和维持有效引用所必需的关联对象。不要用完整 Blueprint 替代增量修改。

## 坐标修改必须按字段解释

WILD 的三维数组顺序为 `[X, Y, Z]`，其中 `Y` 是高度，`X/Z` 是平面方向。但不同字段可能使用世界坐标或宿主局部坐标，不能把“修改 Z”统一理解为改数组第三项：

- `wall.from/to`、`stair.from/to`、`roof.position` 与普通 `position` 使用世界坐标。
- `door/window/opening.from` 使用 `[沿父墙距离, 底部世界Y, 墙体法向偏移]`；其中 `from[2]` 是法向偏移，不是世界 Z。
- 更新墙体平面位置时通常需要同时修改 `from` 与 `to`，并重新检查端点连接、屋盖覆盖和依附构件。
- 更新门窗位置时先读取 `parentWall`，再在父墙有效长度和高度内修改局部 `from`。

移动一面世界坐标墙体的局部操作示例：

```json
{
  "operations": [
    {
      "op": "update_element",
      "id": "wall_front",
      "changes": {
        "from": [0, 0, 1.5],
        "to": [8, 3.2, 1.5]
      }
    }
  ],
  "summary": "将 wall_front 沿世界 Z 方向移动到 1.5m"
}
```

调整父墙上窗户沿墙位置的示例：

```json
{
  "operations": [
    {
      "op": "update_component",
      "id": "window_front_1",
      "changes": {
        "from": [3.2, 0.9, 0]
      }
    }
  ],
  "summary": "将 window_front_1 调整到父墙沿线 3.2m 处"
}
```

示例中的 ID 和数值只解释操作结构。真实值必须来自当前 Blueprint、用户请求和目标宿主，不能复制为默认坐标。
