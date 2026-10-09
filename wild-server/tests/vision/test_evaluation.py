"""P7-B：视觉评价的可判代理指标。

这一层最容易出的错不是"算错"，而是**装作算过了**。所以测试钉的是判据的边界，
不是happy path：

1. **反例必红** —— 每条判据都要有一组"确实有问题"的输入让它翻 ``needs_review``。
   只测正常样例的测试等于没测：判据写死了返回 ``ok`` 也能全绿。
2. **事实源一致** —— 字段名、材质引用位、贴图槽位一律对着
   ``storage/knowledge_base/schema.json`` 核；体量数对着设计文档核。
   凭印象写字段名（本模块初版就写错了两处）会让判据**静默失效**：
   恒为 0、恒为 missing，但测试照样绿。
3. **不假装做视觉判断** —— proxy 只输出能从字段算出来的东西；
   人工评价空模板 ``complete=False``，合并结果不算完成。
"""
import copy
import json
from pathlib import Path

import pytest

from app.agent.vision import evaluation
from app.agent.vision.evaluation import (
    _MATERIAL_REF_FIELDS,
    _RHYTHM_GAP_RATIO,
    _RHYTHM_MIN_GAP,
    _TEXTURE_SLOTS,
    CONFIDENCE_LEVELS,
    STATUSES,
    VISIBLE_CRITERIA,
    entrance_legibility,
    facade_rhythm,
    human_review_template,
    massing_hierarchy,
    material_harmony,
    merge_evaluation,
    proxy_evaluate,
)


# ── 测试夹具：一栋 14×10 两层小楼（与 P7-A 渲染基线同型）──────────────────

def _wall(wall_id, x0, z0, x1, z1, y0=0.0, y1=3.2):
    return {"type": "wall", "id": wall_id, "from": [x0, y0, z0], "to": [x1, y1, z1],
            "thickness": 0.24, "material": "wall_finish"}


def _window(win_id, wall_id, offset):
    return {"id": win_id, "type": "window", "parentWall": wall_id,
            "from": [offset, 0.9, 0.0], "width": 1.5, "height": 1.5}


@pytest.fixture
def house() -> dict:
    """四面外墙 + 每面 3 扇等间距窗 + front 面 1 樘门 + 1 块屋面。

    门**不参与**节奏统计（判据只收 window/balcony —— 门宽 1.0m 与窗宽 1.5m
    不同，中心间距天然对不齐，混算会把正常立面判成间距0.75/4.0）。
    门的位置由``entrance_legibility`` 单独管。
    """

    elements = [
        _wall("wall_front_1", 0, 0, 14, 0), _wall("wall_right_1", 14, 0, 14, 10),
        _wall("wall_back_1", 14, 10, 0, 10), _wall("wall_left_1", 0, 10, 0, 0),
        _wall("wall_front_2", 0, 0, 14, 0, 3.2, 6.4), _wall("wall_right_2", 14, 0, 14, 10, 3.2, 6.4),
        _wall("wall_back_2", 14, 10, 0, 10, 3.2, 6.4), _wall("wall_left_2", 0, 10, 0, 0, 3.2, 6.4),
        {"type": "roof", "id": "roof_01", "roofType": "gable", "position": [7.0, 6.4, 5.0],
         "material": "roof"},
    ]
    components = []
    for wall_id in ("wall_front_1", "wall_right_1", "wall_back_1", "wall_left_1",
                    "wall_front_2", "wall_right_2", "wall_back_2", "wall_left_2"):
        for i in range(3):
            components.append(_window(f"win_{wall_id}_{i}", wall_id, 2.0 + i * 4.0))
    components.append({"id": "door_1", "type": "door", "parentWall": "wall_front_1",
                       "from": [1.8, 0.0, 0.0], "width": 1.0, "height": 2.27,
                       "frameMaterial": "metal", "leafMaterial": "wood"})
    components[0]["frameMaterial"] = "metal"
    components[0]["glassMaterial"] = "glass"
    materials = {
        "wall_finish": {"baseColor": [0.84, 0.82, 0.78], "roughness": 0.72,
                        "metallic": 0.0, "albedo": 1.0, "lightingCondition": "D65_noon"},
        "roof": {"baseColor": [0.27, 0.28, 0.30], "roughness": 0.76, "metallic": 0.0,
                 "albedo": 1.0, "lightingCondition": "D65_noon"},
    }
    return {"meta": {"name": "两层小楼", "type": "building", "version": "1.1"},
            "geometry": {"elements": elements, "components": components},
            "materials": materials, "assets": {}, "behaviors": {}}


# ── 闭集：评价项/状态/置信度 ───────────────────────────────────────────

def test_visible_criteria_is_a_closed_set():
    """评价项是 P7 第 2 条限定的可见问题集合，不是"能算什么就评什么"。"""

    assert VISIBLE_CRITERIA == (
        "massing_hierarchy", "entrance_legibility", "facade_rhythm", "material_harmony",
    )
    assert len(set(VISIBLE_CRITERIA)) == len(VISIBLE_CRITERIA)


def test_statuses_separates_missing_from_needs_review():
    """``missing``（数据不足）与 ``needs_review``（确有问题）必须不同义。

    混成一个的后果：把"没数据"当成"设计有问题"，让修订去改一个没问题的设计。
    """

    assert STATUSES == ("ok", "needs_review", "missing")
    assert set(STATUSES) != {"ok", "bad"}


def test_confidence_levels_is_closed():
    assert CONFIDENCE_LEVELS == ("high", "medium", "low")


# ── 外墙判定：内墙不能混进立面统计 ────────────────────────────────────

def test_interior_wall_is_not_counted_as_exterior(house):
    """内墙 0 开口是正常的。混进统计会让每栋带隔墙的房子都被误判。"""

    bp = copy.deepcopy(house)
    bp["geometry"]["elements"].append(_wall("wall_inner_1", 7.0, 0.0, 7.0, 10.0))
    exterior = evaluation._exterior_wall_ids(bp)
    assert "wall_inner_1" not in exterior
    assert len(exterior) == 8
    # 加一道 0 开口的内墙，统计口径不变。
    before = facade_rhythm(house)
    after = facade_rhythm(bp)
    assert after["status"] == before["status"] == "ok"
    assert set(after["evidence"]["gaps"]) == set(before["evidence"]["gaps"])


def test_exterior_wall_uses_own_footprint_not_distance_from_origin(house):
    """外墙判据不能是"离原点最近/最远" —— 建筑可以建在任意坐标上。

    整栋楼平移 500m 后，外墙集合必须完全不变。
    """

    moved = copy.deepcopy(house)
    for item in moved["geometry"]["elements"]:
        for key in ("from", "to"):
            if item.get(key):
                item[key] = [item[key][0] + 500.0, item[key][1], item[key][2] + 500.0]
        if item.get("position"):
            item["position"] = [item["position"][0] + 500.0, item["position"][1],
                                item["position"][2] + 500.0]
    assert evaluation._exterior_wall_ids(moved) == evaluation._exterior_wall_ids(house)


def test_wall_with_fewer_than_two_windows_is_skipped(house):
    """1 扇窗没有节奏可言，不该进统计（否则间距样本为 0）。"""

    bp = copy.deepcopy(house)
    bp["geometry"]["components"] = [
        c for c in bp["geometry"]["components"]
        if not (c.get("type") == "window"
                and c.get("parentWall") in {"wall_back_1", "wall_back_2"}
                and c["id"] != "win_wall_back_1_0")
    ]
    result = facade_rhythm(bp)
    assert "wall_back_1" not in result["evidence"]["gaps"]
    assert "wall_back_2" not in result["evidence"]["gaps"]
    assert "wall_front_1" in result["evidence"]["gaps"]


def test_all_walls_have_one_window_is_missing_not_ok(house):
    """每面墙都只有 1 扇窗 ⇒ 无从谈节奏，是数据不足不是"节奏没问题"。"""

    bp = copy.deepcopy(house)
    bp["geometry"]["components"] = [
        c for c in bp["geometry"]["components"]
        if not (c.get("type") == "window" and c["id"] != f"win_{c['parentWall']}_0")
    ]
    # 逐墙确认真的只剩 1 扇（守卫测试自己别写错）
    from collections import Counter
    counts = Counter(c["parentWall"] for c in bp["geometry"]["components"]
                     if c.get("type") == "window")
    assert set(counts.values()) == {1}, counts
    assert facade_rhythm(bp)["status"] == "missing"


def test_door_does_not_disturb_window_rhythm(house):
    """🔴 门不参与节奏统计（门宽 1.0m ≠ 窗宽 1.5m，中心天然对不齐）。

    把门挪到与第一扇窗完全重叠的位置，节奏判定也必须不变 ——
    这条钉住"门被排除"，否则"门+两窗"的正常立面会被误判成间距 0.75/4.0。
    """

    baseline = facade_rhythm(house)
    moved = copy.deepcopy(house)
    for item in moved["geometry"]["components"]:
        if item.get("id") == "door_1":
            item["from"] = [2.0, 0.0, 0.0]  # 与 win_wall_front_1_0 完全重叠
    after = facade_rhythm(moved)
    assert after["evidence"]["gaps"] == baseline["evidence"]["gaps"]
    assert after["status"] == baseline["status"] == "ok"


def test_coincident_windows_do_not_crash(house):
    """🔴 两扇窗完全重合时最小间距是 0，做分母会 ZeroDivisionError 打断整个评价。"""

    bp = copy.deepcopy(house)
    coincident = [
        {"id": f"win_dup_{i}", "type": "window", "parentWall": "wall_front_1",
         "from": [2.0, 0.9, 0.0], "width": 1.5, "height": 1.5} for i in range(2)
    ]
    bp["geometry"]["components"] = [
        c for c in bp["geometry"]["components"]
        if not (c.get("type") == "window" and c.get("parentWall") == "wall_front_1")
    ] + coincident
    result = facade_rhythm(bp)
    assert result["status"] in {"ok", "needs_review"}
    assert 0.0 in result["evidence"]["gaps"]["wall_front_1"]


# ── 反例必红：facade_rhythm ───────────────────────────────────────────

def test_rhythm_flags_windows_clustered_at_one_end(house):
    """🔴 真正的节奏问题：同一面墙上窗全挤在一端。

    跨墙密度比**看不见**这个问题（同型房子每面墙都是 3 个洞，密度必然有差），
    只有"同墙内间距"能判出来。
    """

    bp = copy.deepcopy(house)
    clustered = [
        {"id": "win_c0", "type": "window", "parentWall": "wall_front_1",
         "from": [0.3, 0.9, 0.0], "width": 1.5, "height": 1.5},
        {"id": "win_c1", "type": "window", "parentWall": "wall_front_1",
         "from": [0.9, 0.9, 0.0], "width": 1.5, "height": 1.5},
        {"id": "win_c2", "type": "window", "parentWall": "wall_front_1",
         "from": [12.0, 0.9, 0.0], "width": 1.5, "height": 1.5},
    ]
    bp["geometry"]["components"] = [
        c for c in bp["geometry"]["components"]
        if not (c.get("type") == "window" and c.get("parentWall") == "wall_front_1")
    ] + clustered
    result = facade_rhythm(bp)
    assert result["status"] == "needs_review"
    assert "wall_front_1" in result["evidence"]["offenders"]
    assert result["evidence"]["gapRatios"]["wall_front_1"] > _RHYTHM_GAP_RATIO
    # 其它墙仍然均匀 —— offender 是逐墙给出的，不是整栋一刀切。
    assert "wall_back_1" not in result["evidence"]["offenders"]


def test_rhythm_passes_on_evenly_spaced_windows(house):
    """同型房子不该被误报（守卫阈值没设得过严）。"""

    result = facade_rhythm(house)
    assert result["status"] == "ok"
    assert result["evidence"]["offenders"] == []
    # 夹具窗中心 2.75/6.75/10.75 ⇒ 窗距 4.0/4.0。
    assert result["evidence"]["gaps"]["wall_front_1"] == [4.0, 4.0]


def test_rhythm_does_not_penalize_different_wall_lengths(house):
    """🔴 长墙 3 洞 / 短墙 3 洞是正常的，不能因为"密度不同"就判不均。

    这是初版跨墙密度比判据的核心错误：14m 与 10m 的墙同样 3 个洞，
    密度必然 0.214 vs 0.300，差0.086 —— 会被误报。
    """

    result = facade_rhythm(house)
    assert result["status"] == "ok"
    # 两种长度的墙都参与了统计，说明口径确实是"逐墙看间距"而不是"跨墙比密度"。
    assert len(result["evidence"]["gaps"]) == 8


def test_rhythm_flags_two_windows_clustered_even_with_equal_gaps(house):
    """🔴 只有 2 扇窗时相对差**恒为 0**（间距列表长度 1，max==min）。

    "两扇窗挤在 0.2m 内"这种明显问题光靠相对差判不出来 ——
    这是拿真实渲染基线（``wall_front_1`` 只有 2 扇窗）实测出来的盲区，
    所以必须有绝对下限这条判据。
    """

    bp = copy.deepcopy(house)
    # 只留 2 扇窗，且中心间距 0.2m（相对差必然是 0）。
    # 中心 = from[0] + width/2 ⇒ 间距 == 两个 from 的差，width 相同会约掉。
    bp["geometry"]["components"] = [
        c for c in bp["geometry"]["components"]
        if not (c.get("type") == "window" and c.get("parentWall") == "wall_front_1")
    ] + [
        {"id": "win_t0", "type": "window", "parentWall": "wall_front_1",
         "from": [2.0, 0.9, 0.0], "width": 1.5, "height": 1.5},
        {"id": "win_t1", "type": "window", "parentWall": "wall_front_1",
         "from": [2.2, 0.9, 0.0], "width": 1.5, "height": 1.5},
    ]
    result = facade_rhythm(bp)
    assert result["evidence"]["gaps"]["wall_front_1"] == [0.2], (
        f"夹具前提：只有一个间距，实际 {result['evidence']['gaps']['wall_front_1']}")
    assert result["evidence"]["gapRatios"]["wall_front_1"] == 0.0, "相对差确实是 0"
    assert result["status"] == "needs_review", "绝对下限没生效"
    assert "wall_front_1" in result["evidence"]["offenders"]


def test_rhythm_min_gap_does_not_fire_on_normal_spacing(house):
    """绝对下限不能误伤正常立面（基准 4.0m 间距远高于 0.6m）。"""

    result = facade_rhythm(house)
    assert result["status"] == "ok"
    assert min(min(gaps) for gaps in result["evidence"]["gaps"].values()) > _RHYTHM_MIN_GAP


def test_rhythm_without_walls_is_missing_not_ok(house):
    """没有墙是**数据不足**，不是"节奏没问题"。"""

    bp = copy.deepcopy(house)
    bp["geometry"]["elements"] = []
    assert facade_rhythm(bp)["status"] == "missing"


def test_rhythm_degrades_visibly_when_no_axis_aligned_exterior(house):
    """全是斜墙判不出外墙时，要**说明口径退化了**，不能静悄悄换算法。"""

    bp = copy.deepcopy(house)
    for wall in bp["geometry"]["elements"]:
        if wall.get("type") == "wall":
            wall["to"] = [wall["to"][0] + 0.5, wall["to"][1], wall["to"][2] + 0.5]
    result = facade_rhythm(bp)
    if result["status"] != "missing":
        assert "退化" in result["evidence"]["scope"]


# ── 反例必红：entrance_legibility ─────────────────────────────────────

def test_entrance_flags_door_only_on_interior_wall(house):
    """入口落在内墙上 = 没表达入口，必红。"""

    bp = copy.deepcopy(house)
    bp["geometry"]["components"] = [
        c for c in bp["geometry"]["components"] if c.get("type") != "door"
    ]
    bp["geometry"]["elements"].append(_wall("wall_inner_1", 7.0, 0.0, 7.0, 10.0))
    bp["geometry"]["components"].append(
        {"id": "door_inner", "type": "door", "parentWall": "wall_inner_1",
         "from": [2.0, 0.0, 0.0], "width": 0.9, "height": 2.1})
    result = entrance_legibility(bp)
    assert result["status"] == "needs_review"
    assert result["evidence"]["exteriorDoorCount"] == 0


def test_entrance_flags_multiple_doors(house):
    bp = copy.deepcopy(house)
    bp["geometry"]["components"].append(
        {"id": "door_2", "type": "door", "parentWall": "wall_front_2",
         "from": [1.8, 0.0, 0.0], "width": 1.0, "height": 2.27})
    result = entrance_legibility(bp)
    assert result["status"] == "needs_review"
    assert "唯一性" in result["detail"]


def test_entrance_without_any_door_is_missing(house):
    bp = copy.deepcopy(house)
    bp["geometry"]["components"] = [
        c for c in bp["geometry"]["components"] if c.get("type") != "door"
    ]
    assert entrance_legibility(bp)["status"] == "missing"


def test_canopy_on_entrance_does_not_turn_ok_into_needs_review(house):
    """🔴 雨棚是**正面**信息。初版把它塞进"问题列表"，装了雨棚反而被报待复查。"""

    bp = copy.deepcopy(house)
    bp["geometry"]["components"].append(
        {"id": "canopy_1", "type": "canopy", "parentWall": "wall_front_1",
         "from": [1.8, 2.4, 0.0], "width": 1.8, "depth": 1.2, "thickness": 0.12})
    result = entrance_legibility(bp)
    assert result["evidence"]["entranceCanopy"] is True
    assert result["status"] == "ok"
    assert "雨棚" in result["detail"]


def test_entrance_does_not_hardcode_wall_id_prefix(house):
    """🔴 "主立面"不能靠 ``wall_front`` 前缀判定 —— 墙 id 命名是编译器内部约定。

    把所有墙改名成无语义的 hash 之后，判定结果必须完全不变。
    """

    bp = copy.deepcopy(house)
    mapping = {}
    for i, item in enumerate(bp["geometry"]["elements"]):
        if item.get("type") == "wall":
            mapping[item["id"]] = f"w{i:04x}"
    for item in bp["geometry"]["elements"]:
        if item.get("type") == "wall":
            item["id"] = mapping[item["id"]]
    for item in bp["geometry"]["components"]:
        if item.get("parentWall") in mapping:
            item["parentWall"] = mapping[item["parentWall"]]
    assert entrance_legibility(bp)["status"] == entrance_legibility(house)["status"]


# ── 反例必红：massing_hierarchy（事实源在设计文档，不在蓝图）────────────

def test_massing_is_missing_without_design_document(house):
    """🔴 体量数不在蓝图里。初版读 ``blueprint["volumes"]`` ⇒ 恒为 missing。"""

    result = massing_hierarchy(house)
    assert result["status"] == "missing"
    assert "volumes" in result["detail"]


def test_massing_ignores_volumes_key_in_blueprint(house):
    """蓝图里就算塞了 ``volumes``，也不能被当成体量事实源（那是第二份数据）。"""

    bp = copy.deepcopy(house)
    bp["volumes"] = [{"id": "v1"}, {"id": "v2"}, {"id": "v3"}]
    assert massing_hierarchy(bp)["status"] == "missing"


def test_massing_flags_one_roof_over_many_volumes(house):
    """一块屋顶盖三个体量 ⇒ 体量层次在渲染上消失，必红。"""

    doc = {"decisions": {"volumes": [{"id": "v1"}, {"id": "v2"}, {"id": "v3"}]}}
    result = massing_hierarchy(house, doc)
    assert result["status"] == "needs_review"
    assert result["evidence"] == {"volumes": 3, "roofs": 1}


def test_massing_passes_when_roof_count_covers_volumes(house):
    doc = {"decisions": {"volumes": [{"id": "v1"}]}}
    assert massing_hierarchy(house, doc)["status"] == "ok"


def test_massing_passes_with_one_volume_even_with_few_roofs(house):
    """单体量不该因为屋面少被报（compiler 允许无槽位单块屋面）。"""

    bp = copy.deepcopy(house)
    bp["geometry"]["elements"] = [
        e for e in bp["geometry"]["elements"] if e.get("type") != "roof"
    ]
    doc = {"decisions": {"volumes": [{"id": "v1"}]}}
    assert massing_hierarchy(bp, doc)["status"] == "ok"


# ── 反例必红：material_harmony（字段名必须对着 schema）────────────────

def test_material_ref_fields_exist_in_schema(house):
    """🔴 材质引用位是 schema 里的真名。写错 = 那一类构件的材质凭空消失。"""

    schema_path = Path(__file__).resolve().parents[2] / "storage" / "knowledge_base" / "schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    defs = schema["$defs"]
    declared = {
        prop
        for definition in defs.values()
        for prop in (definition.get("properties") or {})
    }
    unknown = [f for f in _MATERIAL_REF_FIELDS if f not in declared]
    assert unknown == [], f"这些材质引用字段在 schema 里不存在：{unknown}"


def test_texture_slots_exist_in_schema():
    """🔴 初版写 ``textureSet``，schema 里根本没这个字段 ⇒ 贴图数恒为 0 且不报错。"""

    schema_path = Path(__file__).resolve().parents[2] / "storage" / "knowledge_base" / "schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    textures = schema["$defs"]["materialDef"]["properties"]["textures"]["properties"]
    assert set(_TEXTURE_SLOTS) <= set(textures), (
        f"贴图槽位与 schema 不一致：多出 {set(_TEXTURE_SLOTS) - set(textures)}"
    )


def test_material_harmony_counts_door_and_window_material_slots(house):
    """🔴 只读 ``material`` 会把整扇门窗的材质漏掉。

    本夹具的门有 ``frameMaterial``/``leafMaterial``、窗有 ``frameMaterial``/``glassMaterial``；
    只读 ``material`` 只能看到 wall_finish + roof = 2 种。
    """

    result = material_harmony(house)
    names = result["evidence"]["materials"]
    assert "wood" in names, "门的 leafMaterial 没被统计"
    assert "glass" in names, "窗的 glassMaterial 没被统计"
    assert "metal" in names, "门窗的 frameMaterial 没被统计"
    # 正因为补齐了引用位，种类数才够 3、不该误报"层次过弱"。
    assert result["status"] == "ok"
    assert result["evidence"]["materialCount"] >= 3


def test_material_harmony_flags_too_few_materials(house):
    """只有 1 种材质 ⇒ 没有层次，必红。"""

    bp = copy.deepcopy(house)
    for item in bp["geometry"]["elements"] + bp["geometry"]["components"]:
        for field in _MATERIAL_REF_FIELDS:
            item.pop(field, None)
        item["material"] = "wall_finish"
    bp["materials"] = {"wall_finish": bp["materials"]["wall_finish"]}
    result = material_harmony(bp)
    assert result["status"] == "needs_review"
    assert "层次" in result["detail"]


def test_material_harmony_flags_too_many_materials(house):
    """9 种以上 ⇒ 拼贴感，必红。"""

    bp = copy.deepcopy(house)
    for i in range(9):
        bp["geometry"]["components"].append(
            {"id": f"light_{i}", "type": "light", "material": f"m{i}",
             "parentWall": "wall_front_1", "from": [1.0, 2.5, 0.0]})
        bp["materials"][f"m{i}"] = dict(bp["materials"]["wall_finish"])
    result = material_harmony(bp)
    assert result["status"] == "needs_review"
    assert "拼贴" in result["detail"]


def test_material_harmony_reports_textured_materials(house):
    """贴图绑定要按 schema 真名 ``textures.*`` 认，且只算真绑了槽位的。"""

    bp = copy.deepcopy(house)
    bp["materials"]["wall_finish"]["textures"] = {"baseColor": {"data": "abc"}}
    bp["materials"]["roof"]["textures"] = {}  # 空对象不算绑定
    result = material_harmony(bp)
    assert result["evidence"]["textured"] == ["wall_finish"]


def test_material_harmony_without_refs_is_missing(house):
    """所有材质引用位都空 ⇒ missing（数据不足），不是 needsReview。"""

    bp = copy.deepcopy(house)
    for item in bp["geometry"]["elements"] + bp["geometry"]["components"]:
        for field in _MATERIAL_REF_FIELDS:
            item.pop(field, None)
    assert material_harmony(bp)["status"] == "missing"


# ── proxy 汇总：只输出可判结论，不夹带视觉判断 ─────────────────────────

def test_proxy_covers_every_visible_criterion_exactly_once(house):
    result = proxy_evaluate(house)
    assert [item["criterion"] for item in result["items"]] == list(VISIBLE_CRITERIA)
    assert result["criteria"] == list(VISIBLE_CRITERIA)


def test_proxy_partitions_criteria_into_exactly_one_bucket(house):
    """每个评价项必须落在 ok / needsReview / missing 中的**恰好一个**桶里。"""

    result = proxy_evaluate(house)
    buckets = result["ok"] + result["needsReview"] + result["missing"]
    assert sorted(buckets) == sorted(VISIBLE_CRITERIA), "有评价项没进任何桶，或进了多个桶"
    assert not (set(result["ok"]) & set(result["needsReview"]))


def test_proxy_reports_missing_separately_from_needs_review(house):
    """没有设计文档时，massing 是 missing 而**不是** needsReview。"""

    result = proxy_evaluate(house)
    assert result["missing"] == ["massing_hierarchy"]
    assert result["needsReview"] == []


def test_proxy_massing_becomes_judged_once_document_is_given(house):
    doc = {"decisions": {"volumes": [{"id": "v1"}]}}
    result = proxy_evaluate(house, doc)
    assert "massing_hierarchy" in result["ok"]
    assert result["missing"] == []


def test_proxy_evidence_is_numbers_and_ids_not_adjectives(house):
    """🔴 proxy 每一项都必须带可复核的 evidence（数字/实体 id）。

    没有 evidence 的 needs_review 只是一句"我觉得丑"，不能进修订队列。
    """

    result = proxy_evaluate(house)
    for item in result["items"]:
        assert set(item) >= {"criterion", "status", "detail", "confidence"}, item
        assert item["confidence"] in CONFIDENCE_LEVELS
        if item["status"] == "needs_review":
            evidence = item.get("evidence")
            assert evidence, f"{item['criterion']} 报了 needs_review 却没有 evidence"


def test_proxy_never_claims_to_have_seen_the_render(house):
    """🔴 proxy 没看过任何一张图，结论里不许出现视觉判断词。

    只扫 ``items``（判据结论），不扫 ``note`` —— note 里写"构图气质等仍需人工看图"
    是在**声明没做**，那是诚实的免责声明，不是越界。
    """

    result = proxy_evaluate(house)
    assert result["source"] == "proxy"
    for item in result["items"]:
        blob = json.dumps(
            {"detail": item["detail"], "evidence": item.get("evidence")},
            ensure_ascii=False,
        )
        for word in ("看起来", "视觉上", "构图", "气质", "渲染里", "截图里", "好看", "丑"):
            assert word not in blob, (
                f"{item['criterion']} 的结论里混进了视觉判断：{word} —— "
                f"proxy 只许输出能从字段算出来的东西"
            )


def test_proxy_is_deterministic(house):
    """同一份蓝图跑两次结果必须逐字相同 —— 否则不能当门禁用。"""

    assert json.dumps(proxy_evaluate(house), sort_keys=True) == json.dumps(
        proxy_evaluate(copy.deepcopy(house)), sort_keys=True)


def test_proxy_tolerates_malformed_input():
    """空/残缺蓝图不许抛异常：返回 missing 也是一种合法答案。"""

    for broken in ({}, {"geometry": None}, {"geometry": {"elements": None, "components": None}}):
        result = proxy_evaluate(broken)
        assert len(result["items"]) == len(VISIBLE_CRITERIA)
        assert result["needsReview"] == [], "残缺蓝图只该 missing，不该 needsReview"


# ── 人工评价：空模板不算完成 ───────────────────────────────────────────

def test_human_template_is_not_complete(house):
    """🔴 P7 第 1 条：模型没有图像输入能力时用人工评价，**不假装**。

    空模板必须 complete=False，否则上层会以为"视觉已确认"。
    """

    manifest = {"baselineVersion": "p7a.1", "glRenderer": "WebKit WebGL",
                "shots": [{"view": "front", "file": "front.png"}]}
    template = human_review_template(manifest, {"name": "两层小楼"})
    assert template["source"] == "human"
    assert template["complete"] is False
    assert template["criteria"] == list(VISIBLE_CRITERIA)
    assert len(template["template"]) == len(VISIBLE_CRITERIA)
    assert template["render"]["files"] == ["front.png"]
    for row in template["template"]:
        assert row["issues"] == [] and row["confidence"] == "" and row["status"] == ""


def test_human_template_carries_unmapped_material_count(house):
    """人工看图前必须知道材质有没有落到渲染上（否则看不出材质问题）。"""

    manifest = {"baselineVersion": "p7a.1", "glRenderer": "WebKit WebGL",
                "unmappedMaterials": 199, "shots": []}
    template = human_review_template(manifest, {})
    assert template["render"]["unmappedMaterials"] == 199


def test_merge_is_not_complete_while_human_template_is_blank(house):
    """🔴 proxy 全绿也不等于评价完成 —— 视觉判断仍缺人确认。"""

    proxy = proxy_evaluate(house)
    manifest = {"baselineVersion": "p7a.1", "shots": []}
    blank = human_review_template(manifest, {})
    merged = merge_evaluation(proxy, blank)
    assert merged["complete"] is False
    assert merged["blockedBy"] == ["human_review"]
    assert merge_evaluation(proxy, None)["complete"] is False


def test_merge_is_complete_only_after_human_fills_status(house):
    proxy = proxy_evaluate(house)
    filled = human_review_template({"shots": []}, {})
    for row in filled["template"]:
        row["status"] = "ok"
        row["confidence"] = "high"
        row["viewEvidence"] = ["front"]
    filled["complete"] = True
    merged = merge_evaluation(proxy, filled)
    assert merged["complete"] is True
    assert merged["blockedBy"] == []
