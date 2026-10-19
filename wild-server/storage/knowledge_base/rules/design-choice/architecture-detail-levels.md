---
entity_name: architecture_detail_levels
topic: parameters
status: supported
authority: maintainer
primary_terms: [建筑设计粒度交付]
synonyms: []
---

# 建筑设计粒度交付标准

依据当前 DETAIL_LEVEL_GUIDANCE。每次只检索 State 选定的档位，完整 JSON 字段格式由 architecture 输出契约提供。各档只定义交付深度；建筑类型、风格、层数、体量、屋型、尺寸与配色由用户需求和本次设计决定。

## 低粒度 minimal

<!-- rag-meta
entity_name: architecture_detail_minimal
primary_terms: [低粒度设计交付]
synonyms: []
-->

适用：State.detail_level=minimal。用户明确需求优先；本档不固定建筑形态、层数、尺寸、材料或构件数量。

交付范围：完成建筑主体、实际围护或开敞面、必要门窗、屋面、基本交通和基础照明。多层建筑落实所需楼梯，已选结构保留必要承接关系。

允许省略：未明确要求的 floor_layouts、精细室内隔墙、家具陈设及装饰细部。功能意图可简述，无需逐房间穷举坐标。

表达重点：massing、volumes、facades 和 roof 说明主体及归属；必要构件在 components 中给出尺寸、位置与适用的宿主。

完成条件：主体、必需功能与已选系统已落实，字段、引用和位置一致即可交付。可选细部未安排不要求继续简化；不得为了降低难度删掉用户要求的附体、特殊屋型或必要构件。契约错误按实际问题修订。

## 中粒度 simple

<!-- rag-meta
entity_name: architecture_detail_simple
primary_terms: [中粒度设计交付]
synonyms: []
-->

适用：State.detail_level=simple。用户明确需求优先；本档不固定建筑形态、层数、尺寸、材料或构件数量。

交付范围：完成主体、围护、必要门窗、屋面、交通与照明，完善基本立面与材质层次。按功能和风格选择适用的入口、阳台、露台、雨棚或栏杆，无需全部配置。

允许省略：未明确要求的完整室内分区、家具陈设、大量装饰与复杂构造节点。

表达重点：选中的附属实体写入 components，给出尺寸、位置、宿主及具体材料意图，说明与主体的连接关系。

完成条件：基础建筑与选中的附属构件、基本材质表达完整且相互一致即可交付。未选择的可选构件不影响完成，不以反复改尺寸、删附体或增加门窗数量代替设计深化。

## 高粒度 standard

<!-- rag-meta
entity_name: architecture_detail_standard
primary_terms: [高粒度设计交付]
synonyms: []
-->

适用：State.detail_level=standard。用户明确需求优先；本档不固定建筑形态、层数、尺寸、材料或构件数量。

交付范围：完成主体、围护、必要门窗、屋面、交通、照明及适用的附属构件，深化已选的开口分格、檐口、屋面衔接和材料分层等外观与构造细节。

允许省略：未明确要求的全套室内家具、完整室内装修及与本次形制无关的装饰。

表达重点：细节写为具体参数或可定位的 components，明确尺寸、宿主、相接标高及材料意图；仅在 concept 或说明中命名不算落实。

完成条件：所选外观与构造细节已落实，构件承接、尺度与材料相互一致即可交付。无需穷举所有候选装饰，不通过增加层数、体量或重复构件表示高粒度；矛盾按相关字段和关系定向修订。

## 极高粒度 detailed

<!-- rag-meta
entity_name: architecture_detail_detailed
primary_terms: [极高粒度设计交付]
synonyms: []
-->

适用：State.detail_level=detailed。用户明确需求优先；本档不固定建筑形态、层数、尺寸、材料或构件数量。

交付范围：完成主体、围护、门窗、屋面、交通及外观构造细节；按建筑用途安排室内功能分区、通行空间、家具陈设和设施，并落实室内外照明与需求涉及的入口、场地细节。

允许省略：本次建筑用途不需要的房间、设施和装饰。房间种类与家具清单由功能决定，无需套用住宅配置或固定构件数量。

表达重点：室内分区通过 floor_layouts 表达，独立内墙、通行开口与房间范围一致；家具逐件或按组合写入 components，给出位置、尺寸、造型与材料意图。

完成条件：所需功能空间、通行开口、家具设施与室内外细节已落实，墙、门、家具之间的布局与引用一致即可交付。缺少已选内容时补齐实际缺项，局部错误定向修订，不整体退回较低粒度。
