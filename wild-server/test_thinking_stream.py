"""
测试 LangGraph 流式思考功能

运行: python test_thinking_stream.py
"""
import asyncio
from app.agent.graph import get_graph


async def test_thinking_stream():
    """测试骨架节点的流式思考"""
    
    thinking_buffer = []
    
    async def on_reasoning_delta(node_name: str, delta: str):
        """模拟前端接收思考内容"""
        thinking_buffer.append((node_name, delta))
        print(f"[思考:{node_name}] {delta}", end="", flush=True)
    
    initial_state = {
        "user_message": "生成一个10×8米的欧式别墅",
        "building_type": "modern_house",
        "session_id": "test_thinking_001",
        "thinking_mode": True,
        "on_reasoning_delta": on_reasoning_delta,
        "max_retries": 3,
        "retry_count": 0,
    }
    
    print("=" * 60)
    print("🧠 测试流式思考功能")
    print("=" * 60)
    print(f"用户输入: {initial_state['user_message']}")
    print(f"思考模式: {initial_state['thinking_mode']}")
    print("-" * 60)
    
    try:
        graph = get_graph()
        result = await graph.ainvoke(initial_state)
        
        print("\n" + "=" * 60)
        print("✅ 测试完成")
        print("=" * 60)
        
        # 统计思考内容
        total_thinking = sum(len(delta) for _, delta in thinking_buffer)
        nodes_with_thinking = set(node for node, _ in thinking_buffer)
        
        print(f"\n思考统计:")
        print(f"  - 总思考字符数: {total_thinking}")
        print(f"  - 思考节点数: {len(nodes_with_thinking)}")
        print(f"  - 节点列表: {', '.join(nodes_with_thinking)}")
        
        # 最终结果
        status = result.get("status", "?")
        final_bp = result.get("final_blueprint") or result.get("merged_blueprint")
        
        if final_bp:
            elements = final_bp.get("geometry", {}).get("elements", [])
            components = final_bp.get("geometry", {}).get("components", [])
            print(f"\n生成结果:")
            print(f"  - 状态: {status}")
            print(f"  - 构件: {len(elements)} 个")
            print(f"  - 组件: {len(components)} 个")
        
        if result.get("error"):
            print(f"\n⚠️  错误: {result['error']}")
    
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_thinking_stream())
