"""验证层数约束识别修复"""
from app.agent.planning.requirements import compile_structured_requirements


def verify_fix():
    """验证原始错误场景已修复"""
    
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
    
    print("=" * 70)
    print("验证结果:")
    print("=" * 70)
    print(f"\n识别为层数约束的数量: {len(floor_count_reqs)} (预期: 1)")
    
    if len(floor_count_reqs) == 1:
        print("✓ 正确！只有1个被识别为层数约束")
        req = floor_count_reqs[0]
        print(f"  - 约束ID: {req['id']}")
        print(f"  - 描述: {req['description'][:50]}...")
        print(f"  - 期望层数: {req['expected']} (预期: 3)")
        
        if req['expected'] == 3:
            print("✓ 层数正确！")
        else:
            print(f"✗ 层数错误！期望3，实际{req['expected']}")
            return False
    else:
        print(f"✗ 错误！应该只有1个层数约束，实际有{len(floor_count_reqs)}个")
        for req in floor_count_reqs:
            print(f"  - {req['id']}: {req['description'][:50]}...")
        return False
    
    # 验证其他的没有被误判为层数约束
    print("\n检查其他约束:")
    req_by_id = {req["id"]: req for req in requirements}
    
    test_cases = [
        ("req_task_1_2", "主体长宽尺寸确定...（层高描述）"),
        ("req_task_3_1", "一层外墙、内墙...（材质描述）"),
        ("req_task_4_1", "为一层主要空间...（门窗描述）"),
        ("req_task_6_1", "屋顶 position...（位置描述）"),
    ]
    
    all_correct = True
    for req_id, description in test_cases:
        if req_id in req_by_id:
            req = req_by_id[req_id]
            if req["kind"] != "architecture_floor_count":
                print(f"✓ {req_id}: 正确识别为 {req['kind']} - {description}")
            else:
                print(f"✗ {req_id}: 错误识别为 architecture_floor_count - {description}")
                all_correct = False
        else:
            print(f"? {req_id}: 未找到该约束")
    
    print("\n" + "=" * 70)
    if all_correct and len(floor_count_reqs) == 1 and floor_count_reqs[0]['expected'] == 3:
        print("✓✓✓ 所有测试通过！修复成功！")
        print("=" * 70)
        return True
    else:
        print("✗✗✗ 部分测试失败")
        print("=" * 70)
        return False


if __name__ == "__main__":
    success = verify_fix()
    exit(0 if success else 1)
