"""测试层数约束识别的修复：确保不会把楼层属性描述误判为总层数约束"""
import pytest
from app.agent.planning.requirements import compile_structured_requirements


def test_floor_count_not_confused_with_floor_attributes():
    """确保"一层XX"这样的楼层属性描述不会被误判为建筑总层数约束"""
    
    # 这些是对楼层属性的描述，不应该被识别为 architecture_floor_count
    test_cases = [
        {
            "description": "主体长宽尺寸确定，如长度12米，宽度8米，地下室层高不小于2.4米，一层层高不小于2.8米。",
            "should_be_floor_count": False,
            "reason": "这是对层高的描述，不是对建筑总层数的约束"
        },
        {
            "description": "一层外墙、内墙、楼板使用如'wood'、'plaster'等材质。",
            "should_be_floor_count": False,
            "reason": "这是对材质的描述，不是对建筑总层数的约束"
        },
        {
            "description": "为一层主要空间（如客厅、卧室区域）的门窗预留开口位置。",
            "should_be_floor_count": False,
            "reason": "这是对门窗开口的描述，不是对建筑总层数的约束"
        },
        {
            "description": "屋顶 position 的 Y 坐标与一层墙顶齐平。",
            "should_be_floor_count": False,
            "reason": "这是对屋顶位置的描述，不是对建筑总层数的约束"
        },
    ]
    
    # 这些才是真正的层数约束
    floor_count_cases = [
        {
            "description": "建筑主体包含地下室、一层及半层阁楼（利用屋顶空间）共三层几何结构。",
            "should_be_floor_count": True,
            "expected_count": 3,
            "reason": "明确说了'共三层几何结构'"
        },
        {
            "description": "建筑分为两层，一层为公共空间，二层为私密空间。",
            "should_be_floor_count": True,
            "expected_count": 2,
            "reason": "明确说了'分为两层'"
        },
        {
            "description": "建筑共一层，地面层包含所有功能空间。",
            "should_be_floor_count": True,
            "expected_count": 1,
            "reason": "明确说了'共一层'"
        },
    ]
    
    # 测试不应该被识别为层数约束的情况
    for case in test_cases:
        plan = {
            "dynamic_tasks": [{
                "id": "task_test",
                "phase": "architecture",
                "acceptance": [case["description"]]
            }]
        }
        
        requirements = compile_structured_requirements(plan)
        assert len(requirements) == 1, f"应该只有一个requirement: {case['description']}"
        
        req = requirements[0]
        if case["should_be_floor_count"]:
            assert req["kind"] == "architecture_floor_count", \
                f"应该被识别为层数约束: {case['description']}\n原因: {case['reason']}"
        else:
            assert req["kind"] != "architecture_floor_count", \
                f"不应该被识别为层数约束，实际类型: {req['kind']}\n描述: {case['description']}\n原因: {case['reason']}"
    
    # 测试应该被识别为层数约束的情况
    for case in floor_count_cases:
        plan = {
            "dynamic_tasks": [{
                "id": "task_test",
                "phase": "architecture",
                "acceptance": [case["description"]]
            }]
        }
        
        requirements = compile_structured_requirements(plan)
        assert len(requirements) == 1, f"应该只有一个requirement: {case['description']}"
        
        req = requirements[0]
        assert req["kind"] == "architecture_floor_count", \
            f"应该被识别为层数约束，实际类型: {req['kind']}\n描述: {case['description']}\n原因: {case['reason']}"
        
        if "expected_count" in case:
            assert req["expected"] == case["expected_count"], \
                f"期望层数不匹配: expected={req['expected']}, want={case['expected_count']}\n描述: {case['description']}"


def test_bugfix_original_error_case():
    """回归测试：验证原始错误场景已修复"""
    
    # 这是导致LangSmith Studio失败的原始场景
    plan = {
        "dynamic_tasks": [
            {
                "id": "task_1",
                "phase": "architecture",
                "acceptance": [
                    "建筑主体包含地下室、一层及半层阁楼（利用屋顶空间）共三层几何结构。",
                    "主体长宽尺寸确定，如长度12米，宽度8米，地下室层高不小于2.4米，一层层高不小于2.8米。",
                ]
            },
            {
                "id": "task_3",
                "phase": "material_plan",
                "acceptance": [
                    "一层外墙、内墙、楼板使用如'wood'、'plaster'等材质。",
                ]
            },
            {
                "id": "task_4",
                "phase": "skeleton",
                "acceptance": [
                    "为一层主要空间（如客厅、卧室区域）的门窗预留开口位置。",
                ]
            },
            {
                "id": "task_6",
                "phase": "skeleton",
                "acceptance": [
                    "屋顶 position 的 Y 坐标与一层墙顶齐平。",
                ]
            },
        ]
    }
    
    requirements = compile_structured_requirements(plan)
    
    # 统计有多少个被识别为 architecture_floor_count
    floor_count_reqs = [req for req in requirements if req["kind"] == "architecture_floor_count"]
    
    # 只有 task_1 的第一个 acceptance 应该被识别为层数约束（共三层）
    assert len(floor_count_reqs) == 1, \
        f"应该只有1个层数约束，实际有 {len(floor_count_reqs)} 个: {[req['description'] for req in floor_count_reqs]}"
    
    assert floor_count_reqs[0]["expected"] == 3, \
        f"层数应该是3，实际是 {floor_count_reqs[0]['expected']}"
    
    assert "共三层几何结构" in floor_count_reqs[0]["description"], \
        f"识别的层数约束应该是'共三层几何结构'那一条，实际是: {floor_count_reqs[0]['description']}"
    
    # 验证其他的没有被误判为层数约束
    req_by_id = {req["id"]: req for req in requirements}
    
    # req_task_1_2: "主体长宽尺寸确定..." - 不应该是层数约束
    assert "req_task_1_2" in req_by_id
    assert req_by_id["req_task_1_2"]["kind"] != "architecture_floor_count", \
        f"req_task_1_2 不应该是层数约束: {req_by_id['req_task_1_2']}"
    
    # req_task_3_1: "一层外墙..." - 不应该是层数约束
    assert "req_task_3_1" in req_by_id
    assert req_by_id["req_task_3_1"]["kind"] != "architecture_floor_count", \
        f"req_task_3_1 不应该是层数约束: {req_by_id['req_task_3_1']}"
    
    # req_task_4_1: "为一层主要空间..." - 不应该是层数约束
    assert "req_task_4_1" in req_by_id
    assert req_by_id["req_task_4_1"]["kind"] != "architecture_floor_count", \
        f"req_task_4_1 不应该是层数约束: {req_by_id['req_task_4_1']}"
    
    # req_task_6_1: "屋顶..." - 不应该是层数约束
    assert "req_task_6_1" in req_by_id
    assert req_by_id["req_task_6_1"]["kind"] != "architecture_floor_count", \
        f"req_task_6_1 不应该是层数约束: {req_by_id['req_task_6_1']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
