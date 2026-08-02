# 阶段八：RAG 与几何固定评测总结

## 阶段目标

把“门窗栏杆是否能被正确检索、生成和编译”从人工印象变成可重复运行的固定评测，防止后续修改知识库、metadata、提示词或编译器时悄悄破坏组合构件链路。

## 几何评测集

新增 `wild-web/scripts/fixtures/component-geometry-eval-cases.json`，当前包含 6 个固定用例：

- 正墙静态门。
- 侧墙带横竖窗棂的窗。
- 带高差的斜向路径栏杆。
- 父墙不存在的门。
- 超出父墙范围的窗。
- 含重复路径点的栏杆。

`npm run eval:components` 使用真实 TypeScript 编译器、Schema、renderer adapter、ScenePatch 和 Store 运行这些用例，同时继续检查来源映射、源数据不变、ID 唯一、错误隔离、撤销与重做。

## RAG 评测集

新增 `wild-server/evals/component_rag_cases.json` 和 `scripts/evaluate_component_rag.py`。当前 5 个固定查询分别验证：

- 基础静态门的 `geometry.components`、`parentWall` 和 `leafMaterial`。
- 基础静态窗的窗棂与玻璃材质字段。
- 路径栏杆的 `path`、`postSpacing` 和 `railLevels`。
- 门、窗、栏杆与 `geometry.elements` 的引擎能力边界。
- 建筑组装 recipe 是否包含组合构件规则。

每个用例同时检查 metadata 过滤、预期来源、必需关键词，以及正式检索中不能混入 `status=proposed` 或 `authority=inferred`。

## 评测发现并修复的问题

原 `doors.md`、`windows.md` 整体为 `status=proposed`。虽然正文已经说明基础静态门窗受支持，但默认 RAG 过滤仍会把整份文件排除，导致 Agent 发出门窗专项查询后无法得到可执行门窗知识。

本阶段没有把整份领域资料错误升级为 supported，而是按状态拆分：

- `doors-supported.md`：只保存当前引擎支持的基础静态门契约。
- `windows-supported.md`：只保存当前引擎支持的基础静态窗契约。
- `doors.md`、`windows.md`：继续保存未来门型、窗型和开启机制提案。
- `railings.md`：新增当前受支持的显式路径栏杆契约。

这样，默认正式生成能够召回基础可执行语法，而高级 `leafCount`、`sashType`、独立 `mullion` 等提案仍被 metadata 排除。

## 建筑生成检索路由

建筑生成从七类查询扩充为八类，在门窗之外增加独立栏杆意图：

```text
栏杆构件参数与路径规则：
railing、path、postSpacing、railLevels、楼梯与阳台栏杆
```

该查询使用 `doc_type=component, entity_type=railing` 过滤，避免栏杆知识只能偶然从大型建筑矩阵中命中。

## 验证结果

| 验证项 | 结果 |
|---|---|
| 固定几何评测 | 6/6 通过 |
| 固定 RAG 检索评测 | 5/5 通过 |
| 临时评测索引 | 349 个真实 chunk |
| 门窗栏杆目标文档预览 | 81 个 chunk，0 个 error |
| 默认检索污染检查 | 未召回 proposed/inferred |

最终服务器知识索引已由 Loader 增量同步为 `total=349, updated=57, deleted=2`；删除项来自门窗 supported 内容从 proposed 长文中拆出后产生的旧 chunk ID，不是删除源知识文件。

RAG 评测使用项目真实 `MarkdownChunker`、metadata 过滤和 Chroma，但 embedding 使用无外部依赖的 `HashEmbeddingFunction`。它适合回归扫描、分片和关键词路由；线上 embedding 的纯语义排序仍需在部署环境另行观察，不能由本地 hash 分数代替。

## 阶段结论

第一批组合构件现在同时具备代码级和知识级回归门槛。以后调整 RAG 文档或组件编译器时，可以先运行两套固定评测，再决定是否允许进入主分支或知识库索引。
