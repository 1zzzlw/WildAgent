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


def test_unknown_host_is_delegated_not_rejected():
    """解析不了的 host **不再**在契约层阻断（2026-10-08 事故，第二例）。

    旧行为：按 `wall_/volume_/slot_/door_/window_` 前缀白名单判，认不出就抛
    `不是有效的宿主引用` ⇒ `architecture` 节点 `status=failed` ⇒ 整轮生成中止。

    为什么必须改：host 的命名空间有一半是**编译期才铸出来**的
    （`roof_planned_NN`、`roof_01`、`cornice_*`…），契约层手里只有体量/立面，
    构造不出这份名单 —— 当时连编译器自己的合法屋面 id 都被这道闸拒掉。
    解析只有一个实现（编译器），认不出就记 `instance_dropped` 交修复环。
    这里钉住"契约层不再替编译器做判定"；"确实被丢弃"由
    `tests/compiler/test_component_instances.py` 钉。
    """

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
                    "host": "nonexistent_host_xyz",  # 悬空引用：不在这里阻断
                    "size": {"width": 3.6, "depth": 1.4},
                },
                {
                    "type": "cornice",  # 编译器自铸的屋面 id：契约层构造不出，更不该拒
                    "host": "roof_planned_01",
                    "size": {"height": 0.45},
                },
            ],
        },
    }

    design = DesignDocument.model_validate(doc)
    assert [item.host for item in design.decisions.components] == [
        "nonexistent_host_xyz",
        "roof_planned_01",
    ]


def test_host_is_required_to_be_non_empty():
    """`host` 仍必须是长度 ≥1 的字符串——形态可以判，解析不判。"""

    doc = {
        "design_id": "test_007",
        "session_id": "session_007",
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
            "components": [{"type": "balcony", "host": "", "size": {"width": 3.6}}],
        },
    }

    with pytest.raises(ValueError):
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
