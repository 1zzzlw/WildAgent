---
entity_type: material
entity_name: material_role_relations
topic: parameters
status: supported
authority: engine
source: wild-web/wild-lang/schema.json
primary_terms:
  - 材质角色
  - material reference
  - glass material
synonyms: []
---

# 材质角色与 WILD 字段关系

## 角色和引用

墙、楼板、框、门扇、屋面和玻璃分别引用本次材质方案中的材料 ID。相同设计角色可以跨节点复用同一 ID；不同物理角色需要不同渲染参数时使用不同 ID。建筑名称不决定颜色、纹理、粗糙度或金属度。

所有 `material`、`frameMaterial`、`leafMaterial` 与 `glassMaterial` 引用必须存在于蓝图 `materials` 或受支持的全局材质库。材料名称只是 ID，不能证明混凝土、木、石等真实结构或专业性能。

## 物理玻璃

需要真实透射时，材料使用 `materialClass: glass`、正数 `transmission` 和有效 `ior`，`opacity` 省略或设为 `1`。玻璃与不透明框架使用不同材料引用。透射外观还需要在实际场景、光照和渲染器中验证。

## 设计自由度

颜色、纹理、粗糙度、金属度、透明度与材质组合来自用户要求和批准材质方案。局部 JSON 示例中的数值只解释字段，不成为住宅、公共建筑或任何风格的默认配色。
