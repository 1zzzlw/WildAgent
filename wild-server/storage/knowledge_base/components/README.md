---
entity_name: components_index
status: supported
authority: maintainer
source: components/README.md
primary_terms:
  - 构件索引
  - components
  - WILD type
synonyms: []
---

# components 知识索引

本目录采用 rules-v2：WILD 协议、构件能力与条件组装关系提供实现边界；类型卡只补充点名类型的特征。尺寸、造型、配色与附属系统由本次需求和已批准方案决定。普通生成不召回策略、完整案例、回退或导航内容。

## 内容入口

- [composite-components-second-batch.md](composite-components-second-batch.md)
- [doors-supported.md](doors-supported.md)
- [doors.md](doors.md)
- [engine-capability-boundaries.md](engine-capability-boundaries.md)
- [glass-curtain-walls.md](glass-curtain-walls.md)
- [light.md](light.md)
- [proposed-component-extensions.md](proposed-component-extensions.md)
- [railings.md](railings.md)
- [roofs-and-eaves.md](roofs-and-eaves.md)
- [stair.md](stair.md)
- [structural-components.md](structural-components.md)
- [walls.md](walls.md)
- [windows-supported.md](windows-supported.md)
- [windows.md](windows.md)

## 维护与生效

按 wild-knowledge-ingest 技能维护来源、knowledge_role、applies_to 与真实分片。路径公共 metadata 在知识库根 config.yaml；Markdown 链接不会自动追踪。更新内容后由 RAGSpecLoader 同步索引，旧版本向量被 rules-v2 过滤；基础协议始终由文件加载。历史原文在 docs-dev/knowledge-before-rules-v2，不参与扫描。
