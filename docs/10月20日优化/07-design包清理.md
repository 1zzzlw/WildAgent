# design 包清理

上次改了新设计路径，但为了保留旧链路，留下了大量旧代码。这次按用户要求删除旧设计体系，不再保留兼容入口。

`app/design` 从 22 个 Python 文件缩减为 3 个：

| 文件 | 保留原因 |
| --- | --- |
| [facts.py](../../wild-server/app/design/facts.py) | 唯一的新版图纸字段定义，模型生成与类型校验使用 |
| [resolve_facts.py](../../wild-server/app/design/resolve_facts.py) | 新图纸引用、参数校验和确定性计算 |
| [__init__.py](../../wild-server/app/design/__init__.py) | 只导出 `DesignFacts`、`resolve_facts` |

删除了 19 个旧模块、约 5,900 行旧源码。删除内容包括：

- 旧字段体系及管理外壳：`base / legacy_architecture / contracts / materials / objects`。
- 旧图纸归一化、解析和存储：`normalization / resolver / repository`。
- 旧立面 token、构件标记与编译：`facades / openings / markers / compilation`。
- 旧坐标、几何关系和空间校验：`coordinates / relations / spatial_review`。
- 旧完整性、履约、审核和预览：`completeness / fulfillment / review_outcome / preview`。

这些模块曾被旧生成链使用，并非全是原来就没有调用者的死代码。删除依据是当前已经选择用新版 DesignFacts 重构；本轮只保留新设计节点需要的实现，不再为旧链路保留一套并行协议。新校验器也不声称完整替代旧几何和空间检查的所有能力。

连带修改只有 architecture 的包入口和 profile 导入：

- 包初始化不再提前加载旧立面、归一化和骨架实现，避免导入新版设计节点时先触发已删除的旧协议。
- `profile.py` 移除对已删除 `design.openings` 的依赖，保留其原有的四种需求解析标签；粒度说明和意图节点使用的函数未改行为。

后续旧节点、API、编译和旧协议测试没有迁移；它们可能仍引用已删除模块，整条旧链路不能当成已经可运行。测试时先针对新版 architecture 输出。按用户要求，本轮没有执行测试、构建、服务启动或模型调用。

由于工作区中部分旧文件尚未提交到 Git，删除前已保存[源码压缩快照](设计包清理证据/清理前-design.zip)。这只是文档目录中的历史证据，不作为运行代码或兼容实现加载。

完整删除清单、指纹、连带改动及使用记录见[设计包清理证据](设计包清理证据/README.md)。
