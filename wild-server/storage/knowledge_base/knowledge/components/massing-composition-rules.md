---
entity_name: massing_composition_rules
topic: composition
status: supported
authority: engine
primary_terms:
  - 体量组织
  - 逐层轮廓
  - 体量起点
  - 屋面覆盖
synonyms: []
---

# 体量与逐层轮廓的设计表达

本条解释当前 DesignDocument 到 Blueprint 的体量表达，而不是规定建筑应退台或错落。依据为 app/design/coordinates.py、app/agent/generation/architecture/planning.py、facade.py 和 app/agent/compiler/compile.py。轮廓、尺寸、对称、体量数量和材料由本次设计选择；普通单体同样可以成立，构件数量不是细部质量。

## 起点、包络和楼层

volumes 每项给 id、role、x、z、width、depth、start_floor 和 end_floor。x/z 是平面起点，覆盖区间为 [x,x+width] 与 [z,z+depth]，不是中心点；可负值或整体平移。massing.width/depth 是整体尺寸控制上限，实际跨度由体量并集计算。外墙按覆盖该层的体量生成，体量需覆盖建模楼层；显式冲突交给设计修订，不能裁剪体量或默默延伸其楼层。层高控制标高链，不要求固定 0.3 米模数。

## 多体量、退台和屋面

选择多体量时声明实际主次与连接范围，不能先选形状名称再期待系统猜出任意轮廓。当前支持独立相邻体量的 flat/gable/hip 分段屋面；完全上下叠置的体量按顶层承托生成顶部屋面。上层部分覆盖下层的局部剩余屋面返回 roof_partial_coverage，多体量其它屋型返回 roof_layout_unsupported。不能把“不报错的单块包围盒屋顶”当作保留了庭院或露台；未实现差异留给设计审核，不承诺自动可达露台。

## 楼板围绕矩形洞口分片

用户提供的咖啡厅、别墅和院落蓝图都通过分片楼板保留实际空缺。对一个轴对齐矩形楼板范围，可按洞口四边拆成不重叠的 `floor` 元素；洞口内不写板。以下是 `geometry.elements` 的局部示例：外框 X[0,8] × Z[0,6]，洞口 X[2,4] × Z[2,4]，板底 Y=3、板厚 0.2；`slab` 是已有材质引用。

```json
{"elements":[{"type":"floor","id":"slab_south","from":[0,3,0],"to":[8,3,2],"thickness":0.2,"material":"slab"},{"type":"floor","id":"slab_north","from":[0,3,4],"to":[8,3,6],"thickness":0.2,"material":"slab"},{"type":"floor","id":"slab_west","from":[0,3,2],"to":[2,3,4],"thickness":0.2,"material":"slab"},{"type":"floor","id":"slab_east","from":[4,3,2],"to":[8,3,4],"thickness":0.2,"material":"slab"}],"components":[]}
```

洞口位置、分片数量和楼板标高由本次图纸决定；边角洞口只需实际剩余片，异形洞口不能硬套四片矩形。若洞口供楼梯通行，还要核对梯跑和平台的投影、上下端标高与板顶；若是露天庭院，还要保持上方屋面同样留空。此片段不自动添加楼梯、屋顶或房间围护，也不代表完整建筑。

## 尺寸链与依附联动

外墙、楼板和屋面从当前体量与楼层求解，门窗从真实墙宿主和立面槽位定位。贯通核心筒、交通和通高构件需要核对其经过的每层轮廓，不能只参考首层包络。修改体量或层高时，应重新核对立面开口、屋面与附属件；不能保留旧宿主坐标来冒充完整修订。最终以当前编译产物与审核投影为准，设计说明不是几何完成证据。
