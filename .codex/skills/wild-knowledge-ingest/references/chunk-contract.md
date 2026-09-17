# 真实分片契约

Skill 负责实体、自包含内容、证据及用途；MarkdownChunker 负责标题解析、metadata 继承、原子代码/表格保护及长度兜底。

H1～H5 是真实分片标题；每块以知识路径补足上下文。JSON 与对应字段解释保持在一个可理解单元中。不要为了整栋案例增大 chunk_size；长实体应拆独立业务主题。普通文本默认 900 字符、overlap 150，代码块不切断。多 part 会补邻片，但不能依赖补邻片修复文档语义。

专用系统规则以 applies_to 限定适用范围，每片保留实体名称、触发条件与必要关系。建筑类型卡和 identity role 不进入 generation scope。策略、完整案例和回退不能与生成规则混在同一个块。

## 分片级 metadata（`<!-- rag-meta -->`）—— 构件级过滤只能靠它

`config.yaml` 的 `mapping_rules` 只能给**整个目录**派生一套 metadata。当一份文档里包含**多个不同实体**
（例如 `component-parameters.md` 里并列讲 wall / roof / window / door），只有分片级 rag-meta 才能让每片
带上自己的 `entity_type`：

```md
## 墙体构件

<!-- rag-meta
entity_type: wall
entity_name: wall_family
topic: parameters
-->

... 本片正文 ...
```

机制：`app/spec/loader.py:615-679` 会把 `<!-- rag-meta -->` 注释**移除**并绑定到它出现的**标题路径**上；
`loader.py:555-558` 把该声明递归叠加到分片 metadata。**优先级：`defaults` → `mapping_rules` → 文件 frontmatter
→ 分片 rag-meta（最高）**。同层更深的标题覆盖祖先声明。

🔴 **v2 目前一个 rag-meta 都没写**（v1 的 `components/*.md` 是逐节写的）。
后果很实：`app/services/agent_service.py` 的生成期查询里有 6 条按构件查询
（`entity_type` = `structural_component` / `wall` / `window` / `door` / `railing` / `roof`），
v2 全部命中 0 —— 因为 v2 的 `entity_type` 只有 `component` 和 `engine_capability_boundaries`。
另有一条 `entity_name: component_selection_conditions` 的 recipe 查询，v2 里也没有对应文档。
**补内容时优先检查这两处：它们决定"按构件检索"是否还能工作。**

顺带一提：`loader.py:788-837` 的 `_infer_document_metadata` 会按**文件名**猜 `entity_type`
（`walls.md` → `wall`）。v1 的文件名恰好命中，所以即使没写 frontmatter 也能被检索到；
v2 的文件名是 `component-parameters.md` 这类通用名，**猜不出构件类型**，所以必须显式写 rag-meta。

任何新版文档必须用项目真实 MarkdownChunker 预览，核对 role、scope、revision、applies_to 是否继承。检查空壳、脱离宿主的片段、超长原子块和重复内容。环境失败时报告阻断，不能用手工估算分片数替代。

来源覆盖在摘要前完成。来源未提供的空间系统不按模板补写；旧参数和无效字段进入有原因的处置记录，不静默丢失。
