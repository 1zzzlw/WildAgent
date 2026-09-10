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

本目录采用 rules-v3：普通生成只召回 WILD 协议、已实现构件能力与可执行组装关系。建筑百科、建筑类型卡、风格策略、完整案例和尚未实现的提案不进入知识库生成上下文；建筑用途由模型理解，执行代码只把需求路由到有限的 WILD 能力 profile。尺寸、造型、配色与附属系统由本次需求和已批准方案决定。

## 内容入口

- [BLUEPRINT-SPEC-FULL.md](BLUEPRINT-SPEC-FULL.md)
- [BLUEPRINT-SPEC-MINIMAL.md](BLUEPRINT-SPEC-MINIMAL.md)
- [BLUEPRINT-PATCH-PROTOCOL.md](BLUEPRINT-PATCH-PROTOCOL.md)
- [components](components/README.md)
- [recipes](recipes/README.md)

## 维护与生效

按 wild-knowledge-ingest 技能维护来源、knowledge_role、applies_to 与真实分片。路径公共 metadata 在知识库根 config.yaml；Markdown 链接不会自动追踪。更新内容后由 RAGSpecLoader 同步索引，旧 revision 向量被 rules-v3 过滤；基础协议始终由文件加载。退出活动召回的类型资料位于 `docs-dev/retired-knowledge/`，待实现能力位于 `docs-dev/knowledge-backlog/`。
