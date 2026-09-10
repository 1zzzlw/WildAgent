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

本目录采用 rules-v3，只保存当前 WILD 字段、构件能力、局部语义映射和实现边界。建筑名称不决定构件数量、尺寸、造型、配色或附属系统。

## 内容入口

- [composite-components-second-batch.md](composite-components-second-batch.md)
- [doors-supported.md](doors-supported.md)
- [doors.md](doors.md)
- [engine-capability-boundaries.md](engine-capability-boundaries.md)
- [glass-curtain-walls.md](glass-curtain-walls.md)
- [light.md](light.md)
- [railings.md](railings.md)
- [roofs-and-eaves.md](roofs-and-eaves.md)
- [stair.md](stair.md)
- [structural-components.md](structural-components.md)
- [walls.md](walls.md)
- [windows-supported.md](windows-supported.md)
- [windows.md](windows.md)

## 维护与生效

按 wild-knowledge-ingest 技能维护来源、knowledge_role、applies_to 与真实分片。只有显式选择的专用系统可以使用 `applies_to`；建筑类型和风格不能成为隐式触发器。未实现提案进入 `docs-dev/knowledge-backlog/`，不在活动目录中等待 status 过滤。更新后由 RAGSpecLoader 同步索引，旧 revision 向量被 rules-v3 过滤。
