# WildAgent RAG 文档

> 文档分类：RAG 专题。返回 [正式文档入口](../README.md)。

本目录只放与知识库分片、向量索引、在线检索、召回评测和 RAG 演进有关的正式文档。知识库正文仍位于 `wild-server/storage/knowledge_base/`，测试脚本仍位于 `wild-server/scripts/rag/`；这里保存的是设计和使用说明，不参与向量入库。

## 推荐阅读顺序

1. [RAG 能力与演进规划](RAG_CAPABILITIES_AND_EVOLUTION.md)：先区分当前已实现能力、部分能力和计划能力。
2. [RAGTrace 日志阅读指南](RAG_TRACE_GUIDE.md)：学习怎样按 request_id 阅读查询、过滤、chunk_id、距离、耗时和 Token。
3. [RAG 在线门控、权限、引用与质量控制手册](RAG_RUNTIME_CONTROLS.md)：配置 observe/enforce、权限、反馈、安全、Judge 和 CI。
4. [RAG 全链路研究说明书](RAG_PIPELINE_GUIDE.md)：理解当前分片、Embedding、Chroma、检索和 Agent 注入细节。
5. [RAG 与智能体优化路线图](RAG_AND_AGENT_OPTIMIZATION_ROADMAP.md)：早期方案参考，包含未实施设想，不能作为当前实现依据。
6. [RAG 测试脚本入门手册](../../wild-server/scripts/rag/README.md)：实际运行分片检查与召回率评测。

## 事实来源

当文档描述与代码不一致时，以以下顺序为准：

1. `wild-server/app/spec/loader.py` 的真实分片、同步和检索代码；
2. `wild-server/app/services/agent_service.py` 与 `wild-server/app/agent/nodes/` 的上下文注入代码；
3. `wild-server/tests/rag/` 的自动测试；
4. 本目录中的当前能力说明；
5. 早期优化路线中的方案和预测。

## 维护规则

- 已实现能力和规划能力必须明确分开；
- 召回率结论必须写明评测集、Embedding、索引模式、Top-K 和知识库版本；
- HashEmbedding 结果只能证明流程能运行，不能代表真实语义质量；
- 调整分片、Embedding、过滤或门控策略后，必须重新运行固定评测集；
- 不在 `docs/` 中保存一次性报告，运行报告继续写入 `wild-server/scripts/reports/`。
