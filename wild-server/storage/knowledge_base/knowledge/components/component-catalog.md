---
doc_type: index
knowledge_role: navigation
doc_scope: index
knowledge_layer: navigation
entity_type: index
entity_name: component_catalog
topic: navigation
status: supported
authority: engine
primary_terms: [构件参考目录]
synonyms: [component_catalog]
---

# 构件参考目录

由 scripts/kb/update_component_catalog.py 从构件注册表及知识小节元数据生成。
修改示例后重新生成此文件；运行时提示词读取同一批元数据，目录不占用构件 RAG 的 top_k。

构件参考目录（非白名单）：用于统一命名和查找已有资料；目录外的新构件仍可设计和实现。
已有示例是实现起点，形态、尺寸和材料由当前图纸决定；experimental 示例需要核对能力限制。
- ac_position=空调机位：balcony-equipment-examples.md (experimental)
- arched_door=拱形门：tangent-arc-colonnade.md (experimental)；适用：拱门, 拱窗, 拱圈, 柱头垫块, 古典檐部, 踏步台基, 双坡屋顶
- arched_window=拱形窗：tangent-arc-colonnade.md (experimental)、window-variants.md (supported)；适用：拱形窗, 百叶窗, 多扇组合窗, 上亮窗, 圆形窗、拱门, 拱窗, 拱圈, 柱头垫块, 古典檐部, 踏步台基, 双坡屋顶
- assembly=组合构件：流程条目
- balcony=阳台：原生协议；无专用形态示例
- balcony_panel=阳台栏板：balcony-equipment-examples.md (experimental)
- bay_window=凸窗：glazing-detail-examples.md (experimental)
- beam=梁：原生协议；无专用形态示例
- bed=床：furniture-layout-examples.md (experimental)
- body=简化人物：原生协议；无专用形态示例
- bookshelf=书架：furniture-layout-examples.md (experimental)
- building_body=建筑主体：envelope-detail-examples.md (experimental)
- canopy=雨棚：原生协议；无专用形态示例
- chimney=烟囱：原生协议；无专用形态示例
- chinese_lattice_door=中式隔扇门：chinese-lattice-openings.md (supported)；适用：中式格棂门窗, 仿古门窗, 隔扇门, 回纹棂格, 套方纹棂格
- chinese_lattice_window=中式格棂窗：chinese-lattice-openings.md (supported)；适用：中式格棂门窗, 仿古门窗, 隔扇门, 回纹棂格, 套方纹棂格
- classical_entablature=古典檐部：tangent-arc-colonnade.md (experimental)；适用：拱门, 拱窗, 拱圈, 柱头垫块, 古典檐部, 踏步台基, 双坡屋顶
- coffee_table=茶几：furniture-layout-examples.md (experimental)
- colonnade=柱廊：tangent-arc-colonnade.md (experimental)；适用：柱廊, 开敞柱廊, colonnade, peristyle
- column=柱：原生协议；无专用形态示例
- combination_window=多扇组合窗：window-variants.md (supported)；适用：拱形窗, 百叶窗, 多扇组合窗, 上亮窗, 圆形窗
- cone_roof_system=圆台锥坡：cone-roof-system.md (experimental)；适用：圆形殿宇, 圆形攒尖顶, 重檐, 圆台基, 环形栏杆
- cornice=檐口：原生协议；无专用形态示例
- decorative_cornice=装饰檐口：roof-facade-detail-examples.md (experimental)
- decorative_pilaster=装饰壁柱：roof-facade-detail-examples.md (experimental)
- desk_chair=书桌椅：furniture-layout-examples.md (experimental)
- dining_table_chairs=餐桌椅：furniture-layout-examples.md (experimental)
- door=门：entrance-door-examples.md (experimental)
- double_height_window=通高窗：glazing-detail-examples.md (experimental)
- downlight=筒灯：light.md (supported)
- dual_pitch_two_slope=两斜板法：dual-pitch-two-slope.md (experimental)；适用：双坡屋顶, 坡屋顶
- eave_soffit=屋檐下悬：roof-facade-detail-examples.md (experimental)
- elevator=电梯：原生协议；无专用形态示例
- entrance_vestibule=主入口门斗：entrance-door-examples.md (experimental)
- equipment_platform=设备平台：balcony-equipment-examples.md (experimental)
- exhaust_outlet=排风口：ventilation-detail-examples.md (experimental)
- fixed_glazing=固定玻璃：glazing-detail-examples.md (experimental)
- floor=楼板：原生协议；无专用形态示例
- floor_lamp=落地灯：light.md (supported)
- floor_window=落地窗：glazing-detail-examples.md (experimental)
- floor_window_group=落地窗组：glazing-detail-examples.md (experimental)
- framed_awning=雨棚构造：roof-facade-detail-examples.md (experimental)
- furniture=家具：原生协议；无专用形态示例
- gable_dormer=老虎窗：roof-facade-detail-examples.md (experimental)
- gable_roof=双坡屋顶：tangent-arc-colonnade.md (experimental)；适用：拱门, 拱窗, 拱圈, 柱头垫块, 古典檐部, 踏步台基, 双坡屋顶
- garden_bench=园林坐凳：pavilion-garden-structure.md (supported)；适用：亭子, 凉亭, 水榭, 园林建筑, 景观亭
- garden_gate=庭院门：entrance-door-examples.md (experimental)
- garden_wall_junction=庭院围墙接口：envelope-detail-examples.md (experimental)
- glass_sliding_door=大面积玻璃移门：entrance-door-examples.md (experimental)
- high_window=高窗：glazing-detail-examples.md (experimental)
- hip_roof=四坡屋顶：pavilion-garden-structure.md (supported)；适用：亭子, 凉亭, 水榭, 园林建筑, 景观亭
- kitchen_cabinet=橱柜：kitchen-sanitary-examples.md (experimental)
- landscape_low_wall=景观矮墙：envelope-detail-examples.md (experimental)
- light=灯具：原生协议；无专用形态示例
- linear_light=线性灯：light.md (supported)
- louvered_window=百叶窗：window-variants.md (supported)；适用：拱形窗, 百叶窗, 多扇组合窗, 上亮窗, 圆形窗
- massing_composition_rules=体量组织：massing-composition-rules.md (supported)
- nightstand=床头柜：furniture-layout-examples.md (experimental)
- operable_sash=开启扇：glazing-detail-examples.md (experimental)
- ornamental_iron_railing=铁艺栏杆：balcony-equipment-examples.md (experimental)
- parapet=女儿墙：roof-facade-detail-examples.md (experimental)
- pediment=山花：tangent-arc-colonnade.md (experimental)；适用：拱门, 拱窗, 拱圈, 柱头垫块, 古典檐部, 踏步台基, 双坡屋顶
- pendant_light=吊灯：light.md (supported)
- primitive=通用几何体：原生协议；无专用形态示例
- railing=栏杆：原生协议；无专用形态示例
- ramp=坡道：原生协议；无专用形态示例
- roman_column=罗马柱：roof-facade-detail-examples.md (experimental)、tangent-arc-colonnade.md (experimental)；适用：拱门, 拱窗, 拱圈, 柱头垫块, 古典檐部, 踏步台基, 双坡屋顶
- roof=屋顶：roof-facade-detail-examples.md (experimental)
- roof_finial=宝顶：pavilion-garden-structure.md (supported)；适用：亭子, 凉亭, 水榭, 园林建筑, 景观亭
- sectional_garage_door=车库门：entrance-door-examples.md (experimental)
- shaft_opening_five_panel=井道留洞：shaft-opening-five-panel.md (experimental)；适用：高层, 标准层, 电梯井, 楼梯间, 塔楼
- shed_roof=单坡屋顶：roof-facade-detail-examples.md (experimental)
- side_door=侧门：entrance-door-examples.md (experimental)
- small_window=小窗：glazing-detail-examples.md (experimental)
- sofa=沙发：furniture-layout-examples.md (experimental)
- sofa_furniture=沙发：sofa.md (supported)；适用：沙发, 三人沙发, 双人沙发, 组合沙发
- sofa_primitive=组合沙发：sofa.md (supported)；适用：沙发, 三人沙发, 双人沙发, 组合沙发
- solid_base=实墙基座：envelope-detail-examples.md (experimental)
- solid_wall=实墙：envelope-detail-examples.md (experimental)
- spherical_shell_massing=球幕骨架：spherical-shell-massing.md (experimental)；适用：球体建筑, 球形幕墙, 电视塔, 斜撑
- stair=楼梯：stair.md (supported)；适用：楼梯, staircase
- stepped_plinth=踏步台基：tangent-arc-colonnade.md (experimental)；适用：拱门, 拱窗, 拱圈, 柱头垫块, 古典檐部, 踏步台基, 双坡屋顶
- stone_stool=石凳：pavilion-garden-structure.md (supported)；适用：亭子, 凉亭, 水榭, 园林建筑, 景观亭
- stone_table=圆石桌：pavilion-garden-structure.md (supported)；适用：亭子, 凉亭, 水榭, 园林建筑, 景观亭
- storage_door=储藏间门：entrance-door-examples.md (experimental)
- terrace_railing=露台栏杆：balcony-equipment-examples.md (experimental)
- tiered_eaves_pagoda=叠涩檐：tiered-eaves-pagoda.md (experimental)；适用：叠涩檐, 叠檐, 多层塔, 砖塔
- toilet=马桶：kitchen-sanitary-examples.md (experimental)
- tv_cabinet=电视柜：furniture-layout-examples.md (experimental)
- ventilation_louvre=通风百叶：ventilation-detail-examples.md (experimental)
- wall=墙体：原生协议；无专用形态示例
- wardrobe=衣柜：furniture-layout-examples.md (experimental)
- washbasin=洗手盆：kitchen-sanitary-examples.md (experimental)
- window=窗：window-variants.md (supported)
