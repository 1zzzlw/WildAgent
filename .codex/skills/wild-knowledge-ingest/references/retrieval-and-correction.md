# 检索与纠错边界

## 查询计划

查询必须保留用户原句，并只按当前阶段选择可执行知识：

```json
{
  "raw_query": "生成一个带玻璃幕墙的办公楼",
  "intent": "building_generation",
  "topics": ["capability", "assembly", "constraints"],
  "filters": {"doc_type": "recipe", "entity_type": "facade"},
  "selected_systems": ["curtain_wall"]
}
```

建筑用途和风格不作为 RAG 文档实体。模型先形成 `DesignDocument`；后续查询只能根据用户原句、已批准系统和实际构件扩展，不得新增建筑套餐。

## 检索分组

1. 方案阶段加载基础协议、通用组装关系和引擎边界。
2. 骨架阶段根据批准体量、楼层、结构和屋顶系统检索关系。
3. 组件阶段按真实 `entity_type` 检索门、窗、栏杆等能力。
4. 专用系统规则必须通过 `applies_to` 检查；建筑类型、风格和近似语义不能替代显式选择。
5. 普通生成只允许 rules-v3 的 protocol、capability、relation；当前活动索引不保存无消费者的 reference 策略。

## 重排与追踪

重排优先级为 schema/engine、verified、maintainer、domain_reference、inferred。按正文哈希去重，并记录查询、过滤条件、命中 source/heading、距离、用途和最终注入字符数。类型文档命中普通生成应视为配置错误，而不是可接受的低相关结果。

## 有界纠错

```text
Draft
  → Structure Check
  → Tool/Schema Check
  → Relation Check
  → Final Validation
```

- Structure Check 检查 JSON、字段和阶段输出边界。
- Tool/Schema Check 使用仓库现有确定性校验器，不让模型凭知识文本修改合法枚举。
- Relation Check 检查 parent、标高、覆盖、入口可达和碰撞。
- 每次只修复失败实体及相关关系，然后重跑受影响检查和最终校验。

检索解决“当前引擎规则能否被找到”，纠错解决“生成结果是否兑现批准设计”。两者都不能用建筑百科、整栋模板或无限重试替代。
