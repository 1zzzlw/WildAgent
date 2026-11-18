---
entity_name: architecture_design_expression
topic: parameters
status: supported
authority: maintainer
primary_terms:
  - 建筑设计表达
  - 设计意图
  - 体量立面屋面
synonyms: []
---

# 建筑图纸与构件实现

设计文档版本固定为 design/1.0。字段事实源为 app/domain/design/contracts.py 和 spatial_contracts.py；空间事实由 spatial.py 统一计算，历史输入只在 spatial_input.py 转换。WILD Schema 约束最终蓝图，不代替设计选择。

## 完整设计与职责

architecture 一次决定建筑用途、体量、标高、空间、开口、屋面、构件和材料意图。concept/design_intent 解释本次选择；实际几何写入对应结构字段。程序封装 DesignDocument，并从其 decisions 派生 architecture_plan，不能丢失轮廓、系统或关系。

massing.width/depth 是所有真实体量的总体包络上限，不是实际建筑轮廓。massing.shape 仅表意。levels 定义楼面、屋面、夹层或平台的世界标高；主要楼层 kind=storey、index从1连续计数，屋面 kind=roof不另计一层。标高引用使用 level及offset，程序计算世界Y。完整表达时 modeled_floors=floors；floor_height是默认层高，显式levels优先。

## 坐标与轮廓

单位为米、弧度，世界Y向上，二维平面点为[X,Z]，右手系。绕+Y旋转后 X'=X*cos(yaw)+Z*sin(yaw)，Z'=-X*sin(yaw)+Z*cos(yaw)。先处理截面缩放、转角和偏移，再应用体量placement；不要手工重复计算世界坐标。

profiles保存稳定ID和真实闭合轮廓。rectangle以原点为中心；circle使用radius；ellipse使用radius_x/radius_z；polygon以带ID的vertices、edges描述有向边；curve_loop由连续的line、arc、cubic_bezier组成。圆与椭圆的连续边名为perimeter，矩形边名front/right/back/left，多边形和曲线的边名由设计确定。holes引用内孔轮廓ID。闭合、连续、不自交、孔洞位于内部由程序校验。

volumes.placement包含origin_xz和yaw。geometry.type=extrusion引用profile、bottom/top标高；section_loft包含按标高递增的sections，各截面有at/profile/offset_xz/yaw/scale。截面间线性插值，边ID及孔洞拓扑保持一致；截面偏移可表达倾斜，缩放表达收分，转角表达扭转。体量在任意楼面处的真实截面由程序计算，不能用整体包围盒替代楼板范围。

## 墙、楼板与留洞

systems按ID保存本次共享构造；wall/slab必须明确thickness，material_role引用材料角色。walls是围护与内墙的唯一几何来源，门窗host引用其逻辑ID。墙可从volume_boundary的volume/edge提取，或用path的frame/segments独立定义。bottom/top是世界标高引用。曲线细分和放样网格由程序落实，不另发一批同位置墙体任务。

slabs指定system、top、region和holes；top为楼面完成面，板底=top减厚度。region可用profile_region，或用volume_union_section在明确level处截取多个体量并求并集。体量洞庭院保留在轮廓内孔中。voids声明具体楼面的楼梯孔或中庭范围，slab.holes引用后才扣洞；声明void不自动生成栏杆。

floor_layouts.level引用levels ID。rooms具有稳定ID、name和region，表示功能区域，不自动生成墙。需要的隔墙统一写walls，门统一写components。房间几何、墙和通行开口必须一致；不能以房间文字名称证明通行或专业安全条件成立。

## 门窗的宿主和安装

门窗host引用逻辑墙ID；程序沿有向墙路径测量offset，结合标高和法向偏移计算安装位置。后墙与前墙的路径方向可能相反，无需执行Agent重新推导四方向坐标规则。

下面是components中的单个局部设计片段，前提是本次已声明wall_entry和L1；尺寸是示例，不是默认值：

```json
{
  "id": "entry_door",
  "type": "door",
  "host": "wall_entry",
  "size": {"width": 1.4, "height": 2.4},
  "placement": {
    "mode": "wall",
    "anchor": "opening_start_bottom",
    "offset": 2.0,
    "elevation": {"level": "L1", "offset": 0},
    "normal_offset": 0
  },
  "form": {"description": "依据本次设计选择门扇和框型"}
}
```

opening_start_bottom/bottom_left表示洞口沿墙起点的下沿；elevation引用世界标高，不能与历史sill_height同时填写。独立构件用mode=world、明确anchor和position。size只写正尺寸，offset、normal_offset和标高偏移可以为0。同墙洞口不得重叠或超出实际可安装范围；分隔墙端头不能进入洞口内部。构造深化在已确定的位置和尺寸下补框扇参数，不改设计决定。

## 楼梯、阳台、屋面与材料

楼梯、阳台、栏杆和装饰均按本次功能或用户要求选择，不因字段存在就自动添加。选定楼梯时，在components声明形式、尺寸、安装锚点、footprint及floor_connections.from_level/to_level；opening引用voids中的上层留洞，access引用所需净空轮廓。上下口的form.lower_entry/upper_exit使用明确世界点。没有入口、尺寸或连接证据时保留待核查状态，不能把未选楼梯当作必备构件补上。

roofs逐片声明id、host、support、geometry和材料角色。屋型、真实outline和参数来自设计，不从总体宽深补一个矩形屋顶；没有独立屋面时使用空数组。同一片屋面不要同时写roofs和components。

materials.roles可声明本次自定义角色及其描述，base_role可引用已有材料用途。systems.material_role和components.material_role/material_bindings均使用这些稳定角色，后续材质节点落实实际PBR参数。角色不同可以使用不同材料，同一角色不应互相矛盾。

## 关系与执行边界

host表达坐标依附；relations记录supported_by、connects_spaces和aligned等设计关系，分别处理承托、通行和对齐。引用存在性不等于关系实体已验收；无法执行的关系保留needs_review，不用描述文字代替结果。circulation中所需通路与净空保留为显式设计条件。

当前确定性空间入口支持上述轮廓、拉伸、对应截面放样、真实楼板并集/留洞及直墙/圆弧墙宿主。自由Bezier墙和变化截面墙可生成放样实体，但其门窗需要进一步的曲面开洞能力。椭圆墙可生成主体，其门窗须核对执行器支持。sweep/revolve/surface_patches/boolean及通用anchor/surface定位保留设计目标，尚未落实的执行能力会明确报告capability_gaps；不能据此承诺完整渲染。

旧x/z/width/depth、四向facades、单对象roof和floor_layouts.walls只用于读取历史图纸，由一个适配入口转换。新方案统一使用上述空间字段，不同时生成pattern门窗和显式门窗。几何校验、设计履约、真实模型生成、渲染和人工视觉验收分别记录；上一层通过不证明下一层已完成。
