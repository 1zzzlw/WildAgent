# WildAgent 正式文档

这里仅保存与当前代码一致、需要持续维护的正式文档。历史方案、阶段总结、修复记录和已失效设计统一放在 [`docs-dev/`](../docs-dev/README.md)，不能作为当前实现依据。

最后核对：2026-08-25。

## 项目级文档

1. [架构说明](ARCHITECTURE.md)：项目边界、模块关系和真实数据流。
2. [开发与测试](DEVELOPMENT.md)：本地启动、配置和验证要求。
3. [测试文件使用指南](TESTING.md)：自动测试、专项评测、图展示和人工脚本的作用与命令。
4. [测试文件详细目录](TESTING_GUIDE.md)：逐个测试文件和命令的详细说明。
5. [服务器部署与运维](DEPLOYMENT.md)：Compose、环境文件位置、重建与故障核对。
6. [优化路线](ROADMAP.md)：跨模块的当前结论、已完成优化和后续优先级。

这些文件影响整个项目，因此保留在 `docs/` 根目录。

## 专题文档

| 目录 | 内容 | 推荐入口 |
|---|---|---|
| [`agent/`](agent/) | Agent 路由、计划审核、校验闭环、建筑平面规划、对话与事件协议 | [AI 对话工作区优化说明](agent/AI对话工作区优化说明.md)、[建筑生成计划模式与当前优化](agent/建筑生成计划模式与当前优化.md)、[建筑生成设计思路（入门版）](agent/BUILDING_GENERATION_DESIGN_GUIDE.md)、[Plan2Build 当前链路](agent/PLAN2BUILD_PIPELINE.md)、[建筑平面生成与确认](agent/FLOOR_PLAN_GENERATION_MVP.md)、[Agent 与 AI 对话设计](agent/AGENT_AND_CHAT.md) |
| [`rag/`](rag/) | 分片、Embedding、Chroma、检索、评测和演进规划 | [RAG 文档入口](rag/README.md) |
| [`specs/`](specs/) | `.wild` Blueprint 规范、字段和当前引擎能力目录 | [WILD Blueprint 当前版本规范](specs/WILD_BLUEPRINT_SPEC.md) |
| [`materials/`](materials/) | PBR、程序化材质、表面系统、`.wildmat` 与 `.wildlook` | [建筑表面系统总览](materials/ARCHITECTURAL_SURFACE_SYSTEM.md) |
| [`operations/`](operations/) | 具体部署与运维专题 | [HTTPS/SSL 配置](operations/HTTPS_SETUP.md) |
| [`tools/`](tools/) | 项目脚本和工具入口 | [工具目录](tools/README.md) |

## 事实来源优先级

出现冲突时按以下顺序判断：

1. 可运行代码、Schema 和自动化测试；
2. 本目录中的正式文档；
3. `wild-web/wild-lang/` 的 WILD 语言契约及源码旁的专项说明；
4. `agent.md`、`wild-web/CLAUDE.md` 等协作上下文；
5. `docs-dev/` 历史材料。

知识库内容位于 `wild-server/storage/knowledge_base/`，它是 Agent 的运行数据，不属于项目说明文档，因此继续与后端存储放在一起。

## 文档维护规则

- 当前能力与规划必须明确分开；跨模块规划写入 [优化路线](ROADMAP.md)，单一专题规划写入对应专题目录。
- 架构或协议变更必须同时更新对应正式文档。
- 临时分析、Bug 复盘、实施日志直接写入 `docs-dev/`。
- 每个主题只保留一个权威入口，避免“总结最终版”“最终修复版”并存。
