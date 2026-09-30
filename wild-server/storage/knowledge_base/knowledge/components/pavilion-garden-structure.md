---
doc_type: component
knowledge_role: capability
doc_scope: generation
knowledge_layer: wild_schema
entity_type: pavilion
entity_name: pavilion_garden_structure
topic: composition
status: supported
authority: maintainer
primary_terms:
  - 亭子
  - 四角亭
  - 凉亭
  - 水榭
  - 亭廊
  - 园林建筑
  - 六角亭
  - 八角亭
synonyms:
  - 亭
  - gazebo
  - pavilion
applies_to:
  - 亭子
  - 凉亭
  - 水榭
  - 园林建筑
  - 景观亭
---

# 亭与园林建筑的设计层表态

适用条件：**方案点名亭子、四角亭、凉亭、水榭、亭廊**等园林建筑时使用。它的本质是"有顶的柱廊节点"——**不是缩小版的房子**。把亭做成带四面实墙的多层体量是本形制最高频的错误。

## 形制判定（先于一切参数）

命中以下任一特征即按本形制设计，**禁止套用通用多层体量**：

- 体量小：面宽 3~6m（柱心距），单层；
- 围合开敞：柱承重、无墙或极少墙，视线穿透；
- 屋顶出檐大：0.6~1.2m，檐口是造型主体；
- 常带台基与坐凳栏杆。

## 设计层表态（当前生成链的合法通道）

| 通道 | 表态 | 说明 |
|---|---|---|
| `massing.shape` | `"pavilion"` 或 `"centralized"` | 单体居中；正方形平面 `width≈depth` |
| `massing.floors` | `1` | **恒单层**。四角亭写多层即形制错误 |
| `massing.floor_height` | `3.2~4.5` | 亭檐下净空比住宅层高高，显挺拔 |
| `facades`（四面） | **四面 pattern 全为 `"empty"`（默认）** | 关键：pattern 全空 = 该面**开敞无墙**（骨架不再生成该面墙体）。亭是环景建筑，**默认无墙无门**。**四面全空本身就是"此面无门"的系统级表态**——主入口强制自动豁免，不需要再写别的字段，也**不需要用 door 去满足入口**：不写 `entrance_bay`、任何面都不写 `door`。仅当**用户原文点名**月洞门/影壁墙等门时才在一面留一个 `"door"`（该面保留实墙），不得自行决定 |
| `required_components` | **只写亭子需要的**（如 `["column", "roof"]`，**不写 door**） | 辅助保险：两条等效豁免通道——①四面 pattern 全空（首选，见上行）；②设计清单显式不含 door。两条满足其一即四面干净开敞 |
| `roof.type` | `"chinese_curved"` 或 `"hip"` | 攒尖顶走 `chinese_curved`（编译器按中式屋顶派生锥坡）；**禁 `"dome"`**（西式半球穹顶）、禁 `gable`/`flat`（别墅语汇） |
| `roof.overhang` | `0.6~1.2` | 出檐是亭的比例核心，不许写 0 |
| `component_quota.column` | `min=4, max=4`（四角亭） | 角柱承重；六角/八角亭按面数给 |
| `component_quota.railing` | 可选 `min=0` | 坐凳栏杆/美人靠语义，点名才给 |
| `volumes` | 单个完整体量 | 不拆分、不退台 |

## 反模式（出现即形制错误）

- 多层体量、楼板重叠——亭没有"楼上"；
- 四面实墙 + 密排门窗——那是房子，不是亭；
- `shape: "rectangle"` + `roof: "gable"` + 25×18m——套用通用建筑档产出别墅；
- 圆形平面上写 `roof: "dome"`（攒尖禁 dome，见圆台锥坡体系）。

## 与其他形制的边界

- **圆形亭/圆台基/环形栏杆** → 圆台锥坡体系（攒尖锥坡、弦线围合栏杆、折面殿身）；
- **多层楼阁式**（有楼层、有平座） → 叠涩檐多层塔体系，不适用本文；
- **带墙的轩/榭**（一面实墙三面开敞） → 仍按本文单层开敞形制，仅一面 facade 给槽位。

## 能力边界（只标记不阻断）

- 角柱的**精确柱位**（四角内退尺寸）设计层没有逐柱坐标通道：配额点名后由构件生成层按体量角部布置；需要精确控制走 ScenePatch 修改链。
- 翘角、宝顶、坐凳靠背等细部为蓝图层技法，编译产物按引擎中式屋顶内置规则展开。

## 蓝图层产物示例

设计层主通道只表态 `massing.shape` / `roof.type` / `component_quota`；需要**逐柱精确控制**（四角内退、柱径柱距）时走 ScenePatch 修改链，蓝图层产物即 `column` 元素 + `roof` 元素。以下是 `geometry.elements` 数组中的组合片段，不是完整 `.wild` 文件：

```json
{
  "type": "column",
  "id": "pavilion_col_01",
  "base": [1.4, 0.45, 1.4],
  "height": 3.6,
  "bottomRadius": 0.12,
  "topRadius": 0.1,
  "style": "chinese_wooden",
  "material": "wood"
}
```

```json
{
  "type": "roof",
  "id": "pavilion_roof",
  "roofType": "chinese_curved",
  "span": 3.6,
  "depth": 3.6,
  "height": 2.2,
  "thickness": 0.16,
  "eaveOutset": 0.9,
  "tiers": 1,
  "material": "tile"
}
```

- 角柱 `base[1]` 落在台基/楼板顶（示例 0.45 为台基顶示意）；四角亭共 4 根，示例只给一根的写法。
- `roof.span` / `depth` 对应柱心距外包络，`eaveOutset` 即设计层 `roof.overhang` 的蓝图层落点；数值仅解释字段，开间、柱径、出檐量由本次方案决定。
- `material` 必须引用骨架 `materials` 里已存在的材质名；坐凳栏杆、宝顶等细部由构件层/引擎内置规则展开，不要在此处发明 schema 之外的字段。
