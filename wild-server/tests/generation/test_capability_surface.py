"""P6-B：可机械提取的引擎能力查询面。

这一层要回答"模型怎么知道引擎能做什么"。判据不是"提示词里写了多少字段"，而是：

1. **字段必须与真实事实源一致**（schema / 组件注册表）—— 漂移要能被发现；
2. **不能建第二份无人同步的白名单**（schema 加字段时查询面必须自动跟着变）；
3. **查询失败 / 无命中 / 引擎不支持是三个不同状态**（混成一个会让模型去请求
   实际不存在的能力，或把真不支持的能力当可用）。

人工维护的部分（坐标语义、宿主约束）允许有，但必须能看出它是人工的，
且键名与 schema 的 type 字面一致 —— 不一致就等于没有（静默失效）。
"""
import json

import pytest

from app.agent.generation import capability as capability_module
from app.agent.generation.capability import (
    _STATUSES,
    CAPABILITY_SURFACE_VERSION,
    capability_brief,
    capability_query,
    capability_surface,
    load_engine_schema,
)
from app.agent.generation.component.registry import COMPONENT_REGISTRY


# ── 与事实源一致 ──────────────────────────────────────────────────


def test_capability_fields_match_engine_schema():
    """🔴 字段/必填/枚举必须逐项来自 schema，不允许本地另抄一份。"""

    schema = load_engine_schema()
    assert schema, "引擎 schema 读不到 —— 整个查询面失效，测试必须先红在这"
    defs = schema["$defs"]
    for type_name, capability in capability_surface().items():
        source = capability["source"]["fields"]
        definition_name = source.rsplit(".", 1)[-1]
        definition = defs[definition_name]
        assert list(definition.get("required") or []) == capability["required"], type_name
        properties = set((definition.get("properties") or {}).keys())
        assert set(capability["fields"]) == properties, type_name


def test_enum_constraints_are_carried_through():
    """取值闭集要从 schema 带出来 —— 这类约束提示词最容易漏。"""

    roof = capability_query("roof")
    assert roof["status"] == "ok"
    assert "roofType" in roof["capability"]["fields"]
    assert roof["capability"]["fields"]["roofType"].get("enum")


def test_target_collection_matches_registry():
    """写进 elements 还是 components 是硬约束（写错会被校验器拒）。"""

    for type_name, config in COMPONENT_REGISTRY.items():
        result = capability_query(type_name)
        if result["status"] != "ok":
            continue
        expected = "elements" if (config.is_element or config.is_list is False) else "components"
        if config.is_element:
            expected = "elements"
        assert result["capability"]["target"] == expected, type_name


# ── 不建第二份白名单：schema 变 → 查询面跟着变 ─────────────────────


def test_surface_follows_schema_without_manual_edit(monkeypatch):
    """临时给 schema 加一个字段，查询面必须自动看到 —— 不许手工同步。"""

    schema = load_engine_schema()
    mutated = json.loads(json.dumps(schema, ensure_ascii=False))
    mutated["$defs"]["canopyComponent"]["properties"]["someNewKnob"] = {
        "type": "number", "exclusiveMinimum": 0,
    }
    monkeypatch.setattr(capability_module, "load_engine_schema", lambda **_: mutated, raising=True)
    monkeypatch.setattr(capability_module, "_capability_cache", None, raising=True)
    surface = capability_surface(refresh=True)
    assert "someNewKnob" in surface["canopy"]["optional"], "新字段没自动出现"
    assert "someNewKnob" in surface["canopy"]["fields"]

    # 还原成真实 schema再查一次：能力面必须回到"没有这个字段"。
    # 只在finally 里 refresh 是不够的 —— monkeypatch 的替换还挂着，
    # refresh 只会把 mutated 又算一遍。
    monkeypatch.undo()
    load_engine_schema(refresh=True)
    capability_surface(refresh=True)
    assert "someNewKnob" not in capability_surface()["canopy"]["optional"]


# ── 四态必须可区分 ────────────────────────────────────────────────


def test_ok_state_carries_capability():
    result = capability_query("canopy")
    assert result["status"] == "ok"
    assert result["capability"]["type"] == "canopy"
    assert result["source_version"] == CAPABILITY_SURFACE_VERSION


def test_not_found_lists_what_exists():
    result = capability_query("no_such_type")
    assert result["status"] == "not_found"
    assert "canopy" in result["available"], "查不到要说有什么，否则模型无从纠正"


def test_unsupported_is_distinct_from_not_found(monkeypatch):
    """🔴 注册表标了 implemented=False ⇒ unsupported，**不能**报 not_found。

    这两个混在一起的后果：模型会以为能力不存在而放弃，或反过来把真不支持的
    能力当成"再查查也许有"。
    """

    config = COMPONENT_REGISTRY["canopy"]
    monkeypatch.setattr(config, "implemented", False)
    result = capability_query("canopy", refresh=True)
    assert result["status"] == "unsupported"
    assert result["capability"]["implemented"] is False


def test_query_failed_is_distinct_from_empty(monkeypatch):
    """🔴 schema 读不到 ⇒ query_failed，**不能**报"查询成功但没有能力"。

    后者会让模型以为引擎什么类型都不支持，于是整轮设计全部退化。
    """

    monkeypatch.setattr(capability_module, "_schema_cache", None, raising=True)
    monkeypatch.setattr(capability_module, "_schema_load_error", None, raising=True)
    monkeypatch.setattr(
        capability_module, "load_engine_schema",
        lambda **_kwargs: None, raising=True,
    )
    result = capability_query("canopy", refresh=True)
    assert result["status"] == "query_failed"
    assert "available" not in result, "查询失败时不能给出能力清单"
    capability_surface(refresh=True)


def test_status_values_are_a_closed_set():
    """状态取值是闭集：新增状态要显式改这条，而不是悄悄多一个。"""

    assert _STATUSES == {"ok", "not_found", "unsupported", "query_failed"}


# ── 人工维护的语义部分必须可用且可追源 ────────────────────────────


def test_manual_semantics_are_present_and_sourced():
    for type_name in ("wall", "floor", "door", "window", "balcony", "railing"):
        capability = capability_query(type_name)["capability"]
        assert capability["coord_semantics"], f"{type_name} 缺坐标语义"
        assert "人工维护" in capability["source"]["semantics"]


def test_manual_semantics_keys_match_schema_type_literals():
    """🔴 语义表的键必须与 schema 的 type 字面一致 —— 不一致就是**静默失效**
    （表里写好了，但查询时永远读不到）。"""

    surface = capability_surface()
    for type_name in capability_module._COORD_SEMANTICS:
        assert type_name in surface, f"语义表里的 {type_name} 在 schema 里不存在"
    for type_name in capability_module._HOST_RULES:
        assert type_name in surface, f"宿主表里的 {type_name} 在 schema 里不存在"


def test_brief_is_compact_and_task_independent():
    """同一个类型换个说法查，结果必须相同（task 不参与判据）。"""

    first = capability_query("canopy", task="入口雨棚")
    second = capability_query("canopy", task="门厅遮雨")
    assert first["capability"] == second["capability"]
    brief = capability_brief("canopy")
    assert "parentWall" in brief
    assert len(brief) < 600, "能力摘要要能塞进提示词"


def test_brief_reports_status_for_unknown_type():
    assert "not_found" in capability_brief("no_such_type")


# ── 接进提示词：不接就是"实现了但无人派发" ────────────────────────


def test_capability_section_is_rendered_into_the_component_block_prompt():
    from app.agent.generation.architecture.design_blocks import BLOCK_BY_NAME
    from app.agent.generation.architecture.design_workflow import build_block_prompt

    prompt = build_block_prompt("BASE", BLOCK_BY_NAME["components"], {})
    assert "引擎能力" in prompt, "能力面没进提示词 = 模型无从知道引擎能做什么"
    assert "parentWall 必须指向有真实门窗的墙" in prompt, "canopy 的宿主约束没送到"
    assert "path 为世界坐标折线" in prompt, "railing 的坐标语义没送到"
    assert "parentRoof" in prompt, "cornice/chimney 的宿主字段没送到"


def test_capability_section_is_not_injected_into_unrelated_blocks():
    from app.agent.generation.architecture.design_blocks import BLOCK_BY_NAME
    from app.agent.generation.architecture.design_workflow import build_block_prompt

    for name in ("massing", "facade", "roof", "structure"):
        prompt = build_block_prompt("BASE", BLOCK_BY_NAME[name], {})
        assert "引擎能力" not in prompt, f"{name} 块不需要引擎能力，塞进去只是白占预算"


def test_capability_section_lists_components_only_not_elements():
    """元素类由骨架确定性派生，模型本轮不写 —— 列进来只是白占提示词预算。"""

    from app.agent.generation.architecture.design_blocks import BLOCK_BY_NAME
    from app.agent.generation.architecture.design_workflow import (
        format_capability_section,
    )

    section = format_capability_section(BLOCK_BY_NAME["components"])
    assert "primitive（" not in section, "primitive 是元素类，不该出现在构件清单"
    assert "canopy（写入 geometry.components）" in section


def test_capability_section_stays_within_prompt_budget():
    """🔴 能力信息不能挤掉真正要写的约束：给一个上限，超了这条测试就红。"""

    from app.agent.generation.architecture.design_blocks import BLOCK_BY_NAME
    from app.agent.generation.architecture.design_workflow import (
        format_capability_section,
    )

    section = format_capability_section(BLOCK_BY_NAME["components"])
    assert 0 < len(section) <= 2600, f"能力段 {len(section)} 字，超预算；先裁剪再谈完整"
    # 必填字段清单默认不展开（那是"要写哪些键"的另一层约束，由块契约负责）。
    assert "必填：" not in section


# ── 漂移检测：两表不一致要能被发现 ────────────────────────────────


def test_schema_and_registry_coverage_difference_is_visible():
    """schema 含全部元素类型，注册表只含设计侧可选构件 —— 差异必须是**已知的**。

    如果哪天 schema 里多出一个类型却没人注册，那才是漂移；这里把当前差异记下来，
    任何一方新增类型时这条断言都会提醒同步。
    """

    surface = set(capability_surface())
    registry = set(COMPONENT_REGISTRY)
    element_only = surface - registry
    assert element_only == {"beam", "dense_brick", "floor", "opening", "stair", "wall"}, (
        "schema 与注册表的差集变了：schema 新增/删除类型，或注册表漏登记。"
        "确认是有意为之后请更新这条断言。"
    )
    assert not registry - surface, (
        f"注册表登记了 {sorted(registry - surface)} 但 schema 里没有 —— "
        "引擎已经不支持了，注册表必须同步"
    )