"""P5-C 第一条：引擎已支持的构件要有**真实的设计控制**（宿主 / 尺寸 / 材质）。

这一层的意义（`P5-扩展建筑设计表达.md`）：栏杆、雨棚、檐口这类构件引擎早已实现，
但图纸侧**没有任何一条通路**能表达它们 —— 写进 ``components`` 的实例被静默丢弃
（``outcome: dropped``），模型不知道该写什么宿主写法，于是"能力已实现却无人派发"。

这里钉住两件事：

1. **宿主写法宽容**：图纸能用的几种写法都要真的解析得到（提示词教给模型的标准
   写法必须能用，否则模型只能靠反复重出来试）；
2. **一个设计变量⇒一个实体差异**：``size`` 改了要真的落到实体上，且只影响该类型。

判据用"两次编译只差一个设计变量，逐字段比对实体"，不是"实体存在" ——
存在但没差异，和没派发通道，在报告里长得一样。
"""
import json

import pytest

from app.agent.compiler import compile_design
from app.agent.generation.architecture import normalize_architecture_plan

_BASE = {
    "massing": {"shape": "rectangular", "width": 12, "depth": 9, "floors": 2},
    "facades": {
        face: {
            "bays": 3,
            "ground_pattern": (
                ["door", "window", "window"] if face == "front" else ["window"] * 3
            ),
            "upper_pattern": ["window"] * 3,
        }
        for face in ("front", "back", "left", "right")
    },
}


def _compile(components, message="两层带阳台的房子"):
    plan = normalize_architecture_plan(
        {**_BASE, "components": list(components)}, message,
    )
    return compile_design(plan, user_message=message)


def _entity(result, component_type):
    for item in result.blueprint["geometry"]["components"]:
        if item.get("type") == component_type:
            return item
    return None


def _instance(result, index=0):
    entries = (result.stats.get("instance_overrides") or {}).get("instance_entities") or []
    return next((item for item in entries if item["index"] == index), None)


# ── 宿主写法：提示词教出去的每一种都必须解析得到 ────────────────────


@pytest.mark.parametrize(
    "host",
    [
        "wall_front_1:floor_1:door:1",  # 派生链自己的开口槽位 id（提示词标准写法）
        "wall_front_1",                 # 骨架墙 id
        "main_L1_front",                # 体量 + 楼层 + 面
        "door_planned_01",              # 已落地��门窗实体 id
    ],
)
def test_every_documented_canopy_host_spelling_resolves(host):
    """🔴 之前这些写法**全部**落空：分支要求派生结果带 ``parentOpening``，
    而派生链从不写这个字段 —— 于是模型无论怎么写都被丢弃。"""

    result = _compile([{"type": "canopy", "host": host, "size": {"depth": 1.5}}])
    assert _instance(result)["outcome"] == "compiled", host
    canopy = _entity(result, "canopy")
    assert canopy and canopy["parentWall"] == "wall_front_1", host


@pytest.mark.parametrize(
    ("host", "expected_y"),
    [
        ("main", 6.6),          # 不写层 ⇒ 体量顶层
        ("railing:main", 6.6),  # railing_slots 的 id 前缀同形
        ("main_L2", 6.6),
        ("main_L1", 3.4),
        ("railing:main:1", 3.4),  # 冒号后是层号，不是出现序
    ],
)
def test_every_documented_railing_host_spelling_resolves(host, expected_y):
    result = _compile([{"type": "railing", "host": host, "size": {"height": 1.1}}])
    assert _instance(result)["outcome"] == "compiled", host
    railing = _entity(result, "railing")
    assert railing["path"][0][1] == pytest.approx(expected_y), host


def test_unresolvable_host_is_dropped_and_recorded():
    """宁缺毋错：宿主解析不到就整条丢弃**并留痕**，"没做到"不能长得像"没查"。"""

    result = _compile([{"type": "canopy", "host": "no_such_wall"}])
    entry = _instance(result)
    assert entry["outcome"] == "dropped"
    assert entry["entity_id"] is None
    # 丢弃必须**两处**都留痕：`instance_entities` 给履约层定位到第几条，
    # `summary()["instance_dropped"]` 给模型通道看（stats 里没有这个平铺键，
    # 它挂在 stats["instance_overrides"]["dropped"] 上）。
    assert entry["declared_host"] == "no_such_wall"
    assert result.summary()["instance_dropped"] == ["canopy:no_such_wall"]


# ── 一个设计变量 ⇒ 一个实体差异 ──────────────────────────────────


def test_canopy_depth_is_the_only_entity_difference():
    shallow = _entity(_compile([{"type": "canopy", "host": "wall_front_1", "size": {"depth": 1.2}}]), "canopy")
    deep = _entity(_compile([{"type": "canopy", "host": "wall_front_1", "size": {"depth": 2.4}}]), "canopy")
    assert shallow["depth"] == pytest.approx(1.2)
    assert deep["depth"] == pytest.approx(2.4)
    #除depth 外逐字段相同 —— 差异必须**只**来自那一个设计变量。
    assert {k: v for k, v in shallow.items() if k != "depth"} == {
        k: v for k, v in deep.items() if k != "depth"
    }


def test_railing_height_is_the_only_entity_difference():
    low = _entity(_compile([{"type": "railing", "host": "main", "size": {"height": 1.1}}]), "railing")
    high = _entity(_compile([{"type": "railing", "host": "main", "size": {"height": 1.4}}]), "railing")
    assert low["height"] == pytest.approx(1.1)
    assert high["height"] == pytest.approx(1.4)
    assert low["path"] == high["path"], "改高度不该动路径"


def test_railing_path_comes_from_the_volume_not_the_drawing():
    """🔴 ``path`` 是世界坐标：图纸不写它，编译器按体量边界算。

    模型算不出体量边界在哪，写出来的栏杆会飘在空中或跨过整栋楼。
    """

    railing = _entity(_compile([{"type": "railing", "host": "main", "size": {}}]), "railing")
    xs = sorted({point[0] for point in railing["path"]})
    zs = sorted({point[2] for point in railing["path"]})
    assert xs == [0.0, 12.0], xs          # 体量 0..12
    assert zs == [0.0, 9.0], zs         # 体量 0..9
    assert len(railing["path"]) >= 2


def test_no_instance_means_no_new_component():
    """没有显式实例时不得凭空多出雨棚/栏杆（派发通道不许变成无条件派生）。"""

    result = _compile([])
    assert _entity(result, "canopy") is None
    assert _entity(result, "railing") is None


def test_instance_binding_never_leaves_a_dangling_material_reference():
    mats = set(_compile([{"type": "railing", "host": "main", "material_role": "frame"}]).blueprint["materials"])
    used = {
        item.get("material")
        for item in _compile([{"type": "railing", "host": "main", "material_role": "frame"}])
        .blueprint["geometry"]["components"]
        if item.get("material")
    }
    assert not used - mats


def test_repeated_compile_is_stable():
    """确定性编译：同输入必须逐字节相同（否则"重复编译稳定"这条验收无从谈起）。"""

    plan = {"type": "railing", "host": "main", "size": {"height": 1.2}}
    first = json.dumps(_compile([plan]).blueprint, sort_keys=True, ensure_ascii=False)
    second = json.dumps(_compile([plan]).blueprint, sort_keys=True, ensure_ascii=False)
    assert first == second