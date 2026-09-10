---
entity_type: stair
entity_name: stair_component
topic: parameters
status: supported
authority: engine
source: wild-web/src/wild-core/src/primitive/resolver.ts
primary_terms:
  - 楼梯
  - stair
  - 直跑楼梯
  - 楼层连接
synonyms:
  - staircase
  - stairs
---

# 楼梯参数与连接关系

## 字段契约

`stair` 写入 `geometry.elements`。必填字段为唯一 `id`、下端 `from`、上端 `to` 和正数 `width`；`material`、`stepCount`、`stepDepth`、`stepHeight` 可选。`from` 与 `to` 都是世界坐标，Y 表示两端标高。

```json
{
  "type": "stair",
  "id": "stair_run_1",
  "from": [2.0, 0.2, 1.0],
  "to": [2.0, 3.4, 5.0],
  "width": 1.4,
  "material": "stair_finish"
}
```

示例数值只解释一段楼梯的字段关系，不是住宅或公共建筑的默认尺寸。

## Resolver 行为

省略有效 `stepCount` 时，`resolveStairSteps` 根据总高差和 XZ 欧氏距离估算步数，内部目标值为步高 `0.18`、步深 `0.30`，再令 `stepHeight × stepCount` 等于总高差、`stepDepth × stepCount` 等于水平长度。这些数值是当前几何解析算法参数，不是建筑法规或项目设计配额。

若总高差或水平长度不超过 `0.25`，解析器退化为一个踏步，并把对应步高或步深限制为至少 `0.05`。显式提供正 `stepCount` 时，解析器不会重新计算；调用方须保证步数、步高、步深与端点一致。

## 当前已校验的楼层连接

- 下端和上端需要分别落在对应标高的楼板区域内，且上端标高高于下端标高。
- 一段 `stair` 只能表达从 `from` 到 `to` 的直跑，不能在中途转向。
- 折跑楼梯使用多段 `stair` 与中间 `floor` 平台；相邻段端点共享平台标高与可达区域。
- 多层建筑为每一对相邻楼层建立实际连接，不能复制一段楼梯而保留原端点。

## 能力边界

当前几何只表达楼梯踏步和宽度，不证明疏散宽度、人体工学、扶手、防火或结构承载合规。旋转、弧形和连续螺旋楼梯没有原生路径类型；只有批准设计接受近似时才能分段表达。

## 校验与尚未实现的边界

当前流水线检查 `from/to` 格式、正宽度、标高对齐、两端楼板区域、相邻梯段平台位置以及通用碰撞。它尚不检查楼梯穿越上层楼板时是否留出完整洞口，也不计算房间可达性；这两项不能只靠本文宣称为已执行硬规则。发现已覆盖问题时修复端点或平台关系，不用建筑类型的经验尺寸覆盖批准设计。
