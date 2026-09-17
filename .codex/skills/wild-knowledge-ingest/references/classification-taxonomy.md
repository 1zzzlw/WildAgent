# 知识分类与职责

## v2 顶层两分（写作目标目录）

第一层按"这条内容是知识还是规则"二分，互斥判据：**「违反了能不能被机器判定」**。

| 路径 | doc_type | knowledge_role | 内容 | 对应检索 |
|---|---|---|---|---|
| `knowledge/protocol/*.md` | blueprint_spec | protocol | 顶层结构、字段、枚举、坐标系、引用格式、ScenePatch 协议 | 知识查询 |
| `knowledge/components/*.md` | component | capability | 单构件/组合构件的最小可用 JSON、可替换参数、能力边界 | 知识查询 |
| `rules/implementation/*.md` | recipe | relation | 无前提的参数与引用关系（如窗必须引用有效墙宿主） | 规则查询 |
| `rules/conditional/*.md` | recipe | relation | 选了 A 就必须落实 B 的跨构件触发规则 | 规则查询 |
| `rules/design-choice/*.md` | component | capability | 明确留给模型的自由变量（边界声明，不是约束） | 知识查询 |
| `README.md` / 目录内 README | index | navigation | 导航，靠 `config.yaml` 派生，不进生成 | 不检索 |

这 5 组过滤对**硬编码在代码里**（`app/agent/knowledge/policy.py:61-69`、
`app/agent/planning/workflow.py:60-65`、`app/services/agent_service.py:1185-1193`），
`config.yaml` 的 `mapping_rules` 负责让"目录 = 分类"生效。**改目录名或 metadata 会让查询直接查空。**

## 强制强度轴（用于判断落位，不是目录名）

| 强度 | 落点 | 判定 |
|---|---|---|
| `engine_hard` | `rules/implementation/` | 无前提成立，Schema/compiler/validator 至少一处执行 |
| `conditional` | `rules/conditional/` | 有 `applies_when` 触发条件，未选中不生效 |
| `preference` | `knowledge/components/`、`rules/design-choice/` | 只影响候选评分，不锁字段 |
| `reference` | 扫描目录之外 | 百科、案例、风格；无消费者 |
| `unsupported` | `docs-dev/knowledge-backlog/` | 能力缺口，禁止伪编译 |

🔴 「确定性关系」**不是第三个顶层分支**，它本身就是 `rules/` 这一支。
`rules/design-choice/` 严格说不是约束，是"这里不约束"的声明，不要往里塞真规则。

## 内容取舍

建筑用途和风格由模型理解，不在活动知识库建立类型卡。代码只保留与执行边界有关的粗粒度 profile
（`app/agent/generation/architecture/profile.py`）。完整场景案例、通用设计策略和失败回退放扫描目录之外；
回退策略由失败路径的确定性代码选择。运行配置（如幕墙解析参数）走 `system` scope，字段不得随语义摘要丢失。

**同一语义只保留一份。** 专业系统只有在当前引擎存在独特映射时才进 `knowledge/components` 或 `rules/`；
不同字段或能力版本不能无证据合并。不为每种建筑复制相同门窗规则。
