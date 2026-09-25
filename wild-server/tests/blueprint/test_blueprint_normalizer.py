"""
Blueprint Normalizer 测试
"""
import pytest
from app.utils.blueprint_normalizer import normalize_blueprint_for_delivery


def test_strip_unknown_fields():
    """测试剥离未知字段"""
    bp = {
        "meta": {"version": "1.1", "type": "building", "name": "测试"},
        "geometry": {
            "components": [
                {
                    "type": "door",
                    "id": "door1",
                    "parentWall": "wall1",
                    "from": [0, 0, 0],
                    "width": 1.0,
                    "height": 2.0,
                    "role": "entrance",  # 未知字段
                }
            ]
        }
    }
    
    normalized, report = normalize_blueprint_for_delivery(bp)
    
    # 未知字段应该被剥离
    assert "role" not in normalized["geometry"]["components"][0]
    assert "door1.role" in report.stripped_fields


def test_repair_interaction():
    """测试修复 interaction 字段"""
    bp = {
        "meta": {"version": "1.1", "type": "building", "name": "测试"},
        "geometry": {
            "components": [
                {
                    "type": "window",
                    "id": "win1",
                    "parentWall": "wall1",
                    "from": [0, 0, 0],
                    "width": 1.5,
                    "height": 1.2,
                    "interaction": {
                        "mode": "swing",
                        "openAngle": 0,  # 应该 > 0
                        "hingeSide": "bottom"  # 只能是 left/right
                    }
                }
            ]
        }
    }
    
    normalized, report = normalize_blueprint_for_delivery(bp)
    
    comp = normalized["geometry"]["components"][0]
    assert comp["interaction"]["openAngle"] == 90.0
    assert comp["interaction"]["hingeSide"] == "left"
    assert any("openAngle" in f for f in report.repaired_fields)


def test_repair_from_z():
    """测试修复 from[2] 偏移"""
    bp = {
        "meta": {"version": "1.1", "type": "building", "name": "测试"},
        "geometry": {
            "components": [
                {
                    "type": "door",
                    "id": "door1",
                    "parentWall": "wall1",
                    "from": [1.0, 0.0, 0.5],  # from[2] 应该 ≈ 0
                    "width": 1.0,
                    "height": 2.0,
                }
            ]
        }
    }
    
    normalized, report = normalize_blueprint_for_delivery(bp)
    
    comp = normalized["geometry"]["components"][0]
    assert comp["from"][2] == 0.0
    assert any("from[2]" in f for f in report.repaired_fields)


def test_deduplicate_walls():
    """测试双墙去重"""
    bp = {
        "meta": {"version": "1.1", "type": "building", "name": "测试"},
        "geometry": {
            "elements": [
                {
                    "type": "wall",
                    "id": "wall1",
                    "from": [0, 0, 0],
                    "to": [10, 3, 0],
                    "thickness": 0.2
                },
                {
                    "type": "wall",
                    "id": "wall1_reverse_dup",
                    "from": [10, 0, 0],
                    "to": [0, 3, 0],
                    "thickness": 0.2
                }
            ]
        }
    }
    
    normalized, report = normalize_blueprint_for_delivery(bp)
    
    # 应该只保留一个墙
    walls = [e for e in normalized["geometry"]["elements"] if e["type"] == "wall"]
    assert len(walls) == 1
    assert walls[0]["id"] == "wall1"


def test_convert_old_column():
    """测试旧版 column 转换"""
    bp = {
        "meta": {"version": "1.1", "type": "building", "name": "测试"},
        "geometry": {
            "elements": [
                {
                    "type": "column",
                    "id": "col1",
                    "dimensions": [0, 0, 0],  # 旧版字段
                    "radius": 0.3,  # 旧版字段
                    "style": "classical"  # 旧版枚举
                }
            ]
        }
    }
    
    normalized, report = normalize_blueprint_for_delivery(bp)
    
    col = normalized["geometry"]["elements"][0]
    # 应该转换为新版字段
    assert "base" in col
    assert "height" in col
    assert "bottomRadius" in col
    assert "topRadius" in col
    assert "dimensions" not in col
    assert "radius" not in col
    assert col["style"] == "corinthian"  # 映射为新枚举
    assert any("column" in f for f in report.repaired_fields)


def test_idempotent():
    """测试幂等性"""
    bp = {
        "meta": {"version": "1.1", "type": "building", "name": "测试"},
        "geometry": {
            "elements": [
                {
                    "type": "wall",
                    "id": "wall1",
                    "from": [0, 0, 0],
                    "to": [10, 0, 0],
                    "thickness": 0.2
                }
            ],
            "components": [
                {
                    "type": "door",
                    "id": "door1",
                    "parentWall": "wall1",
                    "from": [1.0, 0.0, 0.0],
                    "width": 1.0,
                    "height": 2.0,
                }
            ]
        }
    }
    
    # 第一次归一化
    normalized1, report1 = normalize_blueprint_for_delivery(bp)
    
    # 第二次归一化（应该无变化）
    normalized2, report2 = normalize_blueprint_for_delivery(normalized1)
    
    # 应该相同
    assert normalized1 == normalized2
    # 第二次应该没有修复
    assert not report2.stripped_fields
    assert not report2.repaired_fields
    assert not report2.dropped_components


# ── body 元素：只迁移不丢弃 ──────────────────────────────────────────────
# 回归背景：这里曾无条件丢掉 `type == "body"`（理由写的是"body 不是建筑元素"），
# 于是物件链里"生成一个小人"的产物在交付归一时静默消失——批次合并明明报
# "已并入 1 个元素"，收尾归一后蓝图为空，`validate_design_brief` 报
# "body 数量 0 少于设计下限 1"。`body` 现在是 schema 合法类型
# （`$defs/body`）且引擎有 builder（`wild-core` registry，status=partial）。


def _body_blueprint(body: dict) -> dict:
    return {
        "meta": {"version": "1.1", "type": "asset", "name": "小人"},
        "geometry": {
            "elements": [
                body,
                {"type": "primitive", "id": "p_01", "shape": "cylinder",
                 "position": [0, 0.5, 0], "height": 1.0, "radius": 0.2},
            ],
            "components": [],
        },
    }


def test_body_element_survives_delivery_normalization():
    """合规 body 必须原样保留：它是用户点名要交付的几何本体。"""

    bp = _body_blueprint({
        "type": "body", "id": "body_01", "position": [0, 0, 0], "height": 1.72,
        "build": "athletic", "headShape": "round", "armLength": 1.0,
        "legLength": 1.0, "cloakLength": 0.6, "hoodUp": False,
    })

    normalized, report = normalize_blueprint_for_delivery(bp)
    types = [el.get("type") for el in normalized["geometry"]["elements"]]

    assert "body" in types
    assert not report.dropped_elements
    assert not report.repaired_fields  # 已经合规，不该被改动


def test_legacy_body_is_migrated_not_dropped():
    """旧场景取值（实测 `build: "average"`、`cloakLength: 0`）按引擎中性语义迁移。

    `wild-core/src/primitive/geometry/body.ts` 对未知 build 退化为缩放 1（= athletic）、
    对 `cloakLength <= 0.3` 不生成斗篷——迁移后观感不变，但几何不再丢失。
    """

    bp = _body_blueprint({
        "type": "body", "id": "person_1", "position": [2.6, 0, 0.8], "height": 1.75,
        "build": "average", "headShape": "round", "armLength": 0.6,
        "legLength": 0.9, "cloakLength": 0, "hoodUp": False,
    })

    normalized, report = normalize_blueprint_for_delivery(bp)
    body = next(el for el in normalized["geometry"]["elements"] if el.get("type") == "body")

    assert body["build"] == "athletic"
    assert body["cloakLength"] == 0.3   # 0.3 即"不披斗篷"，与 0 等价
    assert body["armLength"] == 0.6     # 区间内，保持原值
    assert not report.dropped_elements


def test_incomplete_body_gets_neutral_defaults():
    """残缺 body 补中性缺省，仍然保留——缺字段是校验器该报的事，不是删除的理由。"""

    bp = _body_blueprint({"type": "body", "id": "body_x", "position": [0, 0, 0]})

    normalized, report = normalize_blueprint_for_delivery(bp)
    body = next(el for el in normalized["geometry"]["elements"] if el.get("type") == "body")

    assert body["height"] == 1.7
    assert body["build"] == "athletic"
    assert body["headShape"] == "round"
    assert body["cloakLength"] == 0.3
    assert body["hoodUp"] is False
    assert not report.dropped_elements
