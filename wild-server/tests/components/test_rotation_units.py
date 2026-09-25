"""`rotation` 单位迁移的回归（2026-09-25 用户报"家具还是生成失败"）。

实测缺陷：模型把家具朝向写成**度数标量**（`"rotation": 180` / `90`），
`validate_element_required_fields` 如实报"rotation 必须是弧度制三维数组"，
于是**整批** 8 个片段被判死 → 条目重试 → 最终 0 件家具落地，表面像"模型不会做家具"。

修法：在**校验之前**做"同一语义、不同单位"的迁移
（`app/utils/rotation.py`，唯一规则函数），生成批次 / 交付归一 / 物件零件三处共用。
校验器保持原样做最后一道网：真正认不出的形态（如 `[0, 7.0, 0]`）仍如实报错。
"""

from __future__ import annotations

import math

import pytest

from app.agent.generation.component_workflow import _coerce_fragment_rotations
from app.agent.generation.objects.planning import normalize_primitive_part
from app.tools.component_tools import validate_component
from app.utils.blueprint_normalizer import normalize_blueprint_for_delivery
from app.utils.rotation import coerce_element_rotation, coerce_rotation

HALF_PI = math.pi / 2
PI = math.pi


def _rotation_errors(blueprint: dict) -> str:
    """走真实消费入口 `validate_component`。

    ⚠️ 不能直接调 `validate_element_required_fields`：它是 `@tool` 装饰过的
    `StructuredTool`（`COMPONENT_TOOLS` 里要 `getattr(..., "func", ...)` 取底层函数），
    直接调用会抛 `'StructuredTool' object is not callable`。
    """

    return validate_component("furniture", blueprint)


def _blueprint(elements: list[dict]) -> dict:
    return {
        "meta": {"version": "1.1", "type": "building"},
        "geometry": {"elements": elements, "components": []},
        "materials": {},
    }


def _furniture(rotation=None) -> dict:
    element = {
        "type": "furniture", "id": "furniture_01", "subtype": "bed",
        "position": [1.0, 0.0, 1.0],
        "dimensions": {"width": 1.6, "depth": 2.0, "height": 0.55},
    }
    if rotation is not None:
        element["rotation"] = rotation
    return element


# ── ① 纯函数：认得出的迁移，认不出的不猜 ─────────────────────────────

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (180, [0.0, PI, 0.0]),
        (90, [0.0, HALF_PI, 0.0]),
        (0, [0.0, 0.0, 0.0]),
        (-90, [0.0, -HALF_PI, 0.0]),
        (270, [0.0, 3 * HALF_PI, 0.0]),
        ("90", [0.0, HALF_PI, 0.0]),
        ("90deg", [0.0, HALF_PI, 0.0]),
        ("90°", [0.0, HALF_PI, 0.0]),
        ("90度", [0.0, HALF_PI, 0.0]),
        ([0, 90, 0], [0.0, HALF_PI, 0.0]),
        ([0, 180, 0], [0.0, PI, 0.0]),
        ([90, 0, 0], [HALF_PI, 0.0, 0.0]),
    ],
)
def test_degree_forms_are_migrated(raw, expected) -> None:
    assert coerce_rotation(raw) == pytest.approx(expected)


@pytest.mark.parametrize(
    "raw",
    [
        [0.0, 1.5708, 0.0],       # 合法弧度数组
        [0, 0, 0],
        [PI, PI, PI],             # 边界内仍按弧度读
        [0.0, 1.0472, 0.0],       # 60°
    ],
)
def test_radian_arrays_are_untouched(raw) -> None:
    assert coerce_rotation(raw) == pytest.approx([float(value) for value in raw])


@pytest.mark.parametrize(
    "raw",
    [
        [0, 7.0, 0],              # 超出 2π 又不是 15 的倍数 → 认不出，不猜
        [0, 1],                   # 长度不是 3
        [0, 1, 2, 3],
        "朝向",                    # 非数字字符串
        True,                     # bool 不是角度
        {"y": 90},
        None,
        [0, None, 0],
        float("nan"),
        float("inf"),
    ],
)
def test_unrecognizable_forms_return_none(raw) -> None:
    assert coerce_rotation(raw) is None


# ── ② 元素级迁移：不改合法值、不凭空补字段 ───────────────────────────

def test_element_rotation_migrated_in_place() -> None:
    element = _furniture(rotation=180)
    assert coerce_element_rotation(element) == pytest.approx([0.0, PI, 0.0])
    assert element["rotation"] == pytest.approx([0.0, PI, 0.0])


def test_element_rotation_valid_value_reports_no_change() -> None:
    element = _furniture(rotation=[0.0, 1.5708, 0.0])
    assert coerce_element_rotation(element) is None
    assert element["rotation"] == [0.0, 1.5708, 0.0]


def test_element_without_rotation_is_not_touched() -> None:
    element = _furniture()
    assert coerce_element_rotation(element) is None
    assert "rotation" not in element


# ── ③ 生成批次入口：8 个片段里混着度数写法，全部迁移后才过校验 ──────────

def test_generation_batch_migrates_degrees_before_validation() -> None:
    fragments = [
        _furniture(rotation=180),
        _furniture(rotation=90),
        _furniture(rotation=[0, 90, 0]),
        _furniture(rotation=[0.0, HALF_PI, 0.0]),
        _furniture(),
    ]
    for index, fragment in enumerate(fragments):
        fragment["id"] = f"furniture_{index:02d}"

    assert "❌" in _rotation_errors(_blueprint(fragments)), (
        "迁移之前校验器确实应当报错（它是对的最后一道网）"
    )

    repaired = _coerce_fragment_rotations(fragments)
    assert repaired == 3, "只有三条是度数写法（180 / 90 / [0,90,0]）"

    result = _rotation_errors(_blueprint(fragments))
    assert "❌" not in result, result
    assert fragments[0]["rotation"] == pytest.approx([0.0, PI, 0.0])
    assert fragments[2]["rotation"] == pytest.approx([0.0, HALF_PI, 0.0])


def test_ambiguous_array_is_left_alone() -> None:
    """形态像 vec3、值又超出 2π：不猜单位，原样交给校验器。

    校验器**只查形态不查量纲**，所以 `[0, 7.0, 0]` 会被当成合法弧度进去。
    这是契约本身的口径（rotation 就是弧度），迁移不替模型改语义。
    """

    fragment = _furniture(rotation=[0, 7.0, 0])
    assert _coerce_fragment_rotations([fragment]) == 0
    assert fragment["rotation"] == [0, 7.0, 0]
    assert "rotation" not in _rotation_errors(_blueprint([fragment]))


@pytest.mark.parametrize("raw", [[0, 1], "朝向", True, {"y": 90}, [0, None, 0], [0, 1, 2, 3]])
def test_unmigratable_shapes_are_still_rejected(raw) -> None:
    """连形态都不对、又认不出是度数写法的，仍要被拦下 —— 迁移不是"把什么都放过"。"""

    fragment = _furniture(rotation=raw)
    assert _coerce_fragment_rotations([fragment]) == 0
    assert "rotation" in _rotation_errors(_blueprint([fragment]))


# ── ④ 交付归一也走同一条规则 ─────────────────────────────────────

def test_delivery_normalization_migrates_rotation() -> None:
    blueprint, report = normalize_blueprint_for_delivery(
        _blueprint([_furniture(rotation=180)]),
    )
    element = blueprint["geometry"]["elements"][0]
    assert element["rotation"] == pytest.approx([0.0, PI, 0.0])
    assert any("rotation" in item for item in report.repaired_fields)


# ── ⑤ 物件链的通用几何零件同样不再静默丢朝向 ─────────────────────────

def test_object_primitive_part_keeps_degree_rotation() -> None:
    part = normalize_primitive_part({
        "shape": "box", "position": [0, 0, 0],
        "dimensions": [1, 1, 1], "rotation": 90,
    })
    assert part is not None
    assert part["rotation"] == pytest.approx([0.0, HALF_PI, 0.0])


def test_object_primitive_part_keeps_radian_rotation() -> None:
    part = normalize_primitive_part({
        "shape": "box", "position": [0, 0, 0],
        "dimensions": [1, 1, 1], "rotation": [0, 1.5708, 0],
    })
    assert part is not None
    assert part["rotation"] == pytest.approx([0.0, 1.5708, 0.0], abs=1e-3)
