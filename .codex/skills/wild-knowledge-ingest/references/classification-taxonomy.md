# 知识分类与职责

| 路径 | doc_type | knowledge_role | 内容 |
|---|---|---|---|
| BLUEPRINT-SPEC-* | blueprint_spec | protocol | 字段、坐标、引用和最小生成协议 |
| components/ | component | capability | 单构件能力、参数、局部示例、受支持降级 |
| recipes/ | recipe | relation | 已选系统的组装、宿主、边界与条件关系 |
| building_types/ | building_type | identity | 按请求补充类型特征与 WILD 映射 |
| patterns/ | pattern | strategy | 可选设计策略与项目偏好，reference scope |
| README / 纯目录 | index | navigation | 导航，不进入生成 |

catalog 仅在有独立类型知识时参与生成；纯别名导航设 index。详细类型不需要完整配方或最少可行蓝图。多个建筑可共用规则，只有有价值的差异才单独维护。

完整场景案例放扫描目录之外；确有查询需求时设 reference scope 与 example role。回退策略仅在明确失败时使用，设 reference/fallback。运行配置如幕墙解析参数设 system scope，字段不得随语义摘要丢失。

同一语义保留一份，相关类型链接不代表 Loader 会追踪链接。类型卡仍须保留关键角色与关系摘要；不同字段或能力版本不能无证据合并。
