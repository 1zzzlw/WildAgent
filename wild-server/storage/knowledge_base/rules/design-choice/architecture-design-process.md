---
entity_name: architecture_design_process
topic: parameters
status: supported
authority: maintainer
primary_terms: [建筑设计步骤与关系复核]
synonyms: []
---

# 建筑设计步骤与关系复核

## 设计步骤与字段落地

适用：architecture 起草与修订。提炼自《WILD蓝图书写流程》“建筑样式设计”及类型设计文档，按当前 DesignDocument 整理。方法不固定建筑类型、层数、尺寸、风格或配色；用户要求和选定粒度决定范围。

1. 需求与形制：明确用途、用户硬要求和本次设计特征；design_intent 只记录实际采用的目标、必要假设、空间与材料策略、已选系统。
2. 体量与标高：用levels、profiles和volumes.placement/geometry落实主次、退台、错动、曲线或放样体量。massing.width/depth控制真实体量总体包络；楼面、墙顶和屋面支承引用同一标高体系。
3. 功能与交通：circulation声明所需通行。floor_layouts.level引用楼面ID，rooms.region表达分区；内墙统一写walls。选用楼梯时在components声明占地、形式、floor_connections.from_level/to_level，上层留洞通过voids及slabs.holes落实。不因多层自动补楼梯。
4. 围护与开口：walls声明有向边界、标高和system，components声明门窗尺寸，host引用逻辑墙ID。程序将沿墙offset、标高引用与法向偏移转换为世界位置，不重新猜测四方向坐标。
5. 屋面与附属：roofs逐片声明宿主、支承、真实范围与屋型；选定门廊、露台、防护等在components落位并声明承接，不重复同一片屋面。
6. 材料与表达：落实材料和配色；design_intent.material_strategy 与构件 description/form 保持一致。构件内部零件与最终 WILD 几何留给后续实现。

## 交付前的关系复核

适用：architecture 起草后与局部修订后。依据类型文档的设计层自检方法，结合当前 contracts.py、coordinates.py、compilation.py 核对已有图纸；这是设计复核指引，不表示程序已实现全部空间、结构或专业规范检查。

- 意图与数据：已选特征须在profiles、volumes、walls、slabs、voids、roofs或components中落实；仅写“庭院、通高、幕墙”等名称不算落实。按粒度保留必要内容，不用继续简化替代修复。
- 体量与承接：核对总体包络、楼层范围、上下层和附体的支承。体量包络相交不等于实体碰撞；共用界面的围护与连通方式仍要明确，避免重复墙或无意封堵。
- 围护与开口：仅声明实际存在的墙；开敞边界不补整面墙。洞口位于宿主实际范围内，同墙开口不重叠，内墙端头避开洞口。历史facades只在输入适配中展开，新方案不输出pattern。
- 通行与楼梯：分隔处需要通行时声明门洞；主要通路可写circulation.clearance_paths的level、points、width/height，净宽高由本次设计选择。路径避开墙垛和家具，穿墙处有门洞；楼梯、平台和出口共用levels，净空和专业安全另行验收。
- 屋面与附属：roofs与components不重复同一片屋面。宿主、位置、尺寸及承接标高一致，材料角色与描述不冲突。
- 修订联动：生成后核对实际实体，再判断入口是否被占用、家具是否遮挡所选开口、楼梯和露台是否到达。修改体量、层高或宿主时复核依附件；仅修受影响关系，保留其他设计决定。数值可由程序计算，说明文字不能代替实际产物。
