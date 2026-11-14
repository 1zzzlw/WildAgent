"""从 wild-core 的构件配方生成后端组件配置。

**唯一事实源**是 ``wild-core/src/compiler/declarative/recipes/*.json`` ——
同一份文件前端用来渲染、属性面板用来生成表单、后端用来规划与写提示词。

为什么要有这一层：以前加一个构件要在 ``component/registry.py``（字段契约、
关键词、提示词规则）、``architecture/profile.py``（点名关键词）、
``wild-core``（编译器 + schema）三处各写一遍。现在几何与字段都属于配方，
这里只做「配方 → ComponentConfig」的机械翻译，不引入第二个声明。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.agent.generation.component.registry import ComponentConfig

#: ``wild-server/app/agent/generation/component/recipes.py`` → 仓库根
_REPO_ROOT = Path(__file__).resolve().parents[5]
RECIPE_DIR = _REPO_ROOT / "wild-core" / "src" / "compiler" / "declarative" / "recipes"


@lru_cache(maxsize=1)
def load_recipes() -> dict[str, dict[str, Any]]:
    """读取全部配方，按 ``type`` 建索引。目录不存在时返回空字典（不阻断启动）。"""

    if not RECIPE_DIR.is_dir():
        return {}
    recipes: dict[str, dict[str, Any]] = {}
    for path in sorted(RECIPE_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        component_type = data.get("type")
        if isinstance(component_type, str) and component_type:
            recipes[component_type] = data
    return recipes


def _format_number(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, (int, float)):
        # 去掉浮点尾巴：0.65 不要写成 0.65000000000000002
        return f"{value:g}"
    return str(value)


def _describe_param(key: str, spec: dict[str, Any]) -> str:
    label = spec.get("label") or key
    bounds: list[str] = []
    if "min" in spec:
        bounds.append(f"≥{_format_number(spec['min'])}")
    if "max" in spec:
        bounds.append(f"≤{_format_number(spec['max'])}")
    kind = {"integer": "整数", "number": "数值", "string": "字符串", "vec3": "三维向量"}.get(spec.get("type"), "值")
    default = _format_number(spec.get("default"))
    parts = [f"{label}（{key}，{kind}"]
    if bounds:
        parts.append("，" + "".join(bounds))
    if default:
        parts.append(f"，默认 {default}")
    parts.append("）")
    return "".join(parts)


def recipe_rules(recipe: dict[str, Any]) -> str:
    """把配方的 params + guards 翻成提示词里的字段约束。

    刻意从配方生成而不是另写一段说明：另写一段就是第二个声明，
    迟早与 ``guards`` 分叉，而分叉后模型会照着过期的约束写参数。
    """

    lines: list[str] = []
    params = recipe.get("params") or {}
    if params:
        lines.append("- 字段：" + "；".join(
            _describe_param(key, spec) for key, spec in params.items()
            if isinstance(spec, dict)
        ))
    defaults = recipe.get("defaults") or {}
    if defaults:
        lines.append("- 初始值：" + "；".join(
            f"{key}={json.dumps(value, ensure_ascii=False)}"
            for key, value in defaults.items()
        ) + "（面板拖入时使用，可按设计覆盖）")
    guards = [item for item in (recipe.get("guards") or []) if isinstance(item, dict)]
    messages = [str(item.get("message")) for item in guards if item.get("message")]
    if messages:
        lines.append("- 约束：" + "；".join(messages))
    notes = str(recipe.get("notes") or "").strip()
    if notes:
        lines.append("- 位置与运行语义：" + notes)
    elements = recipe.get("elements") or []
    if elements:
        shapes = sorted({
            str(item.get("shape"))
            for item in elements
            if isinstance(item, dict) and item.get("shape")
        })
        repeated = sum(1 for item in elements if isinstance(item, dict) and item.get("repeat"))
        summary = f"- 编译后产出 {len(elements)} 组 primitive"
        if shapes:
            summary += f"（{'/'.join(shapes)}）"
        if repeated:
            summary += f"，其中 {repeated} 组按规则重复展开"
        lines.append(summary)
    lines.append(
        "- 该类型由构件配方定义几何，字段校验以配方 guards 为准；"
        "模型只需给出字段值，不要编造配方之外的字段"
    )
    return "\n".join(lines)


def _skip_keywords(words: list[str]) -> list[str]:
    """由点名词推出否定词（「不要百叶」「没有百叶」……）。

    手写否定词表是第三份声明，且极容易漏一个词导致"不要风扇"照样派发。
    这里机械展开，宁可多几个词也不要漏。
    """

    return [f"{prefix}{word}" for word in words for prefix in ("不要", "没有", "不需要")]


def recipe_component_configs() -> list[ComponentConfig]:
    """把每份配方翻成一份 :class:`ComponentConfig`。"""

    configs: list[ComponentConfig] = []
    for component_type, recipe in load_recipes().items():
        params = recipe.get("params") or {}
        defaults = recipe.get("defaults") or {}
        material_fields = [str(item) for item in recipe.get("materialFields") or []]
        optional = list(dict.fromkeys([*params.keys(), *defaults.keys(), *material_fields]))
        # 配方里 position 有默认值 → 它是必填的落点；否则（纯路径类）不强制。
        # 其余必填项由配方 `required` 显式声明 —— 不写就只是"可选"，
        # 模型可以合法地漏掉它（fan 的 controlPosition 就踩过这个坑）。
        required = ["type", "id"]
        if "position" in defaults:
            required.append("position")
        required.extend(str(key) for key in recipe.get("required") or [])
        required = list(dict.fromkeys(required))
        keywords = [str(word) for word in recipe.get("keywords") or []]
        configs.append(
            ComponentConfig(
                component_type=component_type,
                label=str(recipe.get("label") or component_type),
                # KB 里有专属分片的类型必须在配方里点名（如 chimney），
                # 否则检索落不到那一篇、静默退回代码兜底规则。
                entity_type=str(recipe.get("entityType") or "component"),
                rag_extra_queries=[component_type, *keywords],
                is_list=True,
                is_element=False,
                required_fields=required,
                optional_fields=optional,
                skip_keywords=_skip_keywords(keywords),
                need_keywords=keywords,
                extra_rules=recipe_rules(recipe),
                priority=5,
            )
        )
    return configs


def recipe_keywords() -> dict[str, tuple[str, ...]]:
    """配方声明的点名关键词；供规划阶段「用户点了名就进配额」使用。"""

    return {
        component_type: tuple(str(word) for word in recipe.get("keywords") or [])
        for component_type, recipe in load_recipes().items()
        if recipe.get("keywords")
    }
