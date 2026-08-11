---
doc_type: pattern
doc_scope: generation
knowledge_layer: project_pattern
entity_type: building
entity_name: high_detail_architecture_generation
topic: assembly
wild_version: "1.1"
status: supported
authority: maintainer
source: patterns/high-detail-architecture-generation.md
keywords:
  - 高细节建筑
  - 复杂建筑
  - 组合体量
  - 退台
  - 结构轴网
  - 立面层次
  - high detail architecture
---

# 高细节建筑生成模式

> 来源：WildAgent 精密生成流程的项目级约束。
> 用途：把“复杂、丰富、有层次”等意图转换为可验证的体量、结构和细部目标。
> 注意：`volumes`、`structural_grid`、`detail_packages` 是 Agent 规划协议，不是 WILD Blueprint 字段；最终必须编译为引擎支持的元素与组件。

## 精密模式复杂度编译

<!-- rag-meta
entity_type: building
entity_name: precision_complexity_compilation
topic: assembly
status: supported
authority: maintainer
keywords: 精密模式, 高复杂度, 组合体量, 结构轴网, 细部构件包
-->

高细节方案至少应同时满足三类目标：两个可识别的主次体量或退台体量；一套与跨距相符的结构轴网；三个有功能关系的细部构件包。体量必须落实为独立闭合的 floor 与 wall，框架或混合体系应落实为 column 与 beam。细部构件从 canopy、balcony、bay_window、cornice、railing、ramp、light、chimney 中按功能和风格选择，不以重复门窗数量代替复杂度。

若用户明确要求“简单、简易、单一体量、方盒子”，应降级为 simple，不自动补足多体量和细部构件。若模型骨架未达到规划层的体量轮廓数或结构元素目标，必须报告复杂度降级并重新生成或使用体量化安全回退，不能静默交付矩形盒子。

## 低层住宅高细节组合

<!-- rag-meta
entity_type: building
entity_name: detailed_lowrise_residential
topic: assembly
status: supported
authority: maintainer
keywords: 复杂别墅, 现代别墅, 多体量住宅, 退台住宅, 阳台, 雨棚, 凸窗
-->

两层及以上住宅优先采用“完整首层基座 + 缩进上层体量”，缩进应形成可用露台或主入口遮蔽；单层住宅可采用相接的主翼与侧翼形成 L 形轮廓。现代住宅优先组合 balcony、canopy、bay_window；欧式住宅优先组合 balcony、canopy、cornice；中式或新中式住宅优先组合 canopy、cornice、railing。阳台只在二层及以上使用，栏杆只用于真实高差边界。

柱梁用于解释退台、悬挑、门廊或真实跨距，不作为无功能装饰重复布置。立面层次应由体量前后关系、入口进深、檐口或阳台投影共同形成。

## 公共建筑高细节组合

<!-- rag-meta
entity_type: building
entity_name: detailed_public_building
topic: assembly
status: supported
authority: maintainer
keywords: 复杂公共建筑, 主次入口, 门厅体量, 结构网格, 无障碍坡道, 夜景照明
-->

普通公共建筑优先采用“主体功能体量 + 前置门厅或侧翼体量”，并用 frame 或 hybrid 轴网组织 column 与 beam。入口细部优先组合 canopy、ramp、light；存在真实平台或高差时再加入 railing。大跨公共建筑的复杂度主要来自主跨、附属服务体量和入口雨棚，不应复制住宅式阳台或密集凸窗。

公共建筑必须保留清晰主入口、无障碍到达和结构可读性。装饰线脚、灯具与雨棚只强化已经成立的体量转折，不能替代主体结构和交通关系。
