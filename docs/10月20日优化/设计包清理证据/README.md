# design 包清理证据

按用户最新授权删除旧 design 体系，不为后续旧节点保留兼容层；本轮不运行测试。

保留：facts.py（字段）、resolve_facts.py（校验及确定性推导）、__init__.py（公开入口）。

删除：19 个模块；从 22 个 Python 源文件缩减为 3 个，包内源码从 6283 行缩减到 380 行。目录清单与源码指纹仅用于核对删除范围，不代表运行验证。

## 使用了什么

- 上一轮新版 DesignFacts、resolve_facts、architecture_planner、设计起草函数与提示词。
- 对 app/design 的文件列表、导入关系、类与函数定义名进行检索；读取包入口、旧开口 token 和新字段/计算入口，判定哪些服务新协议。
- 读取 architecture 包入口和 profile 的实际导入，核对 intent 对 resolve_complexity_profile 的引用；不迁移后续节点。
- 保留用户关于“只改设计图纸与 architecture、不测试”的范围；按后续明确授权删除旧依赖，不用兼容需求阻止清理。
- 参考项目 building-blueprint-diagnostics 技能的范围与证据原则；没有使用建筑案例坐标、在线资料或知识库检索。
- 使用本地 MEMORY.md 仅回顾脏工作区保留和避免案例规则累加，不把历史架构结论当成现状。

## 工具记录

- PowerShell/rg/Get-Content/git：文件定位、源码阅读、现有改动和删除范围查看。
- Compress-Archive/Copy-Item：在删除前保存所有 22 个 design 源文件及 architecture 两个连带入口的快照，保住尚未提交的旧文件。
- apply_patch：删除 19 个源码文件、精简 design 和 architecture 包入口、移除 profile 对已删模块的依赖、更新当前说明。
- Node REPL 的文件与哈希 API：保存删除前清单、删除原因、清理后目录、行数和 SHA-256。
- 删除 design/__pycache__ 的 PowerShell 命令被执行策略拦截，返回 blocked by policy；缓存目录暂留，没有通过其他工具重试删除。
- 未运行 pytest/unittest、应用导入、语法检查、构建、服务、真实模型或渲染。

## 文件说明

- 清理前-design.zip：删除前全部 design Python 源码的静态压缩快照，不是运行时旧代码目录。
- 清理前-architecture-init.py / 清理前-profile.py：连带入口修改前原文。
- 01-清理清单.json：删除前每个文件的保留/删除决定、行数和指纹。
- 02-清理结果.json：删除原因、新目录与源码指纹、连带修改和未验证边界。

旧节点和旧协议测试仍可能引用被删模块；这是本轮明确选择的重构边界，不把删除文件描述成已经完成全链路迁移，也不宣称旧检查能力已等价迁移。
