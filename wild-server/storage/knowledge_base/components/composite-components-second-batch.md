---
knowledge_layer: wild_schema
entity_type: component
entity_name: composite_components_second_batch
topic: schema
status: supported
authority: engine
source: wild-web/wild-lang/schema.json
primary_terms:
  - 第二批组合构件
  - composite component
  - canopy
  - balcony
  - ramp
  - bay_window
  - cornice
  - chimney
synonyms: []
---

# WILD 第二批组合构件

## 雨棚 canopy

<!-- rag-meta
entity_type: canopy
entity_name: wall_canopy_component
topic: schema
status: supported
authority: engine
primary_terms:
  - 雨棚
  - canopy
  - parentWall
  - supportCount
synonyms: []
-->

`canopy` 写入 `geometry.components`，依附墙体并编译为一块 `primitive.box` 顶板和可选支柱。`from` 是 `[沿父墙距离, 安装世界Y, 墙体法向偏移]`；必填 `parentWall`、`width`、`depth`、`thickness`。`supportCount` 为 0–16 的可选整数。

以下是 `geometry.components` 数组片段，不是完整 `.wild` 文件；假定 `front_wall` 已存在：

```json
{
  "type": "canopy",
  "id": "entry_canopy",
  "parentWall": "front_wall",
  "from": [1.2, 2.5, 0],
  "width": 2.4,
  "depth": 1.1,
  "thickness": 0.12,
  "supportCount": 2,
  "supportSize": 0.06
}
```

## 阳台 balcony

<!-- rag-meta
entity_type: balcony
entity_name: wall_balcony_component
topic: schema
status: supported
authority: engine
primary_terms:
  - 阳台
  - balcony
  - slabThickness
  - railingHeight
synonyms: []
-->

`balcony` 依附墙体，编译为悬挑楼板和 U 形路径栏杆。`from` 是 `[沿父墙距离, 楼板顶面世界Y, 墙体法向偏移]`；通常令 `from[2]=0`，编译器根据宿主墙相对建筑水平包围盒中心的位置推断室外方向，并让正数 `depth` 始终向室外悬挑。必填 `width`、`depth`、`slabThickness`。`railingHeight` 和 `postSpacing` 控制防护外观，但不代表通过建筑规范校核。

同一阳台只能保留一个 `balcony` 组件。组件自身已经包含悬挑板和三面 U 形栏杆，不得再生成与其重合的独立 `floor` 或三段 `railing`；合并阶段会清理这种重复表达。只有不属于该阳台的连续露台或其他真实临空边，才单独使用楼板和栏杆。

以下是 `geometry.components` 数组片段，不是完整 `.wild` 文件；假定 `front_wall` 已存在：

```json
{
  "type": "balcony",
  "id": "bedroom_balcony",
  "parentWall": "front_wall",
  "from": [3, 3.2, 0],
  "width": 2.8,
  "depth": 1.3,
  "slabThickness": 0.18,
  "railingHeight": 1.1,
  "postSpacing": 0.9
}
```

## 坡道 ramp

<!-- rag-meta
entity_type: ramp
entity_name: straight_ramp_component
topic: schema
status: supported
authority: engine
primary_terms:
  - 坡道
  - ramp
  - railingSides
  - parentFloor
synonyms: []
-->

`ramp` 使用 `from`、`to` 定义直线坡道上表面中心线，编译为连续 `primitive.profile_sweep` 斜板。选定栏杆侧会同时生成随坡侧缘挡台、竖直立柱和上下两道连续扶手；栏杆基点从挡台顶面计算，不得另猜高度。必填 `width`、`thickness`；`railingSides` 可为 `none`、`left`、`right`、`both`。未指定 `parentFloor` 时坐标是世界坐标；指定后坐标相对父楼板左下角顶面。

以下是 `geometry.components` 数组片段，不是完整 `.wild` 文件：

```json
{
  "type": "ramp",
  "id": "entry_ramp",
  "from": [0, 0, 0],
  "to": [5.4, 0.45, 0],
  "width": 1.5,
  "thickness": 0.18,
  "railingSides": "both",
  "railingHeight": 1.1,
  "postSpacing": 0.9
}
```

## 凸窗 bay_window

<!-- rag-meta
entity_type: bay_window
entity_name: projected_bay_window_component
topic: schema
status: supported
authority: engine
primary_terms:
  - 凸窗
  - 飘窗
  - bay_window
  - projectionDepth
  - parentWall
synonyms: []
-->

`bay_window` 依附墙体，编译为 `opening`、基础窗框、上下挑板和投影窗面。墙体定位字段与 `window` 相同，另必填正数 `projectionDepth`。它表达确定性静态凸窗几何，不自动生成室内窗台家具。

以下是 `geometry.components` 数组片段，不是完整 `.wild` 文件；假定 `side_wall` 已存在：

```json
{
  "type": "bay_window",
  "id": "living_bay_window",
  "parentWall": "side_wall",
  "from": [1.2, 0.9, 0],
  "width": 1.8,
  "height": 1.2,
  "projectionDepth": 0.45,
  "frameWidth": 0.06
}
```

## 檐口 cornice

<!-- rag-meta
entity_type: cornice
entity_name: profile_sweep_cornice_component
topic: schema
status: supported
authority: engine
primary_terms:
  - 檐口
  - 线脚
  - profile_sweep
  - parentRoof
  - cornice
synonyms: []
-->

`cornice` 把二维分层线脚 `profile` 沿三维 `path` 编译为 `primitive.profile_sweep`。路径至少两个不重合点，闭合截面至少三个二维点。建筑檐口应优先指定 `parentRoof`：路径 X/Z 相对屋顶中心，Y 是屋面高度偏移，未显式设置屋顶 `position` 时编译器会按结构墙包围盒推导与 Core 一致的屋顶原点。未指定 `parentRoof` 只适用于有意使用世界坐标的独立线脚；编辑器构件库不会再创建无依附的悬空檐口。屋顶依附当前只支持 `flat`、`gable`、`hip`。

以下是 `geometry.components` 数组片段，不是完整 `.wild` 文件；假定 `main_roof` 是跨度 8m、进深 6m 的双坡屋顶，路径沿其左侧檐边：

```json
{
  "type": "cornice",
  "id": "left_eave_cornice",
  "parentRoof": "main_roof",
  "path": [[-4, 0, -3], [-4, 0, 3]],
  "profile": [[-0.16, -0.14], [0.16, -0.14], [0.16, -0.07], [0.1, -0.07], [0.1, 0], [0.05, 0], [0.05, 0.08], [-0.16, 0.08]],
  "closedProfile": true
}
```

## 烟囱 chimney

<!-- rag-meta
entity_type: chimney
entity_name: hollow_chimney_component
topic: schema
status: supported
authority: engine
primary_terms:
  - 烟囱
  - chimney
  - parentRoof
  - wallThickness
  - capHeight
synonyms: []
-->

`chimney` 编译为四面薄壁和顶部压顶。必填 `position`、`width`、`depth`、`height`；`wallThickness` 必须小于宽度和深度的一半。指定 `parentRoof` 后，位置相对屋顶中心并贴到已计算屋面；这只完成定位和外观，不执行屋顶布尔穿透。

以下是 `geometry.components` 数组片段，不是完整 `.wild` 文件：

```json
{
  "type": "chimney",
  "id": "main_chimney",
  "position": [1.5, 0, 0.5],
  "width": 0.7,
  "depth": 0.7,
  "height": 2,
  "wallThickness": 0.1,
  "capHeight": 0.08
}
```

## 第二批组件能力边界

<!-- rag-meta
entity_type: component
entity_name: second_batch_component_boundaries
topic: constraints
status: supported
authority: engine
primary_terms:
  - 组合构件边界
  - roof penetration
  - CSG
  - terrain
  - 能力限制
synonyms: []
-->

第二批组件只使用当前 Core 的 `opening`、`primitive`、`beam` 和 `profile_sweep`。当前没有通用 CSG、屋顶真实穿透、复杂曲面屋顶依附、地形贴合、中间坡道平台或结构安全计算。不得把烟囱外观误述为屋顶已开孔，也不得把栏杆参数误述为符合建筑规范。
