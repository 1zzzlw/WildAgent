"""P6-B：可机械提取的引擎能力查询面。

这一层要解决的是「模型不知道引擎能做什么」——P5 里`canopy` 的宿主语义在提示词
与契约里都没定义，就是这个缺陷的一个实例。做法只有一条：

**能从事实源机械提取的字段，一律从事实源读；不能机械提取的语义，标注来源、
人工维护并在漂移时报出来。**

事实源（唯一）：

- ``storage/knowledge_base/schema.json`` —— 必填字段、类型、枚举、取值范围；
- ``generation/component/registry.py::COMPONENT_REGISTRY`` —— 哪些类型已实现、
  写进 elements 还是 components、额外规则文本。

🔴 **不在这里建第二份字段白名单。** 曾经想这么干（列一张"引擎支持哪些字段"的表），
那必然与schema 漂移；本模块的字段部分全部实时从 schema 读，测试里有一条守卫专门
钉住"schema 加字段 → 查询面自动跟着变"。

三态语义（P6-B 第 4 条要求它们**不同**）：

- ``unsupported`` —— 引擎不支持这个类型（查到了但明确不支持）；
- ``not_found`` —— 引擎里根本没有这个类型（名字拼错/未注册）；
- ``query_failed`` —— 查询面自身不可用（schema 读不到、索引缺失）。
"""

from __future__ import annotations

import json
from copy import deepcopy
import threading
from typing import Any

from app.agent.generation.component.registry import COMPONENT_REGISTRY
from app.utils.blueprint_normalizer import SCHEMA_PATH

#: 能力面版本。schema 或注册表变化时**内容会变但版本不变**—— 版本只标"这份查询面
#: 的形状/语义有没有变"，不标"内容有没有变"（内容变更是正常的，改引擎就该变）。
CAPABILITY_SURFACE_VERSION = "p6b.2"

#: 查询状态闭集。新增状态要显式改这里（测试有守卫），别悄悄多一个 —— 状态一多，
#: 调用方的 `if status == "unsupported"` 分支就会漏掉新情况。
_STATUSES = frozenset({"ok", "not_found", "unsupported", "query_failed"})

_schema_lock = threading.Lock()
_schema_cache: dict[str, Any] | None = None
_schema_load_error: str | None = None


def load_engine_schema(*, refresh: bool = False) -> dict[str, Any] | None:
    """读引擎 schema。读不到返回 ``None`` —— 调用方据此报``query_failed``，
    绝不返回空字典假装"查询成功但没有能力"。"""

    global _schema_cache, _schema_load_error
    with _schema_lock:
        if _schema_cache is not None and not refresh:
            return deepcopy(_schema_cache)
        try:
            with open(SCHEMA_PATH, encoding="utf-8") as handle:
                data = json.load(handle)
                if not isinstance(data, dict) or not isinstance(data.get("$defs"), dict):
                    raise ValueError("schema 根或 $defs 不是对象")
        except (OSError, ValueError) as exc:
            _schema_cache = None
            _schema_load_error = f"{type(exc).__name__}: {exc}"
            return None
        _schema_cache = data
        _schema_load_error = None
        return deepcopy(_schema_cache)


def _type_of(definition: dict[str, Any]) -> str | None:
    """仅从 const 读取实体类型；required 字段不能证明具体类型。"""

    raw = definition.get("type")
    if isinstance(raw, dict) and isinstance(raw.get("const"), str):
        return raw["const"]
    const = (definition.get("properties") or {}).get("type") or {}
    if isinstance(const, dict) and isinstance(const.get("const"), str):
        return const["const"]
    return None


def _field_summary(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    """把一个字段的 schema 压成设计侧真正需要知道的约束。"""

    out: dict[str, Any] = {"name": name}
    if isinstance(spec.get("const"), str):
        out["const"] = spec["const"]
    kind = spec.get("type")
    if isinstance(kind, str):
        out["type"] = kind
    if isinstance(spec.get("enum"), list):
        out["enum"] = list(spec["enum"])
    if "exclusiveMinimum" in spec:
        out["exclusiveMinimum"] = spec["exclusiveMinimum"]
    if "minimum" in spec:
        out["minimum"] = spec["minimum"]
    if "maximum" in spec:
        out["maximum"] = spec["maximum"]
    if "minItems" in spec:
        out["minItems"] = spec["minItems"]
    if "maxItems" in spec:
        out["maxItems"] = spec["maxItems"]
    if "minLength" in spec:
        out["minLength"] = spec["minLength"]
    if "maxLength" in spec:
        out["maxLength"] = spec["maxLength"]
    ref = spec.get("$ref")
    if isinstance(ref, str):
        out["ref"] = ref.rsplit("/", 1)[-1]
    one_of = spec.get("oneOf")
    if isinstance(one_of, list):
        refs = [item["$ref"].rsplit("/", 1)[-1] for item in one_of
                if isinstance(item, dict) and isinstance(item.get("$ref"), str)]
        if refs:
            out["oneOfRefs"] = refs
    if isinstance(spec.get("description"), str) and spec["description"]:
        out["description"] = spec["description"][:120]
    return out


def _capability_from_definition(
    entity_kind: str, definition: dict[str, Any], definition_name: str,
) -> dict[str, Any] | None:
    type_name = _type_of(definition)
    if not type_name:
        return None
    properties = definition.get("properties") or {}
    required = list(definition.get("required") or [])
    config = COMPONENT_REGISTRY.get(type_name)
    fields = {
        name: _field_summary(name, spec)
        for name, spec in properties.items()
        if isinstance(spec, dict)
    }
    optional = sorted(name for name in fields if name not in required)
    return {
        "type": type_name,
        "entity_kind": entity_kind,
        "implemented": bool(config.implemented) if config else True,
        # 写进 elements 还是 components —— 设计层选错会被校验器直接拒。
        "target": ("elements" if entity_kind == "element"
                   else "elements" if config and config.is_element else "components"),
        "required": required,
        "optional": optional,
        "fields": fields,
        # 下面三项**不能从 schema 机械提取**，来源标注在source 字段里。
        "coord_semantics": _COORD_SEMANTICS.get(type_name, ""),
        "host_rule": _HOST_RULES.get(type_name, ""),
        "prompt_rules": (config.extra_rules or "") if config else "",
        "source": {
            "fields": f"schema.json::$defs.{definition_name}",
            "registry": bool(config),
            "semantics": "人工维护（见 _COORD_SEMANTICS / _HOST_RULES）",
        },
        "surface_version": CAPABILITY_SURFACE_VERSION,
    }


#: 坐标语义 —— **人工维护**，不从 schema 读（schema 只说"这是 3 个数"，没说每个数
#: 是底还是顶）。键必须与 schema 里的 type 字面一致，否则这条语义永远不会被读到。
_COORD_SEMANTICS: dict[str, str] = {
    "wall": "from[1]=墙底世界Y，to[1]=墙顶世界Y",
    "floor": "from[1]=楼板底面世界Y（板顶= from[1]+thickness）",
    "roof": "position[1]=承托墙顶世界Y",
    "door": "from=[沿墙距离, 洞口底Y, 法向偏移]，from[0] 指开口左边缘",
    "window": "from=[沿墙距离, 窗台Y, 法向偏移]，from[0] 指开口左边缘",
    "balcony": "from=[沿墙距离, 阳台板底Y, 法向偏移]",
    "canopy": "from=[沿墙距离, 雨棚板底Y, 法向偏移]",
    "railing": "path 为世界坐标折线（minItems=2），逐点Y 是栏杆底标高",
    "stair": "from/to 为梯段起止点世界坐标",
    "column": "base 为柱底世界坐标，柱顶Y=base[1]+height",
    "beam": "from/to 为梁端点世界坐标",
    "primitive": "position[1]=形体中心Y",
}

#: 宿主约束 —— **人工维护**，同上。空串表示"该类型无宿主要求"。
_HOST_RULES: dict[str, str] = {
    "door": "parentWall 必须指向已落地的墙",
    "window": "parentWall 必须指向已落地的墙",
    "balcony": "parentWall 必须指向已落地的墙，且该墙竖向范围要容得下 from[1]",
    "canopy": "parentWall 必须指向有真实门窗的墙（无遮蔽对象的雨棚是漂浮废构件）",
    "railing": "只放在有高差处（阳台/露台/楼梯两侧/二层平台），不要放地面层外墙",
    "cornice": "parentRoof 必须是已落地的屋面元素 id",
    "chimney": "parentRoof 必须是已落地的屋面元素 id",
    "light": "无宿主；按出现序与派生结果对齐",
    "stair": "竖向构件须落在 layout.shared_footprint 内",
}


def _collect(*, refresh: bool = False) -> dict[str, dict[str, Any]] | None:
    schema = load_engine_schema(refresh=refresh)
    if schema is None:
        return None
    defs = schema.get("$defs") or {}
    out: dict[str, dict[str, Any]] = {}
    for entity_kind, union in (("element", "geometryElement"), ("component", "componentSpec")):
        for ref in (defs.get(union) or {}).get("oneOf", []):
            name = str(ref.get("$ref") or "").rsplit("/", 1)[-1]
            definition = defs.get(name)
            if not isinstance(definition, dict):
                continue
            capability = _capability_from_definition(entity_kind, definition, name)
            if capability:
                capability["schema"] = definition
                capability["generation_registered"] = capability["type"] in COMPONENT_REGISTRY
                out[capability["type"]] = capability
    return out


_capability_lock = threading.Lock()
_capability_cache: dict[str, dict[str, Any]] | None = None


def capability_surface(*, refresh: bool = False) -> dict[str, dict[str, Any]]:
    """全部能力（类型 → 能力条目）。schema 读不到时返回空字典，
    调用方必须结合 :func:`capability_query` 的状态区分"空"与"查询失败"。

    🔴 **读失败的结果不缓存**：早先把空字典写进缓存，于是 schema 一时读不到
    之后，整个进程的能力面就永久是空的（每次调用都命中缓存、每次都重算成空）。
    正确的口径是"没读到就每次重试"，因为读失败通常是暂时的（文件正被替换、
    部署中间态）。schema 确实读到了但**内容为空**才缓存 —— 那说明引擎侧真的
    一个类型都没有，是稳定事实。
    """

    surface, _ = _capability_snapshot(refresh=refresh)
    return surface


def _capability_snapshot(*, refresh: bool = False):
    """同一查询只加载一次；空能力面与加载失败保留不同状态。"""
    global _capability_cache
    with _capability_lock:
        if _capability_cache is not None and not refresh:
            return deepcopy(_capability_cache), None
        surface = _collect(refresh=refresh)
        _capability_cache = surface
        if surface is None:
            return {}, _schema_load_error or "schema 不可用"
        return deepcopy(surface), None


def capability_query(
    component_type: str,
    *,
    task: str = "",
    refresh: bool = False,
) -> dict[str, Any]:
    """查一个类型的引擎能力。

    返回 ``{"status": ..., "type": ..., "capability": ..., "source_version": ...}``，
    ``status`` 取四个值：

    - ``ok`` —— 查到了；
    - ``not_found`` —— 引擎里没有这个类型（名字写错/未注册）；
    - ``unsupported`` —— 注册表里标了 ``implemented=False``；
    - ``query_failed`` —— 查询面自身不可用（schema 读不到）。

    🔴 这四个必须分开：把"引擎不支持"和"查询没查到"混成一个"不支持"，
    模型会去请求一个其实存在的能力，或者反过来把一个真不支持的能力当可用。
    """

    name = str(component_type or "").strip()
    surface, error = _capability_snapshot(refresh=refresh)
    if error:
        return {
            "status": "query_failed",
            "type": name,
            "reason": error,
            "source_version": CAPABILITY_SURFACE_VERSION,
        }
    capability = surface.get(name)
    if capability is None:
        return {
            "status": "not_found",
            "type": name,
            "available": sorted(surface),
            "source_version": CAPABILITY_SURFACE_VERSION,
        }
    if not capability["implemented"]:
        return {
            "status": "unsupported",
            "type": name,
            "capability": capability,
            "source_version": CAPABILITY_SURFACE_VERSION,
        }
    return {
        "status": "ok",
        "type": name,
        "capability": capability,
        # `task` 只是给调用方裁剪用的提示位，不参与判据 —— 别把它当成过滤条件，
        # 那会让"换个说法查同一个能力"变成查不到。
        "task": str(task or ""),
        "source_version": CAPABILITY_SURFACE_VERSION,
    }


def capability_type_labels() -> list[str]:
    """本次提示词里要展开能力摘要的类型列表（注册表事实，按 priority 排序）。

    只列**注册表里已实现**的类型 —— 未注册的名字不查（那是开放集的通用通道，
    走知识库检索，不在这张能力表里）。排序用注册表的 ``priority``，
    让配额/建议里更可能用到的类型排在前面。
    """

    configs = [c for c in COMPONENT_REGISTRY.values() if c.implemented]
    return [
        c.component_type
        for c in sorted(configs, key=lambda item: (item.priority, item.component_type))
    ]


def capability_brief(
    component_type: str,
    *,
    full: bool = False,
    max_optional: int = 6,
) -> str:
    """给提示词用的紧凑能力摘要（按任务裁剪，不塞整个 schema）。

    ``full=False``（默认）只给**最容易写错、且无法从字段名推断**的三项：写进哪张表、
    坐标语义、宿主约束；可选字段列表截到 ``max_optional`` 个 —— 十几个英文字段名
    挤掉的是"必须表达哪些字段"这条真正的约束，提示词预算花在刀刃上。
    ``full=True`` 给出完整清单，供需要精确字段名的场合（工具回执/调试）使用。
    """

    result = capability_query(component_type)
    if result["status"] != "ok":
        return f"{component_type}：{result['status']}"
    cap = result["capability"]
    lines = [f"{cap['type']}（写入 geometry.{cap['target']}）"]
    if full:
        lines.append(f"  必填：{'、'.join(cap['required']) or '无'}")
    optional = cap["optional"]
    if optional:
        shown = "、".join(optional) if full or len(optional) <= max_optional else (
            "、".join(optional[:max_optional]) + f"…（共 {len(optional)} 个）"
        )
        lines.append(f"  可选设计参数：{shown}")
    if cap["coord_semantics"]:
        lines.append(f"  坐标语义：{cap['coord_semantics']}")
    if cap["host_rule"]:
        lines.append(f"  宿主约束：{cap['host_rule']}")
    return "\n".join(lines)