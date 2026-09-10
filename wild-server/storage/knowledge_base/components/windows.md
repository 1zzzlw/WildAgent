---
entity_type: window
entity_name: window_variant_mappings
topic: assembly
status: supported
authority: maintainer
source: wild-web/wild-lang/schema.json
primary_terms:
  - 窗型映射
  - window variant
synonyms: []
---

# 窗型语义到 WILD 的条件映射

## 共性边界

窗型名称不产生新的 WILD `type`，也不决定建筑风格、窗数、尺寸、排列或材质。基础窗统一服从 `windows-supported.md`；下列映射只在用户或批准设计明确选择对应系统时使用。

## 规则框格窗

<!-- rag-meta
applies_to:
  - 直棂窗
  - 菱花窗
  - 槛窗
  - 条形窗
  - ribbon window
entity_name: gridded_window_mapping
topic: assembly
primary_terms:
  - verticalMullions
  - horizontalMullions
synonyms: []
-->

可规则化的横竖框格使用 `window.verticalMullions` 与 `horizontalMullions`。复杂斜格、花纹或不规则图案没有原生窗格字段；只有批准设计要求且接受近似时才增加显式 `primitive`。

## 空窗与漏窗

<!-- rag-meta
applies_to:
  - 空窗
  - 漏窗
  - 花窗
  - 月洞门
entity_name: open_window_mapping
topic: assembly
primary_terms:
  - opening
  - no glass
synonyms: []
-->

纯洞口使用 `geometry.elements` 中的 `opening` 并引用墙体，不强加玻璃。需要可见格栅时另建受支持几何，格栅不能充当洞口布尔关系。

## 门上亮窗

<!-- rag-meta
applies_to:
  - 横披窗
  - 门亮子
  - transom window
entity_name: transom_window_mapping
topic: assembly
primary_terms:
  - parentWall
  - transom
synonyms: []
-->

亮窗是独立 `window`，与门引用同一 `parentWall`。其底标高由门顶和批准留缝推导，不能使用不存在的 `parentOpening`。

## 拱形与装饰轮廓窗

<!-- rag-meta
applies_to:
  - 玫瑰窗
  - 帕拉第奥窗
  - 尖拱窗
  - 圆拱窗
  - 柳叶窗
entity_name: decorative_window_outline_mapping
topic: constraints
primary_terms:
  - opening style
  - primitive
synonyms: []
-->

当前 `window` 只生成矩形组合窗，没有 `openingStyle`。圆窗、尖拱和复杂装饰轮廓需要 `opening` 与显式 `primitive` 近似；不能把建筑术语写成未定义字段，也不能宣称已实现真实曲线窗系统。

## 幕墙窗

<!-- rag-meta
applies_to:
  - 玻璃幕墙
  - 幕墙窗
  - curtain wall
entity_name: curtain_wall_window_mapping
topic: assembly
primary_terms:
  - curtain wall window
  - facade grid
synonyms: []
-->

幕墙窗按 `glass-curtain-wall-assembly.md` 使用墙体宿主加窗网格，或显式骨架与玻璃。建筑名称本身不触发幕墙。

## 转角窗

<!-- rag-meta
applies_to:
  - 转角窗
  - corner window
entity_name: corner_window_mapping
topic: assembly
primary_terms:
  - two parent walls
synonyms: []
-->

相邻立面分别创建窗口并绑定各自墙体，统一窗台与窗顶标高。单个窗不能跨越两个 `parentWall`。

## 天窗

<!-- rag-meta
applies_to:
  - 天窗
  - skylight
entity_name: skylight_mapping
topic: constraints
primary_terms:
  - parentRoof unsupported
  - transparent roof
synonyms: []
-->

`window` 不支持 `parentRoof`。屋顶采光只能使用透明屋盖材质或独立 `primitive` 近似；当前不能仅靠透明板声称完成真实屋顶开洞。

## 落地窗

<!-- rag-meta
applies_to:
  - 落地窗
  - floor-to-ceiling window
entity_name: floor_to_ceiling_window_mapping
topic: assembly
primary_terms:
  - floor level
  - parentWall
synonyms: []
-->

仍使用标准 `window`。窗底与本层地面关系、窗顶余量和宽度来自批准设计及宿主范围；“落地”不等于出入口，也不规定固定窗高。
