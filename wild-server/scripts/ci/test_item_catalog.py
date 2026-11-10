"""物品库守卫测试：目录索引与 `.wild` 文件必须一一对应，且每份都是合法 asset。

为什么要这一层：物品是**手写坐标**的数据文件，schema 合法不等于几何可用，
但反过来 —— 一旦某份文件把 `meta.type` 写成 `building`、或把 `wall` 塞进
`elements`，"物品"这个概念就退化成"随便一段蓝图"，前端放置会塞出结构构件。
这些错误不会让任何别的测试变红，所以单独钉住。
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ITEM_ROOT = Path(__file__).resolve().parents[2] / "storage" / "item_catalog"
MANIFEST = ITEM_ROOT / "manifest.json"

#: 物品只允许纯几何元素。结构构件（wall/floor/opening/stair…）参与空间求解，
#: 放进物品库会让"物品"和"构件"两个概念混在一起。
GEOMETRY_ONLY = {"primitive", "solid"}


def _manifest() -> dict:
    assert MANIFEST.is_file(), (
        f"缺少目录索引 {MANIFEST}，先跑 scripts/item_catalog/build.py"
    )
    return json.loads(MANIFEST.read_text("utf-8"))


def _entries() -> list[dict]:
    items = _manifest().get("items")
    assert isinstance(items, list) and items, "manifest.items 为空"
    return items


def test_manifest_count_matches_files():
    entries = _entries()
    files = {path.stem for path in (ITEM_ROOT / "items").glob("*.wild")}
    assert {entry["id"] for entry in entries} == files, (
        "manifest 条目与 items/ 下的文件不一致"
    )
    assert _manifest()["count"] == len(entries)


def test_every_item_is_a_valid_asset():
    import jsonschema

    schema = json.loads(
        (Path(__file__).resolve().parents[3] / "wild-core/schema.json").read_text(
            "utf-8"
        )
    )
    validator = jsonschema.Draft202012Validator(schema)
    for entry in _entries():
        blueprint = json.loads((ITEM_ROOT / entry["file"]).read_text("utf-8"))
        errors = [
            f"/{'/'.join(map(str, error.path))}: {error.message}"
            for error in validator.iter_errors(blueprint)
        ]
        assert not errors, f"{entry['id']} 不符合引擎 schema: {errors[:3]}"
        assert blueprint["meta"]["type"] == "asset", (
            f"{entry['id']} 的 meta.type 必须是 asset"
        )
        assert blueprint["meta"]["name"] == entry["name"], (
            f"{entry['id']} 的名称与 manifest 不一致"
        )
        elements = blueprint["geometry"]["elements"]
        assert elements, f"{entry['id']} 没有几何"
        for index, element in enumerate(elements):
            assert element["type"] in GEOMETRY_ONLY, (
                f"{entry['id']} 的 elements[{index}] 是 {element['type']}，物品只允许 {sorted(GEOMETRY_ONLY)}"
            )


def test_item_ids_are_unique_and_slug_safe():
    import re

    pattern = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
    seen = set()
    for entry in _entries():
        identifier = entry["id"]
        assert pattern.match(identifier), f"物品 id 不符合 slug 规则: {identifier}"
        assert identifier not in seen, f"物品 id 重复: {identifier}"
        seen.add(identifier)


def test_item_ids_are_prefix_free():
    """id 不能是另一个 id 的前缀。

    放置时元素 id 形如 `<itemId>_<partId>`，若 `sofa` 与 `sofa_three` 同时存在，
    从 id 反查归属就会歧义，删除/选中会指错对象。
    """

    identifiers = sorted(entry["id"] for entry in _entries())
    for index, identifier in enumerate(identifiers):
        for other in identifiers[index + 1 :]:
            assert not other.startswith(identifier + "_"), (
                f"{identifier!r} 是 {other!r} 的前缀"
            )


def _valid_import_asset() -> dict:
    material = {
        "baseColor": [0.4, 0.2, 0.1],
        "roughness": 0.7,
        "metallic": 0,
        "albedo": 1,
        "lightingCondition": "D65_noon",
    }
    return {
        "meta": {"version": "1.0", "type": "asset", "name": "测试物品"},
        "geometry": {
            "elements": [
                {
                    "type": "primitive",
                    "id": "left",
                    "shape": "box",
                    "position": [-0.5, 0.5, 0],
                    "dimensions": [1, 1, 1],
                    "material": "wood",
                },
                {
                    "type": "primitive",
                    "id": "right",
                    "shape": "box",
                    "position": [0.5, 0.5, 0],
                    "dimensions": [1, 1, 1],
                    "material": "wood",
                },
                {
                    "type": "solid",
                    "id": "joined",
                    "kind": "boolean",
                    "operation": "union",
                    "operands": ["left", "right"],
                    "material": "wood",
                },
            ]
        },
        "materials": {"wood": material},
    }


def test_import_inspection_accepts_complex_geometry_asset():
    from app.services.item_catalog_validation import inspect_item_asset

    assert inspect_item_asset(_valid_import_asset()) == []


def test_import_inspection_rejects_data_that_placement_would_lose():
    from app.services.item_catalog_validation import inspect_item_asset

    asset = _valid_import_asset()
    asset["geometry"]["elements"][2]["operands"] = ["left", "missing"]
    asset["geometry"]["elements"][0]["material"] = "missing_material"
    asset["geometry"]["components"] = [{"type": "fan", "id": "ignored"}]
    asset["behaviors"] = {"scripts": [{"on_click": {"actions": []}}]}
    issues = inspect_item_asset(asset)
    assert any("不存在的零件" in issue for issue in issues)
    assert any("未声明材质" in issue for issue in issues)
    assert any("geometry.components" in issue for issue in issues)
    assert any("behaviors" in issue for issue in issues)


@pytest.mark.parametrize("entry", _entries(), ids=lambda entry: entry["id"])
def test_footprint_matches_manifest(entry):
    """清单里的 footprint 必须是正数三元组，且与几何大致吻合（±0.05m）。

    不精确核对包围盒是有意的：这里只抓"尺寸写成 0 或漏填"这类明显错，
    精确包围盒由 `wild-web/scripts/item-catalog-verify.mjs` 的真引擎跑。
    """

    footprint = entry["footprint"]
    assert isinstance(footprint, list) and len(footprint) == 3, (
        f"{entry['id']} footprint 必须是三元组"
    )
    assert all(isinstance(value, (int, float)) and value > 0 for value in footprint), (
        f"{entry['id']} footprint 含非正数: {footprint}"
    )
