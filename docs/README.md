# WildAgent 正式文档

这里仅保存与当前代码一致、需要持续维护的正式文档。历史方案、阶段总结、修复记录和已失效设计统一放在 [`docs-dev/`](../docs-dev/README.md)，不能作为当前实现依据。

最后核对：2026-08-11。

## 阅读顺序

1. [架构说明](ARCHITECTURE.md)：项目边界、模块关系和真实数据流。
2. [WILD Blueprint 当前版本规范](WILD_BLUEPRINT_SPEC.md)：`.wild` 结构、字段、坐标、组件、材质、校验和兼容边界。
3. [Agent 与 AI 对话设计](AGENT_AND_CHAT.md)：Agent 路由、校验闭环、Claude 风格执行过程和事件协议。
4. [开发与测试](DEVELOPMENT.md)：本地启动、配置和验证要求。
5. [测试文件使用指南](TESTING.md)：全部自动测试、专项评测、图展示和历史脚本的作用与命令。
6. [服务器部署与运维](DEPLOYMENT.md)：Compose、环境文件位置、重建与故障核对。
7. [优化路线](ROADMAP.md)：本轮结论、已完成优化和后续优先级。

## 事实来源优先级

出现冲突时按以下顺序判断：

1. 可运行代码、Schema 和自动化测试；
2. 本目录中的正式文档；
3. `wild-web/wild-lang/` 的 WILD 语言契约及源码旁的专项说明；
4. `agent.md`、`wild-web/CLAUDE.md` 等协作上下文；
5. `docs-dev/` 历史材料。

知识库内容位于 `wild-server/storage/knowledge_base/`，它是 Agent 的运行数据，不属于项目说明文档，因此继续与后端存储放在一起。

## 文档维护规则

- 只描述已经实现的能力；规划统一写入 [优化路线](ROADMAP.md)。
- 架构或协议变更必须同时更新对应正式文档。
- 临时分析、Bug 复盘、实施日志直接写入 `docs-dev/`。
- 每个主题只保留一个权威入口，避免“总结最终版”“最终修复版”并存。
