# WILD 规则知识库（rules-v2）

知识库负责说明当前引擎能表达什么、已选构件如何正确连接，以及特定类型有哪些值得保留的空间关系。用户需求和已批准方案决定建筑的具体形态。不能把精确尺寸改成一组未经依据的范围后，继续作为所有建筑的默认配方。

## 知识职责与召回用途

| knowledge_role | 内容 | 默认用途 |
|---|---|---|
| protocol | WILD 字段、坐标与引用契约 | 基础协议固定加载，完整协议按需检索 |
| capability | 当前实现、有效枚举、宿主与表达边界 | generation |
| relation | 已选择系统的条件组装关系 | generation |
| identity | 被点名类型的必要辨识特征与映射 | generation，并检查 applies_to |
| strategy / example / fallback | 可选设计策略、完整案例、失败回退参考 | reference，普通生成不召回 |
| navigation | 目录和分类导航 | index，不召回 |

规则描述条件，不指定结果。例如“选择阳台时需要有效宿主和通行关系”，不等于“别墅必须配置阳台”。窗宽、层高、色值等只在确有引擎范围或用户依据时成为约束；局部数值示例不构成建筑默认值。

公共默认 metadata 位于 [config.yaml](../../wild-server/storage/knowledge_base/config.yaml)，文档 frontmatter 和实体 rag-meta 可以覆盖。`knowledge_revision: rules-v2` 用于隔离旧内容，不是 embedding 模型版本。角色、scope、来源权威和实现 status 是不同维度。

## 当前内容组织

- building_types 保留必要类型差异、条件关系、WILD 映射与自由变量；去除整栋坐标蓝图、无依据的默认尺寸与重复百科。原有公共建筑 38 个子类型仍有独立实体。
- components 保留当前字段和能力；门窗名称与组合组件的映射保持明确，不能把建筑术语直接当作未实现的 WILD 类型。
- recipes 从建筑套餐改为功能触发、空间衔接、宿主与材料角色关系。patterns 和门窗屋顶风格策略使用 reference scope。
- MINIMAL 不再注入完整小屋示例和住宅典型尺寸表；FULL 保留完整字段说明与局部语法示例。
- 幕墙确定性参数由 `facade_recipe.py` 直接解析。该参数块保留原值并标记 system 用途，避免删掉运行配置，也避免将它当作所有建筑的模型参考。

旧原文完整保存在 [归档目录](../../docs-dev/knowledge-before-rules-v2/ARCHIVE-NOTICE.md)，不在知识库扫描根目录内。[逐节处置记录](../../docs-dev/knowledge-before-rules-v2/migration-audit.json) 包含原文哈希、当前文件和归档位置。被改写段落不声称逐句迁移；普通百科、固定案例和默认设计策略可以只留在归档。

## 代码如何吸收知识

[knowledge_policy.py](../../wild-server/app/agent/knowledge_policy.py) 定义角色、类型适用检查和已选方案查询文本；[loader.py](../../wild-server/app/spec/loader.py) 在向量查询前应用版本、scope、角色、status 与权限过滤，并在单查询、多查询及邻片扩展后检查适用性。

类型路由来自 metadata 的 `applies_to`，不维护另一套建筑关键词大表。未知类型允许没有类型卡，继续使用基础协议与共享关系，不检回最近的别墅模板。当前术语匹配支持大小写与紧邻的简单否定；复杂指代、否定范围和跨句修改仍由规划节点理解，不能视为完整自然语言语义判定。

architecture 节点检索用户点名类型和共性实现关系；skeleton 与组件节点根据已批准方案检索系统和组件能力，避免再次引入另一套建筑方案。普通问答和多意图 System Prompt 注入同样经过 Loader 的用途过滤。

[architecture_plan.py](../../wild-server/app/agent/architecture_plan.py) 不再因为精密模式自动要求多体量，也不因现代风格自动补阳台、雨棚、凸窗。丰富细节不自动等于退台；用户明确要求多体量或相关构件时仍落实这些要求。候选屋顶与对称性评分依据明确要求，不用风格名强制固定形式。有效方案之外的确定性回退仍然存在，不代表所有建筑都由模型无限自由生成。

类型百科不再是知识覆盖的必需主题。缺少本地 WILD 能力规则会报告缺口，不自动去网络寻找引擎实现；显式网络研究需求仍由已有外层 gate 处理。

## 扩库流程

使用已更新的 [wild-knowledge-ingest skill](../../.codex/skills/wild-knowledge-ingest/SKILL.md)。先核实来源与引擎实现，再决定资料进入 capability、relation、identity、reference 或归档。类型卡不再要求十项默认构成、固定尺寸或最小整栋 JSON。

在项目根目录执行：

```powershell
& wild-server/.venv/Scripts/python.exe -X utf8 .codex/skills/wild-knowledge-ingest/scripts/lint_wild_rag_docs.py wild-server/storage/knowledge_base --cross-check
& wild-server/.venv/Scripts/python.exe -X utf8 .codex/skills/wild-knowledge-ingest/scripts/preview_wild_rag_chunks.py wild-server/storage/knowledge_base --json
```

linter 拒绝生成知识中的非空整栋 Blueprint、错误角色用途及缺少适用条件的类型卡。预览必须检查真实合并后的 metadata 和分片，不能用按标题估算的数量替代。

## 同步与验收

文件变化必须同步索引并重启使用旧代码的后端进程。旧向量缺少 rules-v2 标记时不会继续注入；同步完成前，生成可能只有基础协议和已同步规则。同步使用现有 `RAGSpecLoader`，不手动清空 Chroma 目录。

在 wild-server 目录执行：

```powershell
& .venv/Scripts/python.exe -X utf8 -m unittest discover -s tests/rag -p test_knowledge_rules_v2.py -v
& .venv/Scripts/python.exe -X utf8 -m pytest tests/rag tests/components/test_architecture_plan.py tests/agent/test_web_research_gate.py -q
& .venv/Scripts/python.exe -X utf8 scripts/rag/eval_retrieval.py --sync-index --questions evals/rag_retrieval_cases.json --json-output scripts/reports/rules-v2-retrieval.json
```

评测集包含 67 个用例。`expectedSources`、`requiredTerms` 检查所需知识；新增 `forbiddenSources`、`forbiddenTerms`、`expectEmpty` 检查误注入，违反用途隔离时脚本返回 4。通用领域负样本的 `expectedAction: reject` 仍用于门禁阈值校准，不等于向量库必须返回零命中。

检索通过不能证明建筑多样性提高。实际生成验收应固定模型、采样参数和需求，各生成至少 5 次，保留 ArchitecturePlan、.wild 和 RAGTrace：

| 同一需求重复生成 | 必须保持 | 观察差异 |
|---|---|---|
| 一栋两层别墅，未点名风格 | 两层、独立建筑 | 体量组织、屋顶、立面节奏；不能只换颜色 |
| 现代两层住宅，立面丰富，不要退台 | 两层、无退台 | 开口、材质层次、入口处理 |
| 指定退台、阳台与雨棚 | 明确要求的系统 | 在约束内的布置差异 |
| 未收录类型，例如火星科研基地 | 用户明确功能、WILD 有效字段 | 不被别墅或合院模板替代 |
| 精确指定同一方案全部尺寸与材料 | 已批准方案 | 结果相似可以是正确行为，不应为多样性破坏约束 |

同时检查宿主引用、楼层衔接和渲染结果；不能通过降低质量约束、随机扰动坐标或增加无功能构件换取差异。此次本地验证结果及运行阻断记录在 [验证记录](../../docs-dev/knowledge-before-rules-v2/VALIDATION.md)。
