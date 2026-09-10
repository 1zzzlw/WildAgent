# 知识声明到 DesignDocument 的映射

## 声明清单

每条候选内容先转换成以下记录，再决定是否进入活动知识库：

```yaml
claim_id: envelope.curtain-wall.floor-grid-alignment
claim: 幕墙水平分格与建筑楼层关系协调
classification: conditional
applies_when: /decisions/envelope/system == curtain_wall
schema_targets:
  - /decisions/envelope/curtain_wall/grid_strategy
  - /decisions/facades
enforcement:
  - planner
  - resolver
  - validator
source:
  location: 原始资料位置或 URL
  status: verified
free_variables:
  - bay width
  - panel proportion
  - facade rhythm
disposition: relation
```

## 分类与落点

| 分类 | 活动知识库 | DesignDocument | 程序执行 |
|---|---|---|---|
| engine_hard | 可以解释 | 必须有字段或边界 | Schema/compiler/validator 至少一处 |
| conditional | 仅在条件命中时 | 记录选中的系统与参数 | resolver 或 validator |
| preference | 可作为方案参考 | 只记录本次确实选择的值 | 候选生成或评分 |
| reference | 不进入 generation scope | 不写入硬约束 | 无 |
| unsupported | proposed 或隔离区 | 可记能力缺口 | 禁止伪编译 |

## 硬规则完成标准

一条规则只有同时满足以下条件才可以标为已实施：

1. 有稳定 `claim_id` 和适用条件；
2. 有来源或明确标为项目内部引擎事实；
3. 能映射到 DesignDocument 字段；
4. 至少有一个实际执行位置；
5. 有命中和不命中的回归；
6. 保留没有被这条规则决定的自由变量。

提示词中的“必须”“禁止”不构成执行证明。

## Schema 变更边界

若知识声明无法映射到现有字段，先判断当前产品是否真的支持该对象。支持时再提出 Schema 变更，并同时处理：

- `schema_version`；
- Pydantic 类型与 JSON Schema；
- 前端 TypeScript 类型和审阅界面；
- DesignPatch 路径与锁定语义；
- resolver/compiler/validator；
- 历史版本迁移。

当前产品不表达的地基计算、设备系统和法规数值不能为了“知识完整”塞入自由字典。
