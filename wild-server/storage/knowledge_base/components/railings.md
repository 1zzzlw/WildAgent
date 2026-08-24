---
knowledge_layer: wild_schema
entity_type: railing
entity_name: path_railing_component
topic: schema
status: supported
authority: engine
source: wild-web/wild-lang/schema.json
primary_terms:
  - 栏杆
  - railing
  - geometry.components
  - path
  - postSpacing
  - railLevels
synonyms: []
---

# 路径栏杆组合构件

## 当前支持的路径栏杆

`railing` 必须写入 `geometry.components`。它根据显式路径生成等距圆柱立杆，并在每段路径上按高度比例生成圆形横杆；路径可以随楼梯高度变化。默认路径为世界坐标，指定 `parentFloor` 后改用父楼板局部坐标。

### 参数契约

| 字段 | 要求 |
|---|---|
| `type` | 固定为 `railing` |
| `id` | 非空且与全部元素、组件 ID 唯一 |
| `path` | 至少两个不重合的世界坐标点 |
| `height` | 正数，表示立杆高度 |
| `postSpacing` | 可选正数，默认 1.2m |
| `postRadius` | 可选正数，默认 0.035m |
| `railRadius` | 可选正数，默认 0.045m |
| `railLevels` | 可选，1–8 个不重复比例，每个值位于 `(0, 1]` |
| `material` | 可选，必须引用已有材质 |
| `parentFloor` | 可选；指定后 `path` 相对矩形楼板左下角顶面或圆形楼板中心顶面 |

### 有效 JSON 片段

以下是 `geometry.components` 数组中的一个片段，不是完整 `.wild` 文件：

```json
{
  "type": "railing",
  "id": "terrace_railing",
  "path": [[0, 3, 0], [4, 3, 0]],
  "height": 1.1,
  "postSpacing": 0.8,
  "postRadius": 0.035,
  "railRadius": 0.045,
  "railLevels": [0.5, 1],
  "material": "metal"
}
```

### 当前边界

- 单个栏杆最多生成 2000 根立杆，横杆最多 8 层。
- 重复路径点、重复横杆比例、非正尺寸会导致组件编译失败。
- 当前只表达静态几何，不代表满足栏杆高度、杆件净距或结构安全规范。
- 自动栏杆、曲面扶手、任意截面扫掠和交互行为仍未实现。
