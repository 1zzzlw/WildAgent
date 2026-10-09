---
entity_name: massing_layers
topic: composition
status: supported
authority: engine
primary_terms:
  - 分层体量
  - 退台
  - 裙房
  - 层间腰线
synonyms: []
applies_to:
  - 退台
  - 裙房
  - 分层体量
  - 层间腰线
---

# 已选分层体量的表达边界

适用条件：本次需求或当前方案明确选择分层体量、裙房、退台或层间腰线。它们是可选设计，不由用途或风格自动触发。依据为 app/design/contracts.py、app/agent/generation/architecture/facade.py 与 app/agent/compiler/compile.py；当前没有任意楼层露台、交通门与线脚的通用自动装配承诺。

## 分层体量与屋型差异

用 volumes 的 start_floor/end_floor 和平面起点、宽深描述各层体量；roof.volumes 可给某体量不同屋型或出檐。massing.tiers 可描述逐段收放，各段层数之和等于总层数。当前多体量分段只支持 flat/gable/hip；上层部分覆盖下层的剩余局部屋面尚不支持。裙房和退台不是填一个名称就完整实现，先核对具体体量与编译诊断，不以层次感文案代替可表达的几何。

## 板、墙与挂接关系

当前引擎 floor.from[1] 是板底，板顶为 from[1]+thickness；wall.from[1]/to[1] 是墙底/墙顶世界标高。当前骨架与编译器负责标高和分板，architecture 不直接书写这组低层坐标。调整层高或轮廓后核对板顶、墙底、交通与墙挂附件，以实际编译结果为准，不照抄旧实例坐标。文档中的统一板顶坐标口径不能覆盖当前引擎事实。

## 腰线与屋面檐口

引擎 cornice 可用世界 path 和 profile 表达线脚，但当前设计实例以屋面宿主解析，自动模板只覆盖 flat/gable/hip；它不等于任意楼层、任意墙面腰线都能由 architecture 直接生成。需要未提供的路径或楼层挂接时保留表达限制，不能把屋面檐口数量当作已生成层间腰线。没有可执行通道的部分不增加配额，也不改写成已支持的强规则。
