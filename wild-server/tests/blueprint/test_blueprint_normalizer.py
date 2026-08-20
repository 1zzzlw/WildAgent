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
                    "to": [10, 0, 0],
                    "thickness": 0.2
                },
                {
                    "type": "wall",
                    "id": "wall1_dup",
                    "from": [0, 0, 0],
                    "to": [10, 0, 0],
                    "thickness": 0.2
                }
            ]
        }
    }
    
    normalized, report = normalize_blueprint_for_delivery(bp)
    
    # 应该只保留一个墙
    walls = [e for e in normalized["geometry"]["elements"] if e["type"] == "wall"]
    assert len(walls) == 1


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
