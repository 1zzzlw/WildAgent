---
entity_name: furniture_layout_examples
topic: composition
status: experimental
authority: schema
primary_terms:
  - 家具与桌椅组合 JSON 示例
synonyms: []
---

# 家具与桌椅组合 JSON 示例

## 沙发 · sofa

<!-- rag-meta
entity_type: furniture
entity_name: sofa
topic: composition
primary_terms:
  - 沙发
  - sofa
synonyms:
  - couch
  - 三人沙发
-->

原生 furniture.sofa 表达底座、靠背、扶手与坐垫，正面朝 +Z，position 是底面中心；落地 Y 取所在楼板顶标高。示例宽 2.3、深 0.9、高 0.8 为自选米制设计值。来源的钢丝外框与软包曲面没有在本原生样例中复原，需要精确分件时改用 primitive 组合；不能把此简化沙发称为原厂模型。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"furniture","id":"sofa","subtype":"sofa","position":[0,0,0],"rotation":[0,0,0],"dimensions":{"width":2.3,"depth":0.9,"height":0.8},"material":"fabric"}
    ],
    "components":[],
  "materials":{"fabric":{"baseColor":[0.53,0.58,0.65],"roughness":0.9,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Herman Miller Wireframe 沙发立面与尺寸图，第 1 页](https://www.hermanmiller.com/content/dam/hermanmiller/documents/product_literature/product_sheets/emea/wireframe_sofa_product_sheet_en-gb.pdf)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 茶几 · coffee-table

<!-- rag-meta
entity_type: furniture
entity_name: coffee_table
topic: composition
primary_terms:
  - 茶几
  - coffee-table
synonyms:
  - coffee table
  - 矮桌
-->

用 furniture.table 将桌面与腿组合成低桌。position 是底面中心，height 控制桌面总高；这里用矩形四腿近似，来源的圆桌与中心支脚仅为桌面、支承关系参考，未照搬产品结构。宽深、高度、材料与离沙发距离由图纸决定。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"furniture","id":"coffee_table","subtype":"table","position":[0,0,0],"rotation":[0,0,0],"dimensions":{"width":1.1,"depth":0.6,"height":0.42},"material":"wood"}
    ],
    "components":[],
  "materials":{"wood":{"baseColor":[0.3,0.18,0.1],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Herman Miller Eames 桌台图纸，第 1 页](https://www.hermanmiller.com/content/dam/hermanmiller/documents/product_literature/product_sheets/eames_occasional_table_product_sheet.pdf)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 餐桌椅 · dining-table-chairs

<!-- rag-meta
entity_type: furniture
entity_name: dining_table_chairs
topic: composition
primary_terms:
  - 餐桌椅
  - dining-table-chairs
synonyms:
  - dining set
  - dining table chairs
  - 餐桌
  - dining_table
-->

餐桌和每把椅子分别写为 furniture 元素；椅背在 -Z，正面 +Z，rotation[1] 为弧度。两侧椅子转向桌边；示例椅子靠近桌边，正式安装仍要按房间留出拉椅与通行空间。餐椅是盒体近似，没有来源的曲面坐背或金属支脚造型。人数、布置和各尺寸为设计变量，不要求所有餐厅四椅。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"furniture","id":"dining_table","subtype":"table","position":[0,0,0],"rotation":[0,0,0],"dimensions":{"width":1.6,"depth":0.85,"height":0.75},"material":"wood"},
      {"type":"furniture","id":"dining_chair_0","subtype":"chair","position":[-0.45,0,-0.7],"rotation":[0,0,0],"dimensions":{"width":0.45,"depth":0.45,"height":0.85},"material":"wood"},
      {"type":"furniture","id":"dining_chair_1","subtype":"chair","position":[0.45,0,-0.7],"rotation":[0,0,0],"dimensions":{"width":0.45,"depth":0.45,"height":0.85},"material":"wood"},
      {"type":"furniture","id":"dining_chair_2","subtype":"chair","position":[-0.45,0,0.7],"rotation":[0,3.141592653589793,0],"dimensions":{"width":0.45,"depth":0.45,"height":0.85},"material":"wood"},
      {"type":"furniture","id":"dining_chair_3","subtype":"chair","position":[0.45,0,0.7],"rotation":[0,3.141592653589793,0],"dimensions":{"width":0.45,"depth":0.45,"height":0.85},"material":"wood"}
    ],
    "components":[],
  "materials":{"wood":{"baseColor":[0.3,0.18,0.1],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Herman Miller Eames 餐椅图纸，第 2 页](https://www.hermanmiller.com/content/dam/hermanmiller/documents/product_literature/product_sheets/eames_molded_plastic_dining_chair_product_sheet.pdf)；[Herman Miller Eames 桌台图纸，第 1 页](https://www.hermanmiller.com/content/dam/hermanmiller/documents/product_literature/product_sheets/eames_occasional_table_product_sheet.pdf)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 床 · bed

<!-- rag-meta
entity_type: furniture
entity_name: bed
topic: composition
primary_terms:
  - 床
  - bed
synonyms:
  - 双人床
  - double bed
-->

furniture.bed 表达床架、床垫与床头板，床头在 -Z；height 是床头总高，不能当床垫离地高度。position 取底面中心和楼板顶标高；需要明确床垫、床头或床架不同材质/高度时拆为 primitive，不虚构 mattressHeight。来源的储物举升机构与排骨架未实现，示例尺寸自选。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"furniture","id":"bed","subtype":"bed","position":[0,0,0],"rotation":[0,0,0],"dimensions":{"width":1.8,"depth":2.0,"height":1.05},"material":"wood"}
    ],
    "components":[],
  "materials":{"wood":{"baseColor":[0.3,0.18,0.1],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[IKEA MALM 床架装配图，第 1 页](https://www.ikea.com/us/en/assembly_instructions/malm-storage-bed-white__AA-2055625-9-100.pdf)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 衣柜 · wardrobe

<!-- rag-meta
entity_type: furniture
entity_name: wardrobe
topic: composition
primary_terms:
  - 衣柜
  - wardrobe
synonyms:
  - closet
-->

furniture.wardrobe 为柜身、前侧双门和踢脚的简化整体，正面 +Z，position 是底面中心。来源只提供柜体板件参考，不是衣柜产品复刻；门为静态几何，不具备开门交互。宽深高与位置由图纸给定；要开放挂衣区或多门分格可组合 primitive，不添加未知 cabinetDoors 字段。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"furniture","id":"wardrobe","subtype":"wardrobe","position":[0,0,0],"rotation":[0,0,0],"dimensions":{"width":1.8,"depth":0.6,"height":2.2},"material":"wood"}
    ],
    "components":[],
  "materials":{"wood":{"baseColor":[0.3,0.18,0.1],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[IKEA METOD 柜体装配图，第 1 页](https://www.ikea.com/de/de/assembly_instructions/metod-korpus-wandschrank-weiss__AA-2238433-5-2.pdf)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 书架 · bookshelf

<!-- rag-meta
entity_type: furniture
entity_name: bookshelf
topic: composition
primary_terms:
  - 书架
  - bookshelf
synonyms:
  - bookcase
  - 书柜
-->

原生 furniture.bookshelf 含侧板、背板、上下板及两块中间隔板；不能凭 dimensions 声称实现来源全部层数。此例保留开放书架的板件关系，正面 +Z。需要更多层、独立材质或异形柜时用多个 primitive.box 表达，书本不是默认实体。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"furniture","id":"bookshelf","subtype":"bookshelf","position":[0,0,0],"rotation":[0,0,0],"dimensions":{"width":0.9,"depth":0.3,"height":1.8},"material":"wood"}
    ],
    "components":[],
  "materials":{"wood":{"baseColor":[0.3,0.18,0.1],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[IKEA BILLY 书架装配图，第 1 页](https://www.ikea.com/us/en/assembly_instructions/billy-bookcase-white__AA-2289105-4-100.pdf)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 床头柜 · nightstand

<!-- rag-meta
entity_type: furniture
entity_name: nightstand
topic: composition
primary_terms:
  - 床头柜
  - nightstand
synonyms:
  - bedside table
-->

furniture.nightstand 表达台面、低柜与静态抽屉分缝。position 取楼板顶，不挂 parentWall；柜前朝 +Z。来源的板件关系缩减为独立低柜，抽屉不可拉动；本例不自动配置床或台灯。数量、宽深高与床边距离由本次设计决定。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"furniture","id":"nightstand","subtype":"nightstand","position":[0,0,0],"rotation":[0,0,0],"dimensions":{"width":0.5,"depth":0.45,"height":0.5},"material":"wood"}
    ],
    "components":[],
  "materials":{"wood":{"baseColor":[0.3,0.18,0.1],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[IKEA METOD 柜体装配图，第 1 页](https://www.ikea.com/de/de/assembly_instructions/metod-korpus-wandschrank-weiss__AA-2238433-5-2.pdf)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 电视柜 · tv-cabinet

<!-- rag-meta
entity_type: furniture
entity_name: tv_cabinet
topic: composition
primary_terms:
  - 电视柜
  - tv-cabinet
synonyms:
  - tv cabinet
  - 电视机柜
-->

furniture.tv_cabinet 表达低柜台面、两侧柜体与中央设备区；柜前 +Z，底部锚点放在楼板顶。来源只用于柜体分件参考，本例没有电视屏幕或可操作设备。需要屏幕时另组合薄 primitive.box；整体长度、高度和分格应从图纸确定。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"furniture","id":"tv_cabinet","subtype":"tv_cabinet","position":[0,0,0],"rotation":[0,0,0],"dimensions":{"width":1.8,"depth":0.4,"height":0.5},"material":"wood"}
    ],
    "components":[],
  "materials":{"wood":{"baseColor":[0.3,0.18,0.1],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[IKEA METOD 柜体装配图，第 1 页](https://www.ikea.com/de/de/assembly_instructions/metod-korpus-wandschrank-weiss__AA-2238433-5-2.pdf)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。

## 书桌椅 · desk-chair

<!-- rag-meta
entity_type: furniture
entity_name: desk_chair
topic: composition
primary_terms:
  - 书桌椅
  - desk-chair
synonyms:
  - desk
  - 书桌
  - 办公桌
  - desk chair
-->

书桌与座椅分别用 furniture.table/chair，椅子正面转向桌子。示例椅子在桌前 +Z 并旋转 π 弧度，底面 Y 相同。来源提供桌面支承与椅背参考，示例为自选矩形桌、简化椅；没有显示器和抽屉。通行、桌椅距离及房间朝向由本次图纸调整。

下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。

```json
{
    "elements":[
      {"type":"furniture","id":"desk","subtype":"table","position":[0,0,0],"rotation":[0,0,0],"dimensions":{"width":1.2,"depth":0.6,"height":0.75},"material":"wood"},
      {"type":"furniture","id":"desk_chair","subtype":"chair","position":[0,0,0.65],"rotation":[0,3.141592653589793,0],"dimensions":{"width":0.45,"depth":0.45,"height":0.85},"material":"wood"}
    ],
    "components":[],
  "materials":{"wood":{"baseColor":[0.3,0.18,0.1],"roughness":0.7,"metallic":0,"albedo":1,"lightingCondition":"D65_noon"}}
}
```

参考：[Herman Miller Eames 桌台图纸，第 1 页](https://www.hermanmiller.com/content/dam/hermanmiller/documents/product_literature/product_sheets/eames_occasional_table_product_sheet.pdf)；[Herman Miller Eames 餐椅图纸，第 2 页](https://www.hermanmiller.com/content/dam/hermanmiller/documents/product_literature/product_sheets/eames_molded_plastic_dining_chair_product_sheet.pdf)。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。
