---
entity_type: material
entity_name: residential_material_palette
topic: parameters
status: supported
authority: maintainer
source: recipes/residential-material-palette.md
primary_terms:
  - 居住建筑材质
  - 材质角色
synonyms: []
---

# 居住建筑材质角色与字段关系

## 材质选择

墙、楼板、框、门扇、屋面、玻璃分别由本次材质方案确定角色。建筑名称不决定白墙、灰瓦、木色或金属色；同一角色跨节点复用同一材料 ID。旧版调色板仅保存在历史资料，不作为默认色值或 roughness/metallic 配方。

## 物理玻璃

选择真实透射玻璃时使用 materialClass: glass、正 transmission 与有效 ior；opacity 省略或为 1。玻璃与框架分材质，不能用深色不透明墙冒充玻璃。实际透射效果需要场景、光照和渲染验证。塑料膜、实体材质和水面不能仅因需要透明就全部标成 glass。

## 引用与边界

所有 material、frameMaterial、leafMaterial、glassMaterial 引用必须存在于 materials；字段与取值依据 BLUEPRINT-SPEC-FULL.md。材料名字可自定义，混凝土、木、石等名称不证明结构、耐火或保温性能。固定示例数值不是引擎限制，应由用户需求、材质方案与支持范围确定。
