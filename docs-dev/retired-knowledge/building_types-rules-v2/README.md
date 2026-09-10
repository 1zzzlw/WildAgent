---
entity_name: building_types_index
status: supported
authority: maintainer
source: building_types/README.md
primary_terms:
  - 建筑类型索引
  - 建筑分类
synonyms:
  - building types
---

# building_types 知识索引

本目录采用 rules-v2：WILD 协议、构件能力与条件组装关系提供实现边界；类型卡只补充点名类型的特征。尺寸、造型、配色与附属系统由本次需求和已批准方案决定。普通生成不召回策略、完整案例、回退或导航内容。

## 内容入口

- [agricultural](agricultural/)
- [catalog](catalog/README.md)
- [industrial](industrial/)
- [public](public/)
- [residential](residential/)

## 维护与生效

按 wild-knowledge-ingest 技能维护来源、knowledge_role、applies_to 与真实分片。路径公共 metadata 在知识库根 config.yaml；Markdown 链接不会自动追踪。更新内容后由 RAGSpecLoader 同步索引，旧版本向量被 rules-v2 过滤；基础协议始终由文件加载。历史原文在 docs-dev/knowledge-before-rules-v2，不参与扫描。
