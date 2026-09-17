# 入库验收

- 字段、枚举、坐标和引用与当前源码相符；未实现能力不伪装为 supported。
- 用户需求、设计选择、引擎规则和领域资料的权威分开（`authority` 只取白名单里的值）。
- 来源声明有处置和目标，旧语法被拒绝时有效空间语义仍被保留或明确路由。
- 活动目录没有 building_type / pattern / 百科类 generation 文档；建筑分类只存在于执行
  profile（`app/agent/generation/architecture/profile.py`）或扫描目录之外的参考资料。
- 活动目录及 generation 分片没有 `status: proposed`；未实现内容位于 `docs-dev/knowledge-backlog/`。
- 共享规则没有在每个建筑重复；通用常识的保留有具体价值。
- 完整建筑案例、固定策略与回退不参与普通生成；局部 JSON 有有效前置条件。
- README/navigation 不参与生成；运行参数与模型参考用途分开。
- **两端 metadata 都对得上**：
  - `config.yaml` 的 `mapping_rules` 能让每个目录命中一组硬编码过滤对（跑 `check_kb.py` 确认非 0）；
  - 需要**构件级**过滤的内容（wall / window / door / railing / roof / structural_component …）
    已按分片写 `rag-meta`，否则 `agent_service._build_rag_queries` 的多条查询会静默返回 0 条；
  - `required_documents` 与实际 Markdown 双向一致，且**只列 `.md`**。
- 术语与别名不重叠；`primary_terms` / `synonyms` 都不为空时才写。
- 真实 chunk 预览（`preview_wild_rag_chunks.py`）无空壳、断裂或失去实体上下文的片段。
- 代码围栏分工正确：能被模型整段复制的示例用 ` ```json ` 且**严格合法**（无 `//`、`...`、尾逗号）；
  带注释/省略号的反例与教学示意用 ` ```jsonc `。放错会让 CI 红，或教模型写出非法 JSON。
- linter（`lint_wild_rag_docs.py`）的 `error` **必须清零**——`tests/rag/test_knowledge_rules_v3.py` 把它当门禁，
  Jenkins 会跑。`warning`（`redundant_path_metadata` / `short_section` / `empty_container_heading`）属内容 backlog，
  按真实问题处理。**`source` 已不是必需键，不要为了让脚本变绿编造 `source` 或改坏内容。**
- 代码消费者、查询过滤与覆盖判断只请求可执行知识；未知类型不触发建筑百科检索，也不回退到别的建筑模板。
- 回归覆盖：泛建筑请求、明确类型、否定风格、未知类型、已选方案系统、局部组件及旧版本向量隔离。
- 文档迁移后的检索评测以所需事实为答案，补充不应召回项；不以旧文件名命中掩盖语义错误。
- 索引由 Loader 同步，确认索引版本和状态；系统阻断和未跑的 LLM/渲染检查如实列出。
