---
doc_type: blueprint_spec
knowledge_role: protocol
doc_scope: generation
knowledge_layer: wild_schema
entity_type: schema
entity_name: blueprint_templates_instances
topic: structure
wild_version: "1.1"
status: supported
authority: maintainer
primary_terms:
  - 模板与实例
  - templates
  - instances
  - materialOverride
  - 模板 id
synonyms: []
---

# 模板与实例

蓝图可以包含 `templates` 字典和 `instances` 数组。

```json
{
  "templates": {
    "pillar": {
      "type": "column", "id": "pillar_template", "base": [0, 0, 0],
      "height": 3.3, "bottomRadius": 0.16, "topRadius": 0.14,
      "style": "chinese_wooden", "material": "wood"
    }
  },
  "instances": [
    { "ref": "pillar", "position": [0, 0, 0] },
    { "ref": "pillar", "position": [3, 0, 0] }
  ]
}
```

## 模板 id 规则

模板定义中的构件 `id` 可选。引擎展开实例时自动按 `{模板名}_{实例索引}` 方式生成唯一 id（例如 `pillar_0`、`pillar_1`）。

## 材质覆盖

实例可以覆盖模板中的材质：

```json
{ "materialOverride": { "column": "stone" } }
```
