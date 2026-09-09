---
entity_name: knowledge_base_index
status: supported
authority: maintainer
source: README.md
primary_terms:
  - WILD 知识库
  - 文档分类
synonyms:
  - knowledge base
---

# WILD 规则知识库

本目录采用 rules-v2：WILD 协议、构件能力与条件组装关系提供实现边界；类型卡只补充点名类型的特征。尺寸、造型、配色与附属系统由本次需求和已批准方案决定。普通生成不召回策略、完整案例、回退或导航内容。

## 内容入口

- [BLUEPRINT-SPEC-FULL.md](BLUEPRINT-SPEC-FULL.md)
- [BLUEPRINT-SPEC-MINIMAL.md](BLUEPRINT-SPEC-MINIMAL.md)
- [building_types](building_types/README.md)
- [components](components/README.md)
- [patterns](patterns/README.md)
- [recipes](recipes/README.md)

## 维护与生效

按 wild-knowledge-ingest 技能维护来源、knowledge_role、applies_to 与真实分片。路径公共 metadata 在知识库根 config.yaml；Markdown 链接不会自动追踪。更新内容后由 RAGSpecLoader 同步索引，旧版本向量被 rules-v2 过滤；基础协议始终由文件加载。历史原文在 docs-dev/knowledge-before-rules-v2，不参与扫描。
