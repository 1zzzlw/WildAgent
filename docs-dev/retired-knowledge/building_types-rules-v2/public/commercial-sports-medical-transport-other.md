---
entity_name: commercial_sports_medical_transport_other
topic: composition
status: supported
authority: maintainer
source: building_types/public/commercial-sports-medical-transport-other.md
building_category: public
primary_terms:
  - 商业、体育、医疗、交通与园林
synonyms: []
applies_to:
  - 商业、体育、医疗、交通与园林
---

# 商业、体育、医疗、交通与园林：类型特征与条件关系

> 来源：本文件旧版资料的语义审查；旧稿逐节保存在 docs-dev/knowledge-before-rules-v2。仅保留有用的类型差异，示例尺寸、默认配色和整栋蓝图不参与生成。共性字段以 components/ 与 BLUEPRINT-SPEC-FULL.md 为准。

## 商业建筑

<!-- rag-meta
entity_type: building
entity_name: commercial
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 商业建筑
  - 商业综合体
  - 商场
  - 商铺
  - 购物中心
synonyms: []
applies_to:
  - 商业建筑
  - 商业综合体
  - 商场
  - 商铺
  - 购物中心
-->

- 适用条件：用户或已批准方案明确采用商业建筑；名称本身不决定全部构件。
- 类型特征：营业空间、顾客入口与服务动线的联系；橱窗、中庭和雨棚按需求选择。
- 条件关系：中庭采用真实留空楼板；商铺开口归属对应宿主；采光顶不得把 window 直接挂到 roof。
- WILD 映射与边界：采光顶用透明 roof/primitive；扶梯只有 stair/ramp 静态近似。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 体育建筑

<!-- rag-meta
entity_type: building
entity_name: sports
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 体育建筑
  - 体育馆
  - 体育场
synonyms: []
applies_to:
  - 体育建筑
  - 体育馆
  - 体育场
-->

- 适用条件：用户或已批准方案明确采用体育建筑；名称本身不决定全部构件。
- 类型特征：运动场地与观众、服务空间的联系；选择无柱比赛区时支撑避让该区域。
- 条件关系：屋盖支撑与场地净空协调；看台、交通和罩棚依本次平剖面衔接。
- WILD 映射与边界：beam/primitive 表达桁架外观；roof 只用已支持枚举，不能写 arch 或 truss。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 医疗建筑

<!-- rag-meta
entity_type: building
entity_name: medical
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 医疗建筑
  - 医院
  - 诊所
synonyms: []
applies_to:
  - 医疗建筑
  - 医院
  - 诊所
-->

- 适用条件：用户或已批准方案明确采用医疗建筑；名称本身不决定全部构件。
- 类型特征：患者、工作人员、服务空间的功能联系；专科空间和流线按任务指定。
- 条件关系：已指定的分流不能被通用走廊替代；通道和门的尺寸由本次功能输入确定。
- WILD 映射与边界：wall/floor/door/window/stair/ramp 表达几何；不以墙厚或门材质宣称防辐射、气密或无障碍合规。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 交通建筑

<!-- rag-meta
entity_type: building
entity_name: transport
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 交通建筑
  - 车站
  - 客运站
synonyms: []
applies_to:
  - 交通建筑
  - 车站
  - 客运站
-->

- 适用条件：用户或已批准方案明确采用交通建筑；名称本身不决定全部构件。
- 类型特征：候乘空间、到发通道和交通设施之间的联系。
- 条件关系：选择通高大厅时避免整层楼板截断；雨棚与站台、入口和支撑匹配；区分旅客与服务动线。
- WILD 映射与边界：stair/ramp 近似交通设施，beam/primitive 近似大跨；不生成未经支持的轨道、扶梯或专业设备字段。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。

## 园林建筑

<!-- rag-meta
entity_type: building
entity_name: garden
topic: composition
knowledge_role: identity
authority: domain_reference
primary_terms:
  - 园林建筑
  - 园亭
  - 园林廊架
  - 水榭
synonyms: []
applies_to:
  - 园林建筑
  - 园亭
  - 园林廊架
  - 水榭
-->

- 适用条件：用户或已批准方案明确采用园林建筑；名称本身不决定全部构件。
- 类型特征：亭、廊、榭各自保留遮蔽、连接或临水空间角色。
- 条件关系：开放柱廊不强制四面墙；选定临水平台后安排支撑与边缘关系；框景洞口允许没有玻璃。
- WILD 映射与边界：column/beam/roof/floor 与 opening 表达关系；栏杆不是座椅，水面几何不是水体模拟。
- 自由变量：层数、体量轮廓、开间、屋顶形式与材质由本次需求和方案确定。
