"""
P0 方案实施测试

测试结构自检和查询改写功能
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock

# 使用 anyio 而不是 pytest-asyncio（项目已安装）
pytest_plugins = ('pytest_asyncio',)


class TestStructureValidator:
    """测试结构自检功能"""
    
    def test_import_structure_validator(self):
        """测试模块导入"""
        from app.agent.validators import StructureValidator, JsonSchemaValidator
        assert StructureValidator is not None
        assert JsonSchemaValidator is not None
    
    @pytest.mark.asyncio
    async def test_structure_validation_pass(self):
        """测试 Schema 验证通过"""
        from app.agent.validators import StructureValidator, JsonSchemaValidator
        
        # Mock LLM
        mock_llm = AsyncMock()
        
        # 创建验证器
        schema_validator = JsonSchemaValidator()
        validator = StructureValidator(schema_validator, mock_llm)
        
        # 测试数据
        valid_output = {
            "type": "building",
            "name": "test"
        }
        
        schema = {
            "type": "object",
            "required": ["type", "name"],
            "properties": {
                "type": {"type": "string"},
                "name": {"type": "string"}
            }
        }
        
        # 执行验证
        result, errors = await validator.validate_and_fix(
            valid_output,
            "test_node",
            schema
        )
        
        # 验证结果
        assert result == valid_output
        assert len(errors) == 0
    
    @pytest.mark.asyncio
    async def test_structure_validation_missing_field(self):
        """测试缺少必填字段"""
        from app.agent.validators import StructureValidator, JsonSchemaValidator
        
        mock_llm = AsyncMock()
        schema_validator = JsonSchemaValidator()
        validator = StructureValidator(schema_validator, mock_llm)
        
        # 缺少 name 字段
        invalid_output = {
            "type": "building"
        }
        
        schema = {
            "type": "object",
            "required": ["type", "name"],
            "properties": {
                "type": {"type": "string"},
                "name": {"type": "string"}
            }
        }
        
        result, errors = await validator.validate_and_fix(
            invalid_output,
            "test_node",
            schema,
            max_retries=0  # 不进行 LLM 修复
        )
        
        # 应该有错误
        assert len(errors) > 0
        assert any("name" in str(err) for err in errors)


class TestQueryRewriter:
    """测试查询改写功能"""
    
    def test_import_query_rewriter(self):
        """测试模块导入"""
        from app.agent.rag import QueryRewriter, EnhancedRAGRetriever
        assert QueryRewriter is not None
        assert EnhancedRAGRetriever is not None
    
    @pytest.mark.asyncio
    async def test_query_rewrite_basic(self):
        """测试基本查询改写"""
        from app.agent.rag import QueryRewriter
        
        # Mock LLM
        mock_llm = AsyncMock()
        mock_response = Mock()
        mock_response.content = '''
{
    "entity_type": "building",
    "attributes": {"style": "modern"},
    "features": ["energy_efficient"],
    "constraints": {},
    "keywords": ["modern", "building", "design", "energy", "efficient"]
}
'''
        mock_llm.ainvoke.return_value = mock_response
        
        # 领域 schema
        domain_schema = {
            "domain": "architecture",
            "entity_types": [
                {"type": "building", "aliases": ["房屋", "建筑"]}
            ],
            "attributes": [
                {"name": "style", "values": ["modern", "classical"]}
            ],
            "features": [
                {"name": "energy_efficient", "aliases": ["节能"]}
            ]
        }
        
        # 创建改写器
        rewriter = QueryRewriter(mock_llm, domain_schema)
        
        # 执行改写
        result = await rewriter.rewrite("我想要一个现代风格的节能建筑")
        
        # 验证结果
        assert result is not None
        assert "entity_type" in result
        assert "keywords" in result
        assert len(result["keywords"]) > 0
    
    @pytest.mark.asyncio
    async def test_query_rewrite_fallback(self):
        """测试改写失败时的回退策略"""
        from app.agent.rag import QueryRewriter
        
        # Mock LLM that fails
        mock_llm = AsyncMock()
        mock_llm.ainvoke.side_effect = Exception("LLM failure")
        
        domain_schema = {
            "domain": "architecture",
            "entity_types": [],
            "attributes": [],
            "features": []
        }
        
        rewriter = QueryRewriter(mock_llm, domain_schema)
        
        # 应该使用回退策略
        result = await rewriter.rewrite("test query")
        
        assert result is not None
        assert "keywords" in result
        assert result["entity_type"] is None


class TestDomainConfig:
    """测试领域配置加载"""
    
    def test_import_domain_config(self):
        """测试模块导入"""
        from app.config import DomainConfig, get_domain_config
        assert DomainConfig is not None
        assert get_domain_config is not None
    
    def test_load_domain_config(self):
        """测试加载领域配置"""
        from app.config import DomainConfig
        from pathlib import Path
        
        # 使用项目配置文件
        config_path = Path(__file__).parent.parent / "config" / "domain_schema.yaml"
        
        config = DomainConfig(config_path)
        
        # 验证加载
        assert config.get_domain() is not None
        assert isinstance(config.get_entity_types(), list)
        assert isinstance(config.get_constraints(), dict)
    
    def test_find_entity_type(self):
        """测试实体类型查找"""
        from app.config import DomainConfig
        from pathlib import Path
        
        config_path = Path(__file__).parent.parent / "config" / "domain_schema.yaml"
        config = DomainConfig(config_path)
        
        # 测试标准名称
        result = config.find_entity_type("building")
        assert result == "building"
        
        # 测试别名（如果配置文件中有）
        result = config.find_entity_type("墙体")
        if result:  # 仅在配置文件存在时测试
            assert result == "wall"


if __name__ == "__main__":
    # 运行简单测试
    print("开始测试 P0 实施...")
    
    # 测试导入
    try:
        from app.agent.validators import StructureValidator
        from app.agent.rag import QueryRewriter
        from app.config import get_domain_config
        print("✓ 模块导入成功")
    except Exception as e:
        print(f"✗ 模块导入失败: {e}")
        exit(1)
    
    # 测试配置加载
    try:
        config = get_domain_config()
        print(f"✓ 领域配置加载成功: {config.get_domain()}")
        print(f"  - {len(config.get_entity_types())} 个实体类型")
        print(f"  - {len(config.get_attributes())} 个属性")
        print(f"  - {len(config.get_features())} 个特性")
    except Exception as e:
        print(f"✗ 配置加载失败: {e}")
    
    print("\n使用 pytest 运行完整测试:")
    print("  cd wild-server && pytest tests/test_p0_implementation.py -v")
