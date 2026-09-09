---
doc_scope: reference
entity_type: assembly
entity_name: style_selection_reference
topic: definition
knowledge_role: strategy
status: supported
authority: maintainer
source: recipes/door-window-roof-style-reference.md
primary_terms:
  - 风格组合
  - 门窗屋顶选型
synonyms: []
---

# 门窗与屋顶的可选风格策略

## 使用条件与自由变量

本文是参考策略，普通生成不召回。明确进行风格比较时，可以比较门窗比例、开合关系、屋盖轮廓与材质角色的协调；不把风格名映射成唯一屋顶枚举或固定颜色。用户选择后，方案记录具体决定，下游仅加载所需构件能力与关系。

## 构件协调

选定窗型时结合墙面轴网和宿主范围；选定门型时结合入口功能；选定屋顶时结合体量和支点。对称、非对称、连续窗带、独立窗、平顶和坡顶都是可替换方案。引擎支持与审美偏好分开，字段和枚举依据 components/ 与完整规范。
