"""
测试骨架节点建议组件功能 + 组件工具校验修复

运行: python test_suggested_components.py
"""
import asyncio
from app.agent.graph import get_graph


async def test_suggested_components():
    """测试建议组件功能"""
    
    thinking_buffer = {}  # node_name -> [deltas]
    
    async def on_reasoning_delta(node_name: str, delta: str):
        """模拟前端接收思考内容"""
        if node_name not in thinking_buffer:
            thinking_buffer[node_name] = []
        thinking_buffer[node_name].append(delta)
        print(f"[{node_name}思考] {delta}", end="", flush=True)
    
    test_cases = [
        {
            "name": "欧式别墅（应建议 door, window, roof, balcony）",
            "message": "生成一个10×8米的欧式别墅",
            "expected_components": ["door", "window", "roof"],
        },
        {
            "name": "中式凉亭（应建议 door, window, roof, cornice, railing）",
            "message": "生成一个中式凉亭，带飞檐和栏杆",
            "expected_components": ["door", "window", "roof", "cornice", "railing"],
        },
        {
            "name": "无屋顶建筑（不应建议 roof）",
            "message": "生成一个平顶现代建筑，不要屋顶",
            "expected_components": ["door", "window"],
            "not_expected": ["roof"],
        },
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print("\n" + "=" * 80)
        print(f"测试 {i}/{len(test_cases)}: {test_case['name']}")
        print("=" * 80)
        print(f"用户输入: {test_case['message']}")
        print("-" * 80)
        
        thinking_buffer.clear()
        
        initial_state = {
            "user_message": test_case["message"],
            "building_type": "modern_house",
            "session_id": f"test_suggested_{i}",
            "thinking_mode": True,
            "on_reasoning_delta": on_reasoning_delta,
            "max_retries": 3,
            "retry_count": 0,
        }
        
        try:
            graph = get_graph()
            result = await graph.ainvoke(initial_state)
            
            suggested = result.get("suggested_components", [])
            print(f"\n\n建议的组件: {suggested}")
            
            # 检查是否符合预期
            expected = test_case.get("expected_components", [])
            not_expected = test_case.get("not_expected", [])
            
            if expected:
                for comp in expected:
                    if comp in suggested:
                        print(f"  ✅ {comp} - 符合预期")
                    else:
                        print(f"  ⚠️  {comp} - 未被建议（可能不是必需）")
            
            if not_expected:
                for comp in not_expected:
                    if comp not in suggested:
                        print(f"  ✅ {comp} - 正确排除")
                    else:
                        print(f"  ❌ {comp} - 不应被建议")
            
            # 检查思考内容
            print(f"\n思考节点统计:")
            for node_name, deltas in thinking_buffer.items():
                total_chars = sum(len(d) for d in deltas)
                print(f"  - {node_name}: {total_chars} 字符, {len(deltas)} 个 delta")
            
            # 检查生成结果
            final_bp = result.get("final_blueprint") or result.get("merged_blueprint")
            if final_bp:
                elements = final_bp.get("geometry", {}).get("elements", [])
                components = final_bp.get("geometry", {}).get("components", [])
                
                # 统计生成的组件类型
                component_types = {}
                for comp in components:
                    comp_type = comp.get("type")
                    component_types[comp_type] = component_types.get(comp_type, 0) + 1
                
                print(f"\n生成的组件:")
                print(f"  - 构件: {len(elements)} 个")
                print(f"  - 组件: {len(components)} 个")
                print(f"  - 组件类型: {component_types}")
                
                # 检查组件诊断信息
                print(f"\n组件诊断:")
                for comp_type in suggested:
                    diag_key = f"{comp_type}_diag"
                    diag = result.get(diag_key, {})
                    if diag:
                        skipped = diag.get("skipped", False)
                        fragment_count = diag.get("fragment_count", 0)
                        validation_applied = diag.get("validation_applied", False)
                        
                        status = "跳过" if skipped else f"{fragment_count}个"
                        validation_status = "已修复" if validation_applied else "无需修复"
                        print(f"  - {comp_type}: {status}, 校验: {validation_status}")
            
            status = result.get("status", "?")
            print(f"\n状态: {status}")
            
            if result.get("error"):
                print(f"⚠️  错误: {result['error']}")
        
        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_suggested_components())
