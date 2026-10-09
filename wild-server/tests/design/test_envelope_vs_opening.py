"""P5-B：围护与开口分离 —— ``empty``（有墙无洞）与 ``open``（开敞无墙）。

P5-B 的验收口径：两个只在一个设计变量上不同的方案 ⇒ 实体上出现对应差异。
这里的判据是**墙的条数**：开敞与有墙在实体上唯一能测出来的差别就是墙在不在。
"""
import pytest

from app.agent.compiler import compile_design
from app.agent.generation.architecture import normalize_architecture_plan
from app.design.openings import is_open_side, opening_kind, opening_token, split_opening

_FACES = ("front", "back", "left", "right")
_SOLID_UPPER = ("window", "window", "window")


def _face(ground, upper=_SOLID_UPPER):
    return {"bays": 3, "entrance_bay": None,
            "ground_pattern": list(ground), "upper_pattern": list(upper)}


def _all_faces(ground, upper=_SOLID_UPPER):
    return {face: _face(ground, upper) for face in _FACES}


def compile_facades(facades, message="小建筑"):
    plan = {"massing": {"shape": "rectangular", "width": 12, "depth": 9, "floors": 2,
                     "modeled_floors": 2, "floor_height": 3.2},
            "facades": facades}
    notes: list[str] = []
    normalized = normalize_architecture_plan(plan, message, normalize_notes=notes)
    return compile_design(normalized, user_message=message), notes


def walls_of(facades):
    result, _ = compile_facades(facades)
    return sorted(
        item["id"] for item in result.blueprint["geometry"]["elements"]
        if item.get("type") == "wall"
    )


# ── 词法：两个语义各有名字 ────────────────────────────────────────


def test_open_and_empty_are_distinct_kinds():
    assert opening_kind("empty") == "empty"
    assert opening_kind("open") == "open"
    assert split_opening("open") == ("open", None)
    assert opening_token("open", None) == "open"
    # 形态名对这两类都不适用，必须被丢掉而不是被当成类型。
    assert split_opening("open:swing") == ("open", None)
    assert split_opening("empty:swing") == ("empty", None)


def test_is_open_side_distinguishes_whole_face_from_partial():
    assert is_open_side(["open", "open", "open"]) is True
    assert is_open_side(["empty", "empty", "empty"]) is False, "旧文档迁移口径"
    assert is_open_side(["empty", "door", "empty"]) is False, "半面 empty 是有墙无洞"
    assert is_open_side(["window", "window", "window"]) is False
    assert is_open_side([]) is False


# ── 实体：墙在不在 ────────────────────────────────────────────────


def test_explicit_open_removes_the_wall():
    solid = walls_of(_all_faces(("window", "door", "window")))
    opened = walls_of(_all_faces(("open", "open", "open")))
    assert len(solid) == 8, "两层四面实墙"
    assert len(opened) == 4, "只有上层两面（首层四面开敞）"
    assert set(opened).issubset(set(solid))


def test_partial_empty_keeps_the_wall():
    """🔴 这条是本次改动的核心断言：`empty` 曾经**兼职**开敞，
    拆分后"半面 empty"必须重新变回"有墙无洞"。"""

    assert len(walls_of(_all_faces(("empty", "door", "empty")))) == 8


def test_new_all_empty_keeps_a_solid_wall():
    walls = walls_of(_all_faces(("empty", "empty", "empty")))
    assert len(walls) == 8
    _, notes = compile_facades(_all_faces(("empty", "empty", "empty")))
    assert not any("整面为 empty" in note for note in notes)


def test_open_ground_floor_is_reported_as_a_missing_wall_level_not_a_silent_pass():
    """四面开敞 ⇒ 首层无墙 ⇒ 标高缺失。这条缺陷必须**报出来**（error），
    不许因为"开敞是合法表态"就把它吞掉。"""

    result, _ = compile_facades(_all_faces(("open", "open", "open")))
    assert any(
        item.severity == "error" and "墙体标高" in item.evidence
        for item in result.defects
    )


def test_half_empty_is_not_recorded_as_a_migration():
    """半面 empty 本来就是它自己的意思，不需要迁移说明。"""

    _, notes = compile_facades(_all_faces(("empty", "door", "empty")))
    assert not [note for note in notes if "整面为 empty" in note]


def test_open_in_one_face_only_opens_that_face():
    facade = _all_faces(("window", "door", "window"))
    facade["front"] = _face(("open", "open", "open"))
    walls = walls_of(facade)
    assert len(walls) == 7, "只去掉首层正面一堵墙"
    assert not [name for name in walls if name == "wall_front_1"]


# ── 契约与提示词 ──────────────────────────────────────────────────


def test_contract_rejects_open_with_a_form():
    """`open:xxx` 不是合法 token（和 `empty:xxx` 一样）。"""

    from app.design.contracts import FacadeDecision

    with pytest.raises(ValueError):
        FacadeDecision(
            bays=3, ground_pattern=["open:swing", "open", "open"],
            upper_pattern=list(_SOLID_UPPER),
        )
    with pytest.raises(ValueError):
        FacadeDecision(
            bays=3, ground_pattern=["empty:swing", "open", "open"],
            upper_pattern=list(_SOLID_UPPER),
        )


def test_contract_accepts_both_empty_and_open():
    from app.design.contracts import FacadeDecision

    facade = FacadeDecision(
        bays=3, ground_pattern=["open", "open", "open"],
        upper_pattern=list(_SOLID_UPPER),
    )
    assert facade.ground_pattern == ["open", "open", "open"]


def test_block_contract_evidence_names_both_kinds():
    from app.agent.generation.architecture.design_blocks import BLOCK_BY_NAME
    from app.agent.generation.architecture.design_workflow import check_block_contract

    block = BLOCK_BY_NAME["facade"]
    issue = check_block_contract(
        block, {"facades": {"front": {"bays": 1, "ground_pattern": ["garage"],
                                      "upper_pattern": ["window"]}}}, {},
    )
    assert "open" in issue and "empty" in issue


# ── 稳定性 ────────────────────────────────────────────────────────


def test_repeated_compile_is_stable():
    facades = _all_faces(("open", "empty", "window"))
    assert walls_of(facades) == walls_of(facades)


# ── 履约：开敞表态在实体侧可核（P4 层）───────────────────────────




def _open_document():
    """一份"四面首层开敞"的设计文档（履约判据的输入）。"""

    from app.design.resolver import build_design_document

    plan = {
        "massing": {"shape": "rectangular", "width": 12, "depth": 9, "floors": 2,
                    "modeled_floors": 2, "floor_height": 3.2},
        "volumes": [{"id": "main", "role": "primary", "x": 0, "z": 0,
                     "width": 12, "depth": 9, "start_floor": 1, "end_floor": 2}],
        "structural_grid": {"system": "wall_bearing", "x_bays": 3, "z_bays": 2},
        "facades": _all_faces(("open", "open", "open")),
        "roof": {"type": "gable"},
    }
    return build_design_document(
        plan, session_id="intent", source_request="小建筑，四面首层开敞（四面首层开敞）",
    )


def _gap(doc, blueprint, target, expected, quote):
    from app.design.compilation import compile_document
    from app.design.completeness import merge_design_constraints
    from app.design.contracts import DesignConstraint, DesignDocument
    from app.design.fulfillment import evaluate_fulfillment
    from app.design.resolver import _stable_hash

    payload = doc.model_dump(mode="json")
    request = payload["requirements"]["source_request"]
    document = DesignDocument.model_validate(payload)
    document = document.model_copy(update={"constraints": merge_design_constraints(
        document.constraints,
        [DesignConstraint(
            id="user.env", kind="user_hard", target=target,
            expression="这一面开敞", source="user_request",
            source_quote=quote, check="equals", expected=expected,
        )],
        request,
    )})
    final = blueprint if blueprint is not None else compile_document(document).blueprint
    return next(
        item for item in evaluate_fulfillment(document, final, _stable_hash(document))
        if item.constraint_id == "user.env"
    )


def test_open_facade_requirement_is_satisfied_when_that_level_has_no_wall():
    doc = _open_document()
    gap = _gap(doc, None, "/decisions/facades/front/ground_pattern",
               ["open", "open", "open"], "四面首层开敞")
    assert gap.status == "satisfied", gap.evidence


def test_open_facade_requirement_is_open_when_a_wall_is_put_back():
    """🔴 把墙塞回一个声明开敞的面 ⇒ 必须 open。这正是 P4 存在的理由。"""

    from app.design.compilation import compile_document

    doc = _open_document()
    blueprint = compile_document(doc).blueprint
    walls = [item for item in blueprint["geometry"]["elements"] if item.get("type") == "wall"]
    donor = next(item for item in walls if item["id"] == "wall_back_2")
    blueprint["geometry"]["elements"].append({
        **donor, "id": "wall_front_1",
        "from": [0.0, 0.0, 0.0], "to": [12.0, 3.2, 0.0],
    })
    gap = _gap(doc, blueprint, "/decisions/facades/front/ground_pattern",
               ["open", "open", "open"], "四面首层开敞")
    assert gap.status == "open"
    assert "wall_front_1" in gap.evidence


def test_solid_facade_requirement_is_never_claimed_as_satisfied():
    """声明有墙时判 needs_review ——「哪一格无洞」实体侧无字段，不冒充满足。"""

    doc = _open_document()
    gap = _gap(doc, None, "/decisions/facades/front/upper_pattern",
               ["window", "window", "window"], "四面首层开敞")
    assert gap.status == "needs_review"
