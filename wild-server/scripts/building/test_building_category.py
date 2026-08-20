"""测试建筑类型分类和 RAG 检索"""
import asyncio
from app.spec.loader import SpecQuery


async def test_building_category_filter():
    """测试带 building_category 过滤的 RAG 检索"""
    from app.services.agent_service import agent_service
    
    # 重新同步知识库索引
    print("正在同步知识库索引...")
    updated = agent_service.spec_loader.sync_index()
    print(f"✅ 已同步 {updated} 个文档片段\n")
    
    # 测试用例
    test_cases = [
        {
            "query": "社区商铺",
            "filter": {"doc_type": "building_type", "building_category": "commercial"},
            "expected_categories": ["commercial"],
        },
        {
            "query": "现代别墅",
            "filter": {"doc_type": "building_type", "building_category": "residential"},
            "expected_categories": ["residential"],
        },
        {
            "query": "厂房",
            "filter": {"doc_type": "building_type", "building_category": "industrial"},
            "expected_categories": ["industrial"],
        },
        {
            "query": "建筑类型",
            "filter": {"doc_type": "building_type"},
            "expected_categories": ["commercial", "residential", "industrial", "public"],
        },
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"{'='*60}")
        print(f"测试 {i}: {case['query']}")
        print(f"过滤条件: {case['filter']}")
        print(f"{'='*60}")
        
        # 执行检索
        results = agent_service.spec_loader.retrieve(
            query=case["query"],
            metadata_filter=case["filter"],
        )
        
        # 统计结果
        categories = {}
        for result in results:
            cat = result.metadata.get("building_category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1
        
        print(f"\n检索到 {len(results)} 个结果:")
        for cat, count in categories.items():
            print(f"  - {cat}: {count} 个")
        
        # 显示前3个结果
        print(f"\n前3个结果:")
        for j, result in enumerate(results[:3], 1):
            print(f"  {j}. {result.metadata.get('source', '?')} / {result.metadata.get('heading', '?')}")
            print(f"     entity_name: {result.metadata.get('entity_name', '?')}")
            print(f"     building_category: {result.metadata.get('building_category', '?')}")
            distance_str = f"{result.distance:.4f}" if isinstance(result.distance, float) else "N/A"
            print(f"     distance: {distance_str}")
        
        # 验证是否符合预期
        actual_categories = set(categories.keys())
        expected_categories = set(case["expected_categories"])
        
        if actual_categories <= expected_categories:
            print(f"\n✅ 测试通过: 召回的建筑类型符合预期")
        else:
            unexpected = actual_categories - expected_categories
            print(f"\n⚠️  警告: 召回了非预期的建筑类型: {unexpected}")
        
        print()


if __name__ == "__main__":
    asyncio.run(test_building_category_filter())
