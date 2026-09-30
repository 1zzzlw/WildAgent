"""测试构件实例清单的契约校验（§3.4）。"""

import pytest
from app.design.contracts import DesignDocument


def test_valid_component_instance_passes_validation():
    """有效的构件实例通过校验。"""
    
    doc = {
        "design_id": "test_001",
        "session_id": "session_001",
        "revision": 1,
        "requirements": {"source_request": "三层住宅"},
        "decisions": {
            "kind": "architecture",
            "complexity": {"level": "standard"},
            "envelope": {"system": "solid_wall"},
            "massing": {
                "shape": "rectangular",
                "width": 20,
                "depth": 15,
                "floors": 3,
                "modeled_floors": 3,
                "floor_height": 3.2,
            },
            "volumes": [
                {
                    "id": "volume_primary",
                    "x": 0,
                    "z": 0,
                    "width": 20,
                    "depth": 15,
                    "start_floor": 1,
                    "end_floor": 3,
                }
            ],
            "structural_grid": {"system": "wall_bearing", "x_bays": 4, "z_bays": 3},
            "facades": {
                "front": {"bays": 4, "ground_pattern": ["window"] * 4, "upper_pattern": ["window"] * 4},
                "back": {"bays": 4, "ground_pattern": ["window"] * 4, "upper_pattern": ["window"] * 4},
                "left": {"bays": 3, "ground_pattern": ["window"] * 3, "upper_pattern": ["window"] * 3},
                "right": {"bays": 3, "ground_pattern": ["window"] * 3, "upper_pattern": ["window"] * 3},
            },
            "roof": {"type": "flat"},
            "components": [
                {
                    "type": "balcony",
                    "host": "wall_front_1",
                    "size": {"width": 3.6, "depth": 1.4},
                    "form": {"railingHeight": 1.05},
                }
            ],
        },
    }
    
    # 应该不抛异常
    design = DesignDocument.model_validate(doc)
    assert design.decisions.components


def test_invalid_host_raises_error():
    """无效的host引用被拒绝。"""
    
    doc = {
        "design_id": "test_002",
        "session_id": "session_002",
        "revision": 1,
        "requirements": {"source_request": "三层住宅"},
        "decisions": {
            "kind": "architecture",
            "complexity": {"level": "standard"},
            "envelope": {"system": "solid_wall"},
            "massing": {
                "shape": "rectangular",
                "width": 20,
                "depth": 15,
                "floors": 3,
                "modeled_floors": 3,
                "floor_height": 3.2,
            },
            "volumes": [
                {
                    "id": "volume_primary",
                    "x": 0,
                    "z": 0,
                    "width": 20,
                    "depth": 15,
                    "start_floor": 1,
                    "end_floor": 3,
                }
            ],
            "structural_grid": {"system": "wall_bearing", "x_bays": 4, "z_bays": 3},
            "facades": {
                "front": {"bays": 4, "ground_pattern": ["window"] * 4, "upper_pattern": ["window"] * 4},
                "back": {"bays": 4, "ground_pattern": ["window"] * 4, "upper_pattern": ["window"] * 4},
                "left": {"bays": 3, "ground_pattern": ["window"] * 3, "upper_pattern": ["window"] * 3},
                "right": {"bays": 3, "ground_pattern": ["window"] * 3, "upper_pattern": ["window"] * 3},
            },
            "roof": {"type": "flat"},
            "components": [
                {
                    "type": "balcony",
                    "host": "nonexistent_host_xyz",  # 无效host
                    "size": {"width": 3.6, "depth": 1.4},
                }
            ],
        },
    }
    
    with pytest.raises(ValueError, match="不是有效的宿主引用"):
        DesignDocument.model_validate(doc)


def test_negative_size_raises_error():
    """负数尺寸被拒绝。"""
    
    doc = {
        "design_id": "test_003",
        "session_id": "session_003",
        "revision": 1,
        "requirements": {"source_request": "三层住宅"},
        "decisions": {
            "kind": "architecture",
            "complexity": {"level": "standard"},
            "envelope": {"system": "solid_wall"},
            "massing": {
                "shape": "rectangular",
                "width": 20,
                "depth": 15,
                "floors": 3,
                "modeled_floors": 3,
                "floor_height": 3.2,
            },
            "volumes": [
                {
                    "id": "volume_primary",
                    "x": 0,
                    "z": 0,
                    "width": 20,
                    "depth": 15,
                    "start_floor": 1,
                    "end_floor": 3,
                }
            ],
            "structural_grid": {"system": "wall_bearing", "x_bays": 4, "z_bays": 3},
            "facades": {
                "front": {"bays": 4, "ground_pattern": ["window"] * 4, "upper_pattern": ["window"] * 4},
                "back": {"bays": 4, "ground_pattern": ["window"] * 4, "upper_pattern": ["window"] * 4},
                "left": {"bays": 3, "ground_pattern": ["window"] * 3, "upper_pattern": ["window"] * 3},
                "right": {"bays": 3, "ground_pattern": ["window"] * 3, "upper_pattern": ["window"] * 3},
            },
            "roof": {"type": "flat"},
            "components": [
                {
                    "type": "balcony",
                    "host": "wall_front_1",
                    "size": {"width": -3.6, "depth": 1.4},  # 负数宽度
                }
            ],
        },
    }
    
    with pytest.raises(ValueError, match="必须是正数"):
        DesignDocument.model_validate(doc)


def test_excessive_size_raises_error():
    """过大的尺寸被拒绝。"""
    
    doc = {
        "design_id": "test_004",
        "session_id": "session_004",
        "revision": 1,
        "requirements": {"source_request": "三层住宅"},
        "decisions": {
            "kind": "architecture",
            "complexity": {"level": "standard"},
            "envelope": {"system": "solid_wall"},
            "massing": {
                "shape": "rectangular",
                "width": 20,
                "depth": 15,
                "floors": 3,
                "modeled_floors": 3,
                "floor_height": 3.2,
            },
            "volumes": [
                {
                    "id": "volume_primary",
                    "x": 0,
                    "z": 0,
                    "width": 20,
                    "depth": 15,
                    "start_floor": 1,
                    "end_floor": 3,
                }
            ],
            "structural_grid": {"system": "wall_bearing", "x_bays": 4, "z_bays": 3},
            "facades": {
                "front": {"bays": 4, "ground_pattern": ["window"] * 4, "upper_pattern": ["window"] * 4},
                "back": {"bays": 4, "ground_pattern": ["window"] * 4, "upper_pattern": ["window"] * 4},
                "left": {"bays": 3, "ground_pattern": ["window"] * 3, "upper_pattern": ["window"] * 3},
                "right": {"bays": 3, "ground_pattern": ["window"] * 3, "upper_pattern": ["window"] * 3},
            },
            "roof": {"type": "flat"},
            "components": [
                {
                    "type": "balcony",
                    "host": "wall_front_1",
                    "size": {"width": 150, "depth": 1.4},  # 过大的宽度
                }
            ],
        },
    }
    
    with pytest.raises(ValueError, match="超出合理范围"):
        DesignDocument.model_validate(doc)


def test_empty_components_list_passes():
    """空的构件列表（回退到配额模式）能通过校验。"""
    
    doc = {
        "design_id": "test_005",
        "session_id": "session_005",
        "revision": 1,
        "requirements": {"source_request": "三层住宅"},
        "decisions": {
            "kind": "architecture",
            "complexity": {"level": "standard"},
            "envelope": {"system": "solid_wall"},
            "massing": {
                "shape": "rectangular",
                "width": 20,
                "depth": 15,
                "floors": 3,
                "modeled_floors": 3,
                "floor_height": 3.2,
            },
            "volumes": [
                {
                    "id": "volume_primary",
                    "x": 0,
                    "z": 0,
                    "width": 20,
                    "depth": 15,
                    "start_floor": 1,
                    "end_floor": 3,
                }
            ],
            "structural_grid": {"system": "wall_bearing", "x_bays": 4, "z_bays": 3},
            "facades": {
                "front": {"bays": 4, "ground_pattern": ["window"] * 4, "upper_pattern": ["window"] * 4},
                "back": {"bays": 4, "ground_pattern": ["window"] * 4, "upper_pattern": ["window"] * 4},
                "left": {"bays": 3, "ground_pattern": ["window"] * 3, "upper_pattern": ["window"] * 3},
                "right": {"bays": 3, "ground_pattern": ["window"] * 3, "upper_pattern": ["window"] * 3},
            },
            "roof": {"type": "flat"},
            "components": [],  # 空列表
        },
    }
    
    # 应该不抛异常
    design = DesignDocument.model_validate(doc)
    assert design.decisions.components == []


def test_volume_host_formats_accepted():
    """体量相关的host格式被接受。"""
    
    doc = {
        "design_id": "test_006",
        "session_id": "session_006",
        "revision": 1,
        "requirements": {"source_request": "三层住宅"},
        "decisions": {
            "kind": "architecture",
            "complexity": {"level": "standard"},
            "envelope": {"system": "solid_wall"},
            "massing": {
                "shape": "rectangular",
                "width": 20,
                "depth": 15,
                "floors": 3,
                "modeled_floors": 3,
                "floor_height": 3.2,
            },
            "volumes": [
                {
                    "id": "volume_primary",
                    "x": 0,
                    "z": 0,
                    "width": 20,
                    "depth": 15,
                    "start_floor": 1,
                    "end_floor": 3,
                }
            ],
            "structural_grid": {"system": "wall_bearing", "x_bays": 4, "z_bays": 3},
            "facades": {
                "front": {"bays": 4, "ground_pattern": ["window"] * 4, "upper_pattern": ["window"] * 4},
                "back": {"bays": 4, "ground_pattern": ["window"] * 4, "upper_pattern": ["window"] * 4},
                "left": {"bays": 3, "ground_pattern": ["window"] * 3, "upper_pattern": ["window"] * 3},
                "right": {"bays": 3, "ground_pattern": ["window"] * 3, "upper_pattern": ["window"] * 3},
            },
            "roof": {"type": "flat"},
            "components": [
                {
                    "type": "balcony",
                    "host": "volume_primary",  # 直接体量id
                    "size": {"width": 3.6, "depth": 1.4},
                },
                {
                    "type": "window",
                    "host": "volume_primary_L2_south",  # 体量-层-面格式
                    "size": {"width": 1.2, "height": 1.4},
                },
            ],
        },
    }
    
    # 应该不抛异常
    design = DesignDocument.model_validate(doc)
    assert len(design.decisions.components) == 2
