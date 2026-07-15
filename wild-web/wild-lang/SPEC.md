# 原语语言规范 v1.0

## 一、文件格式

原语蓝图使用 JSON 编码。文件扩展名 `.wild`。

顶层结构必须包含 `meta` 和 `geometry`，可选 `materials` 和 `behaviors`。

```json
{
  "meta": { ... },
  "geometry": { ... },
  "materials": { ... },
  "behaviors": { ... }
}
```

## 二、元数据 (meta)

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `version` | string | 是 | 原语版本，当前 "1.0" |
| `type` | string | 是 | "building" 或 "avatar" |
| `name` | string | 是 | 实体名称 |
| `author` | string | 否 | 创建者地址 |
| `createdAt` | number | 否 | 创建时间戳 |
| `style` | string | 否 | 语义风格标识，如 "east-asian-tower" |
| `seed` | number | 否 | 随机种子，用于微调细节 |

## 三、几何原语 (geometry)

### 3.1 公共字段

所有构件都具有：

- `id`：唯一标识符
- `material`：引用材质库中的材质名（可选）

### 3.2 构件类型定义

参见 [PRIMITIVES.md](PRIMITIVES.md)。

### 3.3 高分辨率体积砖块 (dense_brick)

```json
{
  "type": "dense_brick",
  "id": "dragon_carving",
  "resolution": [256, 128, 256],
  "origin": [x, y, z],
  "data": "base64_gzip_encoded_voxel_data",
  "material": "stone",
  "method": "marching_cubes"
}
```

- `data`：体素数据，使用 RLE 或八叉树压缩后再 gzip 压缩，Base64 编码。
- `method`：重建算法，可选 "marching_cubes"（平滑）或 "dual_contouring"（保留锐边）。若不指定，引擎自动选择。
- 体积砖块可携带颜色信息：每个体素除了密度值还可包含 RGBA 通道。此时 `material` 可省略，颜色由体素数据直接提供。

### 3.4 骨架变形 (body，化身专用)

```json
{
  "type": "body",
  "id": "avatar_body",
  "height": 0.72,
  "build": "lean",
  "headShape": "oval",
  "armLength": 0.65,
  "legLength": 0.7,
  "cloakLength": 0.8,
  "hoodUp": false,
  "material": "avatar_skin"
}
```

### 3.5 模板与实例

蓝图可以包含 `templates` 字典和 `instances` 数组：

```json
{
  "templates": {
    "pillar": { "type": "column", "height": 3.3, "radius": 0.15, "material": "wood" }
  },
  "instances": [
    { "ref": "pillar", "position": [0, 0, 0] },
    { "ref": "pillar", "position": [3, 0, 0] }
  ]
}
```

**模板 id 规则**：模板定义中的构件 `id` 可选。引擎展开实例时自动按 `{模板名}_{实例索引}` 方式生成唯一 id（例如 `pillar_0`、`pillar_1`）。

实例可以覆盖模板中的材质：

```json
"materialOverride": { "column": "stone" }
```

### 3.6 布局放置 (placements)

`placements` 数组提供了一种用数学规则批量生成构件实例的方式。与 `instances` 逐个指定位置不同，`placements` 通过父构件表面 + 网格布局参数自动计算每个实例的位置和朝向。

**适用场景**：屋顶瓦片铺排、墙面砖缝排列、地板铺装、密集装饰阵列等。

**语法**：

```json
"placements": [
  {
    "id": "roof_tiles_left",
    "template": "roof_tile",
    "onSurface": {
      "parent": "main_roof",
      "face": ["left", "right"]
    },
    "layout": {
      "type": "grid",
      "columns": 19,
      "rows": 23,
      "rowSpacing": 0.183,
      "colSpacing": 0.308,
      "overlap": 0.04,
      "gapWidth": 0.008
    }
  }
]
```

**字段说明**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 本 placement 的唯一标识，引擎用它构建实例 id 前缀 |
| `template` | string | 是 | 引用的模板名，须在顶层 `templates` 中定义 |
| `onSurface` | object | 是 | 指定放置目标表面 |
| `onSurface.parent` | string | 是 | 目标构件 ID |
| `onSurface.face` | string 或 string[] | 是 | 目标表面的名称。可以是单一面（如 `"left"`）或面名数组（如 `["left", "right"]`）。各面共用一个 layout 参数。面的命名规则参见各构件类型定义 |
| `layout` | object | 是 | 放置布局描述 |

**`layout.type: "grid"` 参数**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `columns` | number | 是 | 每行瓦/块数（沿表面 U 方向） |
| `rows` | number | 是 | 行数（沿表面 V 方向） |
| `colSpacing` | number | 是 | 列间距（米），含块宽和缝隙 |
| `rowSpacing` | number | 是 | 行间距（米），含块高和缝隙 |
| `overlap` | number | 否 | V 方向重叠量（米），用于叠瓦场景。为 0 时无重叠 |
| `gapWidth` | number | 否 | 同排行之间的缝隙宽度（米）。默认 0.008 |
| `cellMaterials` | object | 否 | 按格子覆盖材质。键为 `"{行}_{列}"`，值为材质名。例：`{"3_5": "broken_tile"}` 表示第 3 行第 5 列的格子使用 "broken_tile" 材质而非模板默认材质 |

**展开规则**：

引擎按以下步骤将一条 placement 展开为若干独立构件：

1. 根据 `onSurface.parent` 查找父构件，根据 `onSurface.face` 确定目标表面。
2. 从父构件的几何定义中推导目标表面的四角坐标和法线方向。
3. 在表面上以 (U, V) 网格计算每个放置点的 3D 坐标：
   - U 方向第 col 列：`u = col * colSpacing`
   - V 方向第 row 行：`v = row * rowSpacing`
   - 网格原点位于表面的第一个角（底前）。
4. 每个放置点生成一个独立构件，构件定义为模板的深拷贝，并覆写：
   - `position`：根据表面四角插值计算的 3D 坐标
   - `rotation`：对齐表面法线的朝向（XYZ 欧拉角）
5. 构件的 `id` 自动生成为 `{placement_id}_{行}_{列}`（若 `face` 为数组则加上面索引，如 `roof_tiles_left_0_0`）。

**与 instances 的关系**：

- `placements` 和 `instances` 在同一蓝图中共存，引擎先展开 placements，再追加 instances。
- 两者展开后的结果合并为一个元素列表，输入模板展开器后的同一处理管线。因此 placements 生成的实例同样可被 behaviors 中的事件引用。

参见 [MATERIALS.md](MATERIALS.md)。

## 五、动态原语 (behaviors)

参见 [BEHAVIORS.md](BEHAVIORS.md)。

**作用范围说明**：
- 顶层 `behaviors.physics` 作用于整个实体的物理存在。对于 `type: "building"`，质量设为 0 表示整体不可移动；约束定义构件间的机械连接关系。
- 顶层 `behaviors.animation` 作用于化身实体的运动姿态，仅对 `type: "avatar"` 有效。
- 顶层 `behaviors.scripts` 通过事件条件中的构件 id 定位到具体元素。

## 六、版本兼容

引擎在解析蓝图时验证 `meta.version`。若版本不兼容，引擎拒绝解析并返回错误。

原语语言规范遵循"永不删除"原则：更高版本只增加新构件类型、新字段、新效果层和新指令，不删除或修改任何已定义内容。v1.0 中合法的蓝图在 v2.0 中继续有效且语义不变。

## 七、合规性

任何声称实现本语言规范的引擎，必须通过原荒协议发布的合规性测试套件。该套件包含一组标准蓝图及其已知正确的输出网格哈希。
