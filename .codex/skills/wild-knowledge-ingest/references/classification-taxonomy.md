# 知识分类与职责

| 路径 | doc_type | knowledge_role | 内容 |
|---|---|---|---|
| BLUEPRINT-SPEC-* | blueprint_spec | protocol | 字段、坐标、引用和最小生成协议 |
| components/ | component | capability | 单构件能力、参数、局部示例、受支持降级 |
| recipes/ | recipe | relation | 已选系统的组装、宿主、边界与条件关系 |
| README / 纯目录 | index | navigation | 导航，不进入生成 |

建筑用途和风格由模型理解，不在活动知识库建立类型卡。代码只保留与执行边界有关的粗粒度 profile，例如高层、大跨和地下交通；profile 负责 WILD 能力范围与确定性回退，不提供完整建筑方案。

完整场景案例和通用设计策略放扫描目录之外。若以后建立项目专有策略库，必须先提供结构化策略标识、显式路由节点和独立 reference 查询，再建立对应索引。回退策略由失败路径的确定性代码选择。运行配置如幕墙解析参数设 system scope，字段不得随语义摘要丢失。

同一语义保留一份。专业系统只有在当前引擎存在独特映射时才进入 component/recipe；不同字段或能力版本不能无证据合并。
