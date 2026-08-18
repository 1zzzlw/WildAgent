"""
P0 方案使用示例

展示如何在生成节点中集成结构自检和查询改写
"""
import asyncio
from unittest.mock import AsyncMock, Mock


async def example_structure_validator():
    """示例 1: 结构自检的使用"""
    print("=" * 60)
    print("示例 1: 结构自检 (Structure Validator)")
    print("=" * 60)
    
    from app.agent.validators import StructureValidator, JsonSchemaValidator
    
    # 模拟 LLM（实际使用时用真实 LLM）
    mock_llm = AsyncMock()
    mock_response = Mock()
    # 返回正确格式的 JSON（包含 name 字段）
    mock_response.content = '{"type": "building", "name": "Modern Villa", "floors": 2}'
    mock_llm.ainvoke.return_value = mock_response
    
    # 创建验证器
    schema_validator = JsonSchemaValidator()
    validator = StructureValidator(schema_validator, mock_llm)
    
    # 模拟 LLM 输出（缺少必填字段）
    llm_output = {
        "type": "building",
        # 缺少 "name" 字段
        "floors": 2
    }
    
    # 目标 Schema
    schema = {
        "type": "object",
        "required": ["type", "name", "floors"],
        "properties": {
            "type": {"type": "string"},
            "name": {"type": "string"},
            "floors": {"type": "integer"}
        }
    }
    
    print("\n原始 LLM 输出（缺少 name 字段）:")
    print(llm_output)
    
    # 执行验证和自动修复
    result, errors = await validator.validate_and_fix(
        llm_output,
        node_name="example_node",
        schema=schema,
        max_retries=1  # 允许 LLM 修复一次
    )
    
    print("\n验证结果:")
    if errors:
        print(f"发现 {len(errors)} 个错误（修复前）:")
        for err in errors:
            print(f"  - {err}")
    
    print("\n修复后的输出:")
    print(result)
    
    # 验证修复是否成功
    if "name" in result:
        print(f"✓ 成功修复: 已添加 name 字段 = '{result['name']}'")
    else:
        print(f"✗ 修复失败: name 字段仍然缺失")
    
    print("\n" + "=" * 60)


async def example_query_rewriter():
    """示例 2: 查询改写的使用"""
    print("\n示例 2: 查询改写 (Query Rewriter)")
    print("=" * 60)
    
    from app.agent.rag import QueryRewriter
    from app.config import get_domain_config
    
    # 加载领域配置
    domain_schema = get_domain_config().get_schema()
    print(f"\n当前领域: {domain_schema.get('domain')}")
    print(f"实体类型数: {len(domain_schema.get('entity_types', []))}")
    
    # 模拟 LLM
    mock_llm = AsyncMock()
    mock_response = Mock()
    mock_response.content = '''
{
    "entity_type": "building",
    "attributes": {
        "style": "modern",
        "size": "large"
    },
    "features": ["energy_efficient", "open_plan"],
    "constraints": {},
    "keywords": ["现代", "建筑", "大型", "节能", "开放式", "设计", "空间", "通透"]
}
'''
    mock_llm.ainvoke.return_value = mock_response
    
    # 创建查询改写器
    rewriter = QueryRewriter(mock_llm, domain_schema)
    
    # 用户自然语言查询
    user_query = "我想要一个现代风格的大型节能建筑，要有开放式布局"
    
    print(f"\n原始用户查询:")
    print(f"  {user_query}")
    
    # 执行查询改写
    structured_query = await rewriter.rewrite(user_query)
    
    print(f"\n改写后的结构化查询:")
    print(f"  实体类型: {structured_query.get('entity_type')}")
    print(f"  属性: {structured_query.get('attributes')}")
    print(f"  特性: {structured_query.get('features')}")
    print(f"  关键词: {structured_query.get('keywords')[:5]}...")
    
    print("\n" + "=" * 60)


async def example_integration_in_node():
    """示例 3: 在生成节点中的完整集成"""
    print("\n示例 3: 在生成节点中的完整集成")
    print("=" * 60)
    
    from app.agent.validators import StructureValidator, JsonSchemaValidator
    from app.agent.rag import QueryRewriter
    from app.config import get_domain_config
    
    # 模拟节点函数
    async def mock_generation_node(user_message: str):
        """模拟一个生成节点"""
        
        # 1. 查询改写（RAG 检索前）
        print("\n[步骤 1] 查询改写...")
        domain_schema = get_domain_config().get_schema()
        
        # 模拟 LLM
        mock_llm_rewrite = AsyncMock()
        mock_response = Mock()
        mock_response.content = '{"entity_type": "door", "keywords": ["门", "入口", "现代"]}'
        mock_llm_rewrite.ainvoke.return_value = mock_response
        
        rewriter = QueryRewriter(mock_llm_rewrite, domain_schema)
        structured_query = await rewriter.rewrite(user_message)
        
        print(f"  改写结果: entity_type={structured_query.get('entity_type')}")
        
        # 2. 使用改写后的查询进行 RAG 检索（模拟）
        print("\n[步骤 2] RAG 检索...")
        keywords = " ".join(structured_query.get("keywords", []))
        print(f"  检索关键词: {keywords}")
        print(f"  元数据过滤: entity_type={structured_query.get('entity_type')}")
        
        # 模拟 RAG 返回
        spec_text = "[模拟的 RAG 检索结果: 门的设计规范...]"
        
        # 3. LLM 生成（模拟）
        print("\n[步骤 3] LLM 生成...")
        llm_output = {
            "type": "door",
            "width": 1.0,
            "height": 2.2
            # 假设 LLM 忘记了 "id" 字段
        }
        print(f"  LLM 原始输出: {llm_output}")
        
        # 4. 结构自检
        print("\n[步骤 4] 结构自检...")
        
        # 模拟修复 LLM
        mock_llm_fix = AsyncMock()
        mock_fix_response = Mock()
        mock_fix_response.content = '''
{
    "type": "door",
    "id": "door_1",
    "width": 1.0,
    "height": 2.2
}
'''
        mock_llm_fix.ainvoke.return_value = mock_fix_response
        
        schema_validator = JsonSchemaValidator()
        validator = StructureValidator(schema_validator, mock_llm_fix)
        
        schema = {
            "type": "object",
            "required": ["type", "id", "width", "height"],
            "properties": {
                "type": {"type": "string"},
                "id": {"type": "string"},
                "width": {"type": "number"},
                "height": {"type": "number"}
            }
        }
        
        validated_output, errors = await validator.validate_and_fix(
            llm_output,
            node_name="door_gen",
            schema=schema,
            max_retries=1
        )
        
        if errors:
            print(f"  发现错误: {errors}")
            print(f"  ✓ 已自动修复")
        else:
            print(f"  ✓ 验证通过")
        
        print(f"  最终输出: {validated_output}")
        
        return validated_output
    
    # 执行模拟节点
    result = await mock_generation_node("生成一个现代风格的入口门")
    
    print("\n[完成] 最终生成结果:")
    print(f"  {result}")
    
    print("\n" + "=" * 60)


def example_domain_config():
    """示例 4: 领域配置的使用"""
    print("\n示例 4: 领域配置 (Domain Config)")
    print("=" * 60)
    
    from app.config import get_domain_config
    
    # 获取配置
    config = get_domain_config()
    
    print(f"\n当前领域: {config.get_domain()}")
    
    # 获取实体类型
    print(f"\n实体类型 (前 5 个):")
    for entity in config.get_entity_types()[:5]:
        entity_type = entity.get('type')
        aliases = ", ".join(entity.get('aliases', [])[:3])
        print(f"  - {entity_type}: {aliases}")
    
    # 查找实体类型（支持别名）
    print(f"\n实体类型查找:")
    tests = ["building", "墙体", "window", "门"]
    for test in tests:
        result = config.find_entity_type(test)
        print(f"  '{test}' → {result}")
    
    # 获取约束
    print(f"\n约束配置 (door):")
    door_constraints = config.get_entity_constraint("door")
    for attr, constraint in door_constraints.items():
        print(f"  - {attr}: {constraint}")
    
    print("\n" + "=" * 60)


async def main():
    """运行所有示例"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "P0 方案使用示例" + " " * 28 + "║")
    print("╚" + "=" * 58 + "╝")
    
    # 示例 1: 结构自检
    await example_structure_validator()
    
    # 示例 2: 查询改写
    await example_query_rewriter()
    
    # 示例 3: 完整集成
    await example_integration_in_node()
    
    # 示例 4: 领域配置
    example_domain_config()
    
    print("\n" + "=" * 60)
    print("所有示例运行完成！")
    print("=" * 60)
    print("\n提示:")
    print("  - 在实际使用时，将 AsyncMock 替换为真实的 LLM 实例")
    print("  - 根据需要调整 Schema 和领域配置")
    print("  - 查看 test_p0_implementation.py 了解更多测试用例")
    print()


if __name__ == "__main__":
    asyncio.run(main())
