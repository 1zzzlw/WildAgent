"""条目可用的工具集：注册表 + 按 (op, kind) 裁剪。

对应《动态节点设计规划》§4.8–§4.11。

两条纪律：
1. **fail-closed 默认值**：工具作者不声明时，按最保守的假设处理——默认只读为否、
   默认不可并发、默认单条目只允许调用 1 次（对照 Claude Code 的 ``buildTool()`` +
   ``TOOL_DEFAULTS``，忘了声明就是"会写入、不能并发"）。
2. **工具集是数据的函数**：``tools_for(item)`` 是纯函数，顺序确定；新增 ``kind`` 只加
   一条声明，不改这里的逻辑。

本模块只在第一次访问注册表时才导入 ``spatial_tools``（三万余行的工具模块），
避免拖慢不需要工具的路径。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

#: 工具型条目：只有这两类会把工具交给模型（§4.7）。其余条目必须确定性可复现。
TOOL_TYPED_OPS: tuple[str, ...] = ("generate", "repair")

#: 工具类别（§4.8）。类别决定它能出现在哪些条目上。
TOOL_CATEGORIES: tuple[str, ...] = (
    "knowledge_search",
    "validate",
    "fix",
    "mutate",
    "web_search",
)


@dataclass(frozen=True)
class ToolSpec:
    """一个工具的声明。默认值即 fail-closed 假设。"""

    name: str
    category: str
    tool: Any = None
    #: 单条目内允许的调用次数上限；不声明时按 1 处理。
    max_calls: int = 1
    #: 是否只读（fail-closed：默认视为会写入）。
    read_only: bool = False
    #: 是否允许并发（fail-closed：默认不允许）。
    concurrency_safe: bool = False
    #: 是否不可逆（删除类操作）。
    destructive: bool = False
    #: 允许使用它的条目，形如 ``("generate:window", "repair")``；空元组表示全部条目。
    applies_to: tuple[str, ...] = ()
    #: 只有该开关为真时才进入工具集（默认关闭的能力走这里，例如在线检索）。
    enabled: bool = True
    notes: str = ""


def tool_spec(
    name: str,
    category: str,
    tool: Any = None,
    **overrides: Any,
) -> ToolSpec:
    """builder：补齐 fail-closed 默认值，只让工具作者声明自己的特殊之处。"""

    if category not in TOOL_CATEGORIES:
        raise ValueError(f"未知工具类别 {category!r}，允许值：{TOOL_CATEGORIES}")
    return replace(ToolSpec(name=name, category=category, tool=tool), **overrides)


_REGISTRY: tuple[ToolSpec, ...] | None = None


def _knowledge_tool() -> Any:
    """按需检索工具（带 metadata 过滤，见 §4.10）。"""

    from app.agent.plan.knowledge_tool import search_knowledge

    return search_knowledge


def _build_registry() -> tuple[ToolSpec, ...]:
    from app.tools.spatial_tools import (
        fix_element_dimensions,
        fix_element_elevations,
        fix_material_references,
        fix_opening_coords,
        fix_opening_fit,
        fix_roof_coverage,
        fix_stair_alignment,
        fix_wall_junctions,
        validate_collision,
        validate_element_dimensions,
        validate_element_required_fields,
        validate_blueprint_structure,
        validate_opening_coords,
        validate_opening_fit,
        validate_reference_integrity,
        validate_roof_coverage,
        validate_stair_alignment,
        validate_wall_junctions,
    )

    opening_scope = ("generate:door", "generate:window", "generate:bay_window", "repair")
    roof_scope = ("generate:roof", "generate:chimney", "repair")
    wall_scope = ("generate:door", "generate:window", "generate:canopy", "generate:balcony", "repair")
    component_scope = ("generate", "repair")

    specs: list[ToolSpec] = [
        # ── 检索：唯一允许模型自己发起的知识查询入口（§4.10）──
        tool_spec(
            "search_knowledge",
            "knowledge_search",
            tool=_knowledge_tool(),
            max_calls=2,
            read_only=True,
            concurrency_safe=True,
            applies_to=component_scope,
            notes="必须带 metadata 过滤，不得绕过 app/rag/security.py",
        ),
        # ── 校验：可以给模型自查，但关键校验由 validate 条目兜底（§4.7）──
        tool_spec("validate_blueprint_structure", "validate", validate_blueprint_structure,
                  read_only=True, concurrency_safe=True, applies_to=component_scope),
        tool_spec("validate_reference_integrity", "validate", validate_reference_integrity,
                  read_only=True, concurrency_safe=True, applies_to=component_scope),
        tool_spec("validate_element_dimensions", "validate", validate_element_dimensions,
                  read_only=True, concurrency_safe=True, applies_to=component_scope),
        tool_spec("validate_element_required_fields", "validate",
                  validate_element_required_fields, read_only=True, concurrency_safe=True,
                  applies_to=component_scope),
        tool_spec("validate_opening_coords", "validate", validate_opening_coords,
                  read_only=True, concurrency_safe=True, applies_to=opening_scope),
        tool_spec("validate_opening_fit", "validate", validate_opening_fit,
                  read_only=True, concurrency_safe=True, applies_to=opening_scope),
        tool_spec("validate_wall_junctions", "validate", validate_wall_junctions,
                  read_only=True, concurrency_safe=True, applies_to=wall_scope),
        tool_spec("validate_roof_coverage", "validate", validate_roof_coverage,
                  read_only=True, concurrency_safe=True, applies_to=roof_scope),
        tool_spec("validate_collision", "validate", validate_collision,
                  read_only=True, concurrency_safe=True, applies_to=("repair",)),
        tool_spec("validate_stair_alignment", "validate", validate_stair_alignment,
                  read_only=True, concurrency_safe=True, applies_to=("repair",)),
        # ── 确定性修复：只给 repair 条目（generate 不该自己改既有元素）──
        tool_spec("fix_material_references", "fix", fix_material_references, applies_to=("repair",)),
        tool_spec("fix_opening_coords", "fix", fix_opening_coords, applies_to=("repair",)),
        tool_spec("fix_opening_fit", "fix", fix_opening_fit, applies_to=("repair",)),
        tool_spec("fix_wall_junctions", "fix", fix_wall_junctions, applies_to=("repair",)),
        tool_spec("fix_stair_alignment", "fix", fix_stair_alignment, applies_to=("repair",)),
        tool_spec("fix_element_dimensions", "fix", fix_element_dimensions, applies_to=("repair",)),
        tool_spec("fix_element_elevations", "fix", fix_element_elevations, applies_to=("repair",)),
        tool_spec("fix_roof_coverage", "fix", fix_roof_coverage, applies_to=("repair",)),
        # ── 定点改蓝图：白名单动作，由程序执行（§4.11 族 B）──
        tool_spec(
            "repair_actions",
            "mutate",
            tool=None,
            max_calls=1,
            destructive=True,
            applies_to=("repair",),
            notes="REPAIR_TOOL_SPECS 白名单动作，经 execute_repair_actions 执行",
        ),
        # ── 外部检索：默认关闭（§4.12）──
        tool_spec(
            "web_search",
            "web_search",
            tool=None,
            max_calls=1,
            read_only=True,
            enabled=False,
            applies_to=("repair",),
            notes="默认关闭；开启后命中必须记 URL 并标记本次结果不可复现",
        ),
    ]
    return tuple(specs)


def get_tool_registry() -> tuple[ToolSpec, ...]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return _REGISTRY


def _scope_matches(spec: ToolSpec, op: str, kind: str) -> bool:
    if not spec.applies_to:
        return True
    target = f"{op}:{kind}" if kind else op
    return target in spec.applies_to or op in spec.applies_to


def tools_for(item: Any) -> list[ToolSpec]:
    """按条目裁剪工具集。纯函数：同样的条目必然得到同样的工具集与顺序。

    漏斗顺序（对照 Claude Code 的分层注册）：``enabled`` → ``applies_to`` →
    条目形态约束。``enabled=False`` 的工具在这里就被滤掉，而不是等调用时失败。
    """

    op = getattr(item, "op", "") or ""
    kind = getattr(item, "kind", "") or ""
    # 硬闸门：merge / validate / fix 是确定性条目，工具集恒为空。
    # 关键校验由 plan 里显式的 validate 条目保证，模型无法跳过。
    if op not in TOOL_TYPED_OPS:
        return []
    selected = [
        spec
        for spec in get_tool_registry()
        if spec.enabled and _scope_matches(spec, op, kind)
    ]
    return sorted(selected, key=lambda spec: (spec.category, spec.name))


def tool_names_for(item: Any) -> list[str]:
    """给提示词与审计用的工具名列表（顺序与 ``tools_for`` 一致）。"""

    return [spec.name for spec in tools_for(item)]
