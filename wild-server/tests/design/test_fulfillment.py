"""P4：设计履约验收（最终 Blueprint 是否兑现批准设计）。

这些用例全部跑**真实编译产物**，不用手写蓝图：设计文档 → `compile_document`
→ 在成品上逐条判定。这样"设计层 satisfied / 实体层 open"才是真的分叉，而不是
在假数据上验证假结论。
"""
import json
from pathlib import Path

from app.design.compilation import compile_document
from app.design.contracts import DesignConstraint
from app.design.fulfillment import (
    FULFILLMENT_VERSION,
    evaluate_fulfillment,
    fulfillment_line,
    fulfillment_summary,
)
from app.design.resolver import _stable_hash, build_design_document

_FIXTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures/design_trace_baseline.json").read_text(encoding="utf-8")
)["normalized_plan"]


def document(constraints=()):
    """用夹具建一份设计文档，并把**每条要求的原文片段真的写进 user_request**。

    🔴 不是形式：`merge_design_constraints` 会把 `source_quote` 不在用户原文里的
    `user_hard` 降级成 `check="manual"`（P2A 的红线：没有原文就不许当硬要求）。
    测试里偷懒写一句不存在的原文，全部要求都会被降级，履约结果自然是 needs_review。
    """
    plan = json.loads(json.dumps(_FIXTURE))  # 深拷贝：夹具是模块级共享的
    plan["design_constraints"] = list(constraints)
    quotes = "、".join(str(item.get("source_quote") or "") for item in constraints)
    request = f"生成一个两层 L 形别墅（{quotes}）" if quotes else "生成一个两层 L 形别墅"
    return build_design_document(plan, session_id="intent", source_request=request)


def blueprint_of(doc):
    return compile_document(doc).blueprint


def status_of(gaps, constraint_id):
    return next((gap.status for gap in gaps if gap.constraint_id == constraint_id), None)


def constraint(constraint_id, target, expected, *, quote=None, **updates):
    payload = {
        "id": constraint_id,
        "kind": "user_hard",
        "target": target,
        "expression": f"要求 {target} = {expected!r}",
        "source": "user_request",
        "source_quote": quote or str(expected),
        "check": "equals",
        "expected": expected,
    }
    payload.update(updates)
    return payload


def summary_of(doc, blueprint=None):
    return fulfillment_summary(
        evaluate_fulfillment(doc, blueprint if blueprint is not None else blueprint_of(doc), _stable_hash(doc)),
        design_hash=_stable_hash(doc),
    )


# ── 实例清单：实例索引 → 实体 id 映射（P4 收口）─────────────────────


def instance_document(instances, constraints=()):
    """在夹具方案上挂一份实例清单。

    夹具本身没有 ``components``（走配额派生），这里补上是为了走**实例覆盖**那条路 ——
    实例→实体映射只在 ``use_instance_list`` 为真时才有，测派生路径等于什么都没测。
    """

    plan = json.loads(json.dumps(_FIXTURE))
    plan["components"] = list(instances)
    plan["design_constraints"] = list(constraints)
    quotes = "、".join(str(item.get("source_quote") or "") for item in constraints)
    request = f"生成一个两层 L 形别墅（{quotes}）" if quotes else "生成一个两层 L 形别墅"
    return build_design_document(plan, session_id="intent", source_request=request)


def instance_gaps(doc, blueprint=None, compiled=None):
    """跑真实编译并把映射喂进履约（与 `validation/workflow.py` 的调用姿势一致）。"""

    result = compiled if compiled is not None else compile_document(doc)
    entities = list(
        (result.stats.get("instance_overrides") or {}).get("instance_entities") or []
    )
    return evaluate_fulfillment(
        doc,
        result.blueprint if blueprint is None else blueprint,
        _stable_hash(doc),
        entities,
    )


def test_instance_type_requirement_is_verified_against_the_produced_entity():
    """实例的类型要求有了映射就不该再 needs_review —— 要真判出满足/不满足。"""

    doc = instance_document(
        [{"type": "balcony", "host": "wall_front_2_1", "size": {"width": 3.6, "depth": 1.4}}],
        [constraint("user.inst.type", "/decisions/components/0/type", "balcony")],
    )
    gap = next(
        gap for gap in instance_gaps(doc) if gap.constraint_id == "user.inst.type"
    )
    assert gap.status == "satisfied"
    assert gap.actual == "balcony"


def test_instance_type_requirement_is_open_when_the_type_is_different():
    doc = instance_document(
        [{"type": "balcony", "host": "wall_front_2_1", "size": {"width": 3.6, "depth": 1.4}}],
        [constraint("user.inst.type", "/decisions/components/0/type", "light")],
    )
    gap = next(
        gap for gap in instance_gaps(doc) if gap.constraint_id == "user.inst.type"
    )
    assert gap.status == "open"
    assert gap.actual == "balcony"


def test_resolved_host_is_satisfied_with_the_real_host_field_as_evidence():
    """宿主按原意解析到时，证据必须指出**实体上那个字段**，不是复述图纸写法。"""

    doc = instance_document(
        [{"type": "door", "host": "wall_front_1_1"}],
        [constraint("user.inst.host", "/decisions/components/0/host", "wall_front_1_1")],
    )
    gap = next(
        gap for gap in instance_gaps(doc) if gap.constraint_id == "user.inst.host"
    )
    assert gap.status == "satisfied"
    assert gap.actual == "wall_front_1_1"
    assert "parentWall" in gap.evidence


def test_dropped_instance_is_open_and_points_at_the_compile_report():
    """宿主解析不到、整条被丢弃的实例必须 open，而不是 needs_review 装看不见。"""

    doc = instance_document(
        [
            {"type": "door", "host": "wall_front_1_1"},
            {"type": "door", "host": "wall_nowhere_9"},
        ],
        [constraint("user.inst.host", "/decisions/components/1/host", "wall_nowhere_9")],
    )
    gap = next(
        gap for gap in instance_gaps(doc) if gap.constraint_id == "user.inst.host"
    )
    assert gap.status == "open"
    assert "instance_dropped" in gap.evidence


def test_instance_size_requirement_is_checked_against_the_entity_field():
    doc = instance_document(
        [{"type": "door", "host": "wall_front_1_1"}],
        [constraint("user.inst.width", "/decisions/components/0/size/width", 9.9)],
    )
    gap = next(
        gap for gap in instance_gaps(doc) if gap.constraint_id == "user.inst.width"
    )
    # 尺寸通道当前**没有**实例级落地（compiler.instance_size 只记不改），所以判 open 而不是
    # 假满足 —— 这条断言就是钉住"没落实就不能说满足"。
    assert gap.status == "open"
    assert gap.actual != 9.9


def test_mapping_index_is_the_design_order_not_the_compile_order():
    """🔴 编译循环按**类型分组**跑，映射若不按下标排序，履约就会把第 3 条当第 1 条。"""

    doc = instance_document(
        [
            {"type": "window", "host": "wall_right_1_1"},
            {"type": "balcony", "host": "wall_front_2_1"},
            {"type": "door", "host": "wall_front_1_1"},
        ]
    )
    entities = compile_document(doc).stats["instance_overrides"]["instance_entities"]
    assert [item["index"] for item in entities] == [0, 1, 2]
    assert [item["declared_type"] for item in entities] == ["window", "balcony", "door"]


def test_mapping_is_projected_into_the_compile_report():
    """映射投影不出来 = 履约层永远判不了，守卫挂在 summary() 上。"""

    doc = instance_document([{"type": "door", "host": "wall_front_1_1"}])
    report = compile_document(doc).summary()
    assert len(report["instance_entities"]) == 1
    assert report["instance_entities"][0]["entity_id"]


def test_instance_check_without_the_mapping_is_never_satisfied():
    """映射缺席时退 needs_review（旧行为），不得凭类型级证据判过。"""

    doc = instance_document(
        [{"type": "balcony", "host": "wall_front_2_1"}],
        [constraint("user.inst.type", "/decisions/components/0/type", "balcony")],
    )
    gap = next(
        gap
        for gap in evaluate_fulfillment(doc, blueprint_of(doc), _stable_hash(doc))
        if gap.constraint_id == "user.inst.type"
    )
    assert gap.status == "needs_review"
    assert "instance_entities" in gap.evidence


def test_instance_index_beyond_the_mapping_is_not_satisfied():
    doc = instance_document(
        [{"type": "door", "host": "wall_front_1_1"}],
        [constraint("user.inst.type", "/decisions/components/7/type", "door")],
    )
    gap = next(
        gap for gap in instance_gaps(doc) if gap.constraint_id == "user.inst.type"
    )
    assert gap.status == "needs_review"


# ── 逐体量屋顶（P5-A）：屋面逐块核对 ────────────────────────────────


def roof_plan(roof, volumes=None):
    plan = json.loads(json.dumps(_FIXTURE))
    plan["massing"] = {**plan["massing"], "width": 20, "depth": 15}
    plan["volumes"] = volumes or [
        {"id": "main", "role": "primary", "x": 0, "z": 0,
         "width": 12, "depth": 10, "start_floor": 1, "end_floor": 2},
        {"id": "wing", "role": "secondary", "x": 12, "z": 0,
         "width": 6, "depth": 6, "start_floor": 1, "end_floor": 2},
    ]
    plan["roof"] = roof
    return plan


def roof_gaps(doc, compiled):
    slots = list((compiled.design_brief or {}).get("roof_slots") or [])
    return evaluate_fulfillment(doc, compiled.blueprint, _stable_hash(doc), None, slots)


def roof_document(roof, constraints=()):
    plan = roof_plan(roof)
    plan["design_constraints"] = list(constraints)
    quotes = "、".join(str(item.get("source_quote") or "") for item in constraints)
    request = f"生成一个 L 形别墅（{quotes}）" if quotes else "生成一个 L 形别墅"
    return build_design_document(plan, session_id="intent", source_request=request)


def test_per_volume_roof_type_is_checked_against_its_own_roof_element():
    doc = roof_document(
        {"type": "gable", "overhang": 0.6, "volumes": [{"volume": "wing", "type": "flat"}]},
        [constraint("user.wing", "/decisions/roof/volumes/0/type", "flat")],
    )
    gap = next(gap for gap in roof_gaps(doc, compile_document(doc)) if gap.constraint_id == "user.wing")
    assert gap.status == "satisfied"
    assert gap.actual == "flat"
    assert "wing" in gap.evidence


def test_per_volume_roof_type_is_open_when_the_element_disagrees():
    """设计层说侧翼 flat，实体却是 gable ⇒ 必须 open（这正是本层存在的理由）。"""

    doc = roof_document(
        {"type": "gable", "overhang": 0.6, "volumes": [{"volume": "wing", "type": "flat"}]},
        [constraint("user.wing", "/decisions/roof/volumes/0/type", "hip")],
    )
    compiled = compile_document(doc)
    gap = next(gap for gap in roof_gaps(doc, compiled) if gap.constraint_id == "user.wing")
    assert gap.status == "open"
    assert gap.actual == "flat"


def test_per_volume_roof_without_slot_evidence_stays_needs_review():
    doc = roof_document(
        {"type": "gable", "overhang": 0.6, "volumes": [{"volume": "wing", "type": "flat"}]},
        [constraint("user.wing", "/decisions/roof/volumes/0/type", "flat")],
    )
    compiled = compile_document(doc)
    gap = next(
        gap
        for gap in evaluate_fulfillment(doc, compiled.blueprint, _stable_hash(doc))
        if gap.constraint_id == "user.wing"
    )
    assert gap.status == "needs_review"
    assert "roof_slots" in gap.evidence


def test_template_roof_type_is_satisfied_even_when_a_volume_is_overridden():
    """🔴 有逐体量覆盖时 ``roof.type`` 是**模板**，不是"整栋唯一形态"——
    被覆盖的体量已经兑现了另一条要求，不该在这里再报一次缺失。"""

    doc = roof_document(
        {"type": "gable", "overhang": 0.6, "volumes": [{"volume": "wing", "type": "flat"}]},
        [constraint("user.roof", "/decisions/roof/type", "gable")],
    )
    compiled = compile_document(doc)
    assert len([item for item in compiled.blueprint["geometry"]["elements"] if item.get("type") == "roof"]) == 2
    gap = next(gap for gap in roof_gaps(doc, compiled) if gap.constraint_id == "user.roof")
    assert gap.status == "satisfied"
    assert sorted(gap.actual) == ["flat", "gable"]


def test_template_roof_type_is_open_when_an_unexplained_type_appears():
    """对照上一条：覆盖声明了 flat，实体却冒出第三种 hip ⇒ **解释不了**，必须 open。

    （"覆盖条数 < 屋面条数"不是判据 —— 数数会把"每条覆盖都兑现了"误判成缺口。）
    """

    doc = roof_document(
        {"type": "gable", "overhang": 0.6, "volumes": [{"volume": "wing", "type": "flat"}]},
        [constraint("user.roof", "/decisions/roof/type", "gable")],
    )
    compiled = compile_document(doc)
    for roof in compiled.blueprint["geometry"]["elements"]:
        if roof.get("type") == "roof" and roof.get("roofType") == "flat":
            roof["roofType"] = "hip"  # 覆盖声明的是 flat，hip 没有任何设计依据
            break
    gap = next(gap for gap in roof_gaps(doc, compiled) if gap.constraint_id == "user.roof")
    assert gap.status == "open"
    assert sorted(gap.actual) == ["gable", "hip"]


def test_roof_overhang_is_verified_against_final_outline():
    """出檐参数有槽位证据，并逐项核对最终屋面位置、跨度和进深。"""

    doc = roof_document(
        {"type": "gable", "overhang": 0.6, "volumes": [{"volume": "wing", "overhang": 0.3}]},
        [constraint("user.wing.out", "/decisions/roof/volumes/0/overhang", 0.3)],
    )
    gap = next(
        gap for gap in roof_gaps(doc, compile_document(doc)) if gap.constraint_id == "user.wing.out"
    )
    assert gap.status == "satisfied"
    assert "最终屋面核对" in gap.evidence


# ── 核心：设计层通过 ≠ 实体层通过 ────────────────────────────────


def test_design_layer_satisfied_but_entity_layer_open_is_reported():
    """🔴 本阶段存在的唯一理由：设计层 satisfied 不能复制成最终通过。

    设计写的是 gable（设计层满足），但末端修复把成品屋顶改成了 flat ——
    履约必须发现，且 ``actual`` 指到实体里的真实取值。
    """

    doc = document([constraint("user.roof", "/decisions/roof/type", "gable")])
    blueprint = blueprint_of(doc)
    for roof in blueprint["geometry"]["elements"]:
        if roof.get("type") == "roof":
            roof["roofType"] = "flat"

    gaps = evaluate_fulfillment(doc, blueprint, _stable_hash(doc))
    gap = next(gap for gap in gaps if gap.constraint_id == "user.roof")
    assert gap.status == "open"
    assert gap.actual == ["flat"]
    assert gap.layer == "implementation"
    assert "roof" in gap.evidence


def test_matching_requirement_is_satisfied_with_entity_evidence():
    doc = document([constraint("user.roof", "/decisions/roof/type", "gable")])
    summary = summary_of(doc)
    assert summary["satisfied"] == 1
    assert summary["open"] == 0
    assert summary["satisfied_ratio"] == 1.0
    assert summary["version"] == FULFILLMENT_VERSION


def test_wrong_requirement_on_valid_geometry_is_open_not_an_error():
    """几何完全合法，只是屋型与用户要求不符 ⇒ 履约 open，但**不是**几何错误。"""

    doc = document([constraint("user.roof", "/decisions/roof/type", "flat")])
    result = compile_document(doc)
    assert result.ok, "蓝图本身必须仍然合法"
    summary = summary_of(doc, result.blueprint)
    assert summary["open"] == 1
    assert summary["geometry_blocking"] is False


def test_shrunk_building_is_detected_even_though_design_layer_passes():
    """修复环把整体改小（宽度腰斩）时，尺寸要求必须失败。"""

    doc = document([constraint("user.width", "/decisions/massing/width", 18.0)])
    blueprint = blueprint_of(doc)
    for entity in blueprint["geometry"]["elements"]:
        for key in ("from", "to"):
            vector = entity.get(key)
            if isinstance(vector, list) and len(vector) == 3:
                vector[0] = round(vector[0] * 0.5, 3)

    gaps = evaluate_fulfillment(doc, blueprint, _stable_hash(doc))
    gap = next(gap for gap in gaps if gap.constraint_id == "user.width")
    assert gap.status == "open"
    assert gap.actual == 9.0


def test_roof_overhang_does_not_break_the_width_requirement():
    """出檐让屋顶比墙体外扩 —— 轮廓尺寸必须只按墙量，否则永远判不满足。"""

    doc = document([constraint("user.width", "/decisions/massing/width", 18.0)])
    assert status_of(evaluate_fulfillment(doc, blueprint_of(doc), _stable_hash(doc)), "user.width") == "satisfied"


def test_facade_bays_are_compared_per_floor():
    """``bays`` 是每层槽位数；两层住宅每层 3 个，不该因为总数 6 而误判。"""

    doc = document([constraint("user.bays", "/decisions/facades/front/bays", 3)])
    blueprint = blueprint_of(doc)
    gap = next(
        gap for gap in evaluate_fulfillment(doc, blueprint, _stable_hash(doc))
        if gap.constraint_id == "user.bays"
    )
    assert gap.status == "satisfied"
    assert sorted(gap.actual.values()) == [3, 3]

    # 拆掉一层的某个开口 ⇒ 该层变成 2 ⇒ 履约必须失败
    walls = {
        item["id"]: item for item in blueprint["geometry"]["elements"] if item.get("type") == "wall"
    }
    victim = next(
        opening for opening in blueprint["geometry"]["components"]
        if opening.get("type") == "window"
        and abs(float(walls[opening["parentWall"]]["from"][1]) - 0.0) < 0.01
    )
    blueprint["geometry"]["components"].remove(victim)
    gap = next(
        gap for gap in evaluate_fulfillment(doc, blueprint, _stable_hash(doc))
        if gap.constraint_id == "user.bays"
    )
    assert gap.status == "open"


# ── 不冒充：判不了的必须留痕 ───────────────────────────────────────


def test_instance_level_requirement_is_not_satisfied_without_entity_mapping():
    """实例的宿主/位置没有实体 ID 映射时必须 needs_review，不能只凭"有该类型"判过。"""

    doc = document([constraint("user.inst", "/decisions/components/0/type", "canopy")])
    gap = next(
        gap for gap in evaluate_fulfillment(doc, blueprint_of(doc), _stable_hash(doc))
        if gap.constraint_id == "user.inst"
    )
    assert gap.status == "needs_review"
    assert "instance_entities" in gap.evidence


def test_manual_check_is_never_satisfied():
    doc = document([constraint("user.look", "/decisions/massing/shape", "l_shape", check="manual")])
    assert status_of(evaluate_fulfillment(doc, blueprint_of(doc), _stable_hash(doc)), "user.look") == "needs_review"


def test_unknown_design_field_is_unsupported_not_open():
    doc = document([constraint("user.x", "/decisions/roof/per_volume", "gable")])
    assert status_of(evaluate_fulfillment(doc, blueprint_of(doc), _stable_hash(doc)), "user.x") == "unsupported"


def test_undeterminable_items_stay_out_of_the_ratio():
    doc = document([
        constraint("user.roof", "/decisions/roof/type", "gable"),
        constraint("user.inst", "/decisions/components/0/type", "canopy"),
    ])
    summary = summary_of(doc)
    assert (summary["satisfied"], summary["needs_review"]) == (1, 1)
    # 分母只算"能判定"的条目：needs_review 不被算成失败，也不被算成满足。
    assert summary["satisfied_ratio"] == 1.0


# ── 报告与交付语义 ────────────────────────────────────────────────


def test_no_requirement_means_no_claim():
    doc = document()
    summary = summary_of(doc)
    assert summary["total"] == 0
    assert fulfillment_line(summary) == ""


def test_summary_reports_design_hash_so_a_changed_design_invalidates_it():
    first = summary_of(document([constraint("user.roof", "/decisions/roof/type", "gable")]))
    second = summary_of(document([constraint("user.roof", "/decisions/roof/type", "flat")]))
    assert first["design_hash"] != second["design_hash"]


def test_superseded_decision_is_counted_instead_of_silently_dropped():
    payload = constraint("user.roof", "/decisions/roof/type", "gable")
    doc = document([payload])
    superseded = DesignConstraint.model_validate(
        {**payload, "id": "user.roof.v2", "adoption": "superseded"}
    )
    doc = doc.model_copy(update={"constraints": [*doc.constraints, superseded]})
    summary = fulfillment_summary(
        evaluate_fulfillment(doc, blueprint_of(doc), _stable_hash(doc)),
        design_hash=_stable_hash(doc),
        superseded=sum(1 for c in doc.constraints if c.adoption == "superseded"),
    )
    assert summary["superseded"] == 1
    assert all(gap["id"] != "gap.impl.user.roof.v2" for gap in summary["gaps"])


def test_delivery_reply_states_the_gap_without_changing_the_gate():
    """履约缺口必须出现在交付文案里，且**不进**几何门禁的错误计数。"""

    from app.services.agent_delivery import BlueprintDelivery, ValidationSummary

    delivery = BlueprintDelivery(
        filename="a.wild", file_url="/api/scenes/a.wild", name="别墅",
        elements_count=10, components_count=12,
        validation=ValidationSummary(total=5, passed=5, warnings=0, errors=0),
        fulfillment={
            "total": 2, "satisfied": 1, "open": 1, "needs_review": 0,
            "unsupported": 0, "superseded": 0, "satisfied_ratio": 0.5,
            "geometry_blocking": False,
            "gaps": [{
                "id": "gap.impl.user.roof", "target": "/decisions/roof/type",
                "status": "open", "expected": "flat", "actual": ["gable"],
                "evidence": "屋顶实体 roof_01 的 roofType",
            }],
        },
    )
    assert "设计履约 1/2 已兑现" in delivery.reply
    assert "/decisions/roof/type" in delivery.reply
    assert delivery.validation.errors == 0
