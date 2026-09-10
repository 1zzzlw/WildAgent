---
entity_name: recipes_index
status: supported
authority: maintainer
source: recipes/README.md
primary_terms:
  - 组装配方索引
  - recipes
  - assembly
synonyms: []
---

# recipes 知识索引

本目录采用 rules-v3，只记录已选系统的宿主、装配、引用和验证关系。是否选择某个系统由用户需求与已批准 `DesignDocument` 决定。

## 内容入口

- [component-selection-relations.md](component-selection-relations.md)
- [glass-curtain-wall-assembly.md](glass-curtain-wall-assembly.md)
- [material-role-relations.md](material-role-relations.md)
- [supported-assembly-relations.md](supported-assembly-relations.md)

## 维护与生效

按 wild-knowledge-ingest 技能维护来源、knowledge_role、applies_to 与真实分片。只有源码能够表达或校验的关系进入活动 recipes；尚无执行点的设计不变量进入 `docs-dev/knowledge-backlog/`。更新内容后由 RAGSpecLoader 同步索引，旧 revision 向量被 rules-v3 过滤；运行时直接解析的参数块继续使用 system scope。
