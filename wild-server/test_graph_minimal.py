"""
最小测试：验证 LangGraph 完整流程（骨架 → 并行组件 → 合并 → 校验）

运行: python test_graph_minimal.py
"""
import asyncio
import json
from app.agent.graph import get_graph


async def test_skeleton_and_doors():
    """测试完整流程"""
    graph = get_graph()
    
    initial_state = {
        "user_message": "生成一个 10×8 米的中式庭院，前后各有一扇门，每面墙有两个窗户，需要中式坡屋顶",
        "building_type": "chinese_courtyard",
        "session_id": "test_001",
        "thinking_mode": True,  # ← 模型要求必须为 True
        "max_retries": 3,
        "retry_count": 0,
    }
    
    print("🚀 开始测试完整流程（骨架 → 并行组件 → 合并 → 校验）...")
    print(f"用户输入: {initial_state['user_message']}")
    print("-" * 60)
    
    try:
        final_state = await graph.ainvoke(initial_state)
        
        print("\n✅ 测试成功！")
        print("\n返回的状态键：", list(final_state.keys()))
        
        # 骨架统计
        if "skeleton_blueprint" in final_state:
            bp = final_state["skeleton_blueprint"]
            elements = bp.get("geometry", {}).get("elements", [])
            print(f"\n骨架: {len(elements)} 个构件")
        
        # 组件统计
        if "door_fragments" in final_state:
            doors = final_state["door_fragments"]
            print(f"门: {len(doors)} 个")
        
        if "window_fragments" in final_state:
            windows = final_state["window_fragments"]
            print(f"窗: {len(windows)} 个")
        
        if "roof_fragment" in final_state:
            roof = final_state["roof_fragment"]
            if roof:
                print(f"屋顶: {roof.get('id', '?')}")
        
        if "railing_fragments" in final_state:
            railings = final_state["railing_fragments"]
            print(f"栏杆: {len(railings)} 个")
        
        # 合并结果
        if "merged_blueprint" in final_state:
            merged = final_state["merged_blueprint"]
            elements = merged.get("geometry", {}).get("elements", [])
            components = merged.get("geometry", {}).get("components", [])
            print(f"\n合并后 Blueprint: {len(elements)} elements + {len(components)} components")
        
        # 校验结果
        if "validation_results" in final_state:
            results = final_state["validation_results"]
            total = len(results)
            errors = sum(1 for r in results if r.get("has_error"))
            warnings = sum(1 for r in results if r.get("has_warning") and not r.get("has_error"))
            passed = total - errors - warnings
            print(f"\n校验结果: {total} 步，✅ {passed} 通过，⚠️  {warnings} 警告，❌ {errors} 错误")
        
        if "failed_components" in final_state:
            failed = final_state["failed_components"]
            if failed:
                print(f"\n失败组件: {len(failed)} 个")
                for fc in failed[:3]:  # 只显示前3个
                    print(f"  - {fc.get('component_id')}: {fc.get('error_step')}")
        
        # 最终状态
        status = final_state.get("status", "?")
        print(f"\n最终状态: {status}")
        
        if "error" in final_state and final_state["error"]:
            print(f"⚠️  错误: {final_state['error']}")
        
        # 保存最终 Blueprint（可选）
        if "final_blueprint" in final_state:
            final_bp = final_state["final_blueprint"]
            with open("test_output_blueprint.json", "w", encoding="utf-8") as f:
                json.dump(final_bp, f, ensure_ascii=False, indent=2)
            print(f"\n✅ 最终 Blueprint 已保存到 test_output_blueprint.json")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_skeleton_and_doors())
