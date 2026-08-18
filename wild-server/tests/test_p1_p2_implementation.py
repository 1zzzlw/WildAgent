"""
P1 和 P2 方案测试

测试事实自检、工具自检、推理自检和混合检索功能
"""
import pytest
from unittest.mock import AsyncMock, Mock


pytest_plugins = ('pytest_asyncio',)


class TestFactualValidator:
    """测试事实自检功能"""
    
    def test_import_factual_validator(self):
        """测试模块导入"""
        from app.agent.validators import FactualValidator
        assert FactualValidator is not None
    
    @pytest.mark.asyncio
    async def test_validate_entity_pass(self):
        """测试实体验证通过"""
        from app.agent.validators import FactualValidator
        
        constraints = {
            "door": {
                "width": {"min": 0.7, "max": 3.0, "unit": "m"},
                "height": {"min": 1.8, "max": 3.5, "unit": "m"}
            }
        }
        
        validator = FactualValidator(constraints)
        
        # 合法的门
        valid_door = {
            "type": "door",
            "width": 1.0,
            "height": 2.2
        }
        
        is_valid, errors = await validator.validate_entity(valid_door)
        
        assert is_valid
        assert len(errors) == 0
    
    @pytest.mark.asyncio
    async def test_validate_entity_range_violation(self):
        """测试范围违规"""
        from app.agent.validators import FactualValidator
        
        constraints = {
            "door": {
                "width": {"min": 0.7, "max": 3.0, "unit": "m"},
                "height": {"min": 1.8, "max": 3.5, "unit": "m"}
            }
        }
        
        validator = FactualValidator(constraints)
        
        # 宽度超出范围的门
        invalid_door = {
            "type": "door",
            "width": 5.0,  # 超过最大值 3.0
            "height": 2.2
        }
        
        is_valid, errors = await validator.validate_entity(invalid_door)
        
        assert not is_valid
        assert len(errors) > 0
        assert any("width" in err for err in errors)
    
    @pytest.mark.asyncio
    async def test_auto_correct_clamp(self):
        """测试自动修正（钳位策略）"""
        from app.agent.validators import FactualValidator
        
        constraints = {
            "door": {
                "width": {"min": 0.7, "max": 3.0},
                "height": {"min": 1.8, "max": 3.5}
            }
        }
        
        validator = FactualValidator(constraints)
        
        # 超出范围的门
        door = {
            "type": "door",
            "width": 5.0,
            "height": 0.5
        }
        
        corrected = await validator.auto_correct(
            door,
            ["width超出", "height超出"],
            correction_strategy="clamp"
        )
        
        # 应该被钳位到边界
        assert corrected["width"] == 3.0
        assert corrected["height"] == 1.8


class TestToolValidator:
    """测试工具自检功能"""
    
    def test_import_tool_validator(self):
        """测试模块导入"""
        from app.agent.validators import ToolValidator
        assert ToolValidator is not None
    
    @pytest.mark.asyncio
    async def test_diagnose_tool_error(self):
        """测试工具错误诊断"""
        from app.agent.validators import ToolValidator
        
        # Mock LLM
        mock_llm = AsyncMock()
        mock_response = Mock()
        mock_response.content = '''
{
    "root_cause": "实体尺寸超出父容器",
    "fix_actions": ["减小宽度到3.0以内", "调整位置"],
    "prevention": "生成前检查父容器尺寸"
}
'''
        mock_llm.ainvoke.return_value = mock_response
        
        domain_context = {
            "domain_name": "测试领域",
            "output_schema": {},
            "tool_descriptions": {
                "validate_size": "验证尺寸是否合理"
            }
        }
        
        validator = ToolValidator(mock_llm, domain_context)
        
        diagnosis = await validator.diagnose_tool_error(
            tool_name="validate_size",
            error_output="错误：宽度5.0超出父容器最大值3.0",
            generated_output={"width": 5.0}
        )
        
        assert diagnosis is not None
        assert "root_cause" in diagnosis
        assert "fix_actions" in diagnosis
        assert len(diagnosis["fix_actions"]) > 0


class TestReasoningValidator:
    """测试推理自检功能"""
    
    def test_import_reasoning_validator(self):
        """测试模块导入"""
        from app.agent.validators import ReasoningValidator
        assert ReasoningValidator is not None
    
    @pytest.mark.asyncio
    async def test_validate_reasoning_consistent(self):
        """测试推理一致性验证（一致的情况）"""
        from app.agent.validators import ReasoningValidator
        
        # Mock LLM
        mock_llm = AsyncMock()
        mock_response = Mock()
        mock_response.content = '''
{
    "has_contradiction": false,
    "contradictions": []
}
'''
        mock_llm.ainvoke.return_value = mock_response
        
        domain_context = {
            "domain_name": "测试领域",
            "contradiction_types": []
        }
        
        validator = ReasoningValidator(mock_llm, domain_context)
        
        is_consistent, contradictions = await validator.validate_reasoning(
            reasoning_text="用户要求现代风格，所以生成现代风格的门",
            user_query="生成一个现代风格的门",
            output={"style": "modern", "type": "door"}
        )
        
        assert is_consistent
        assert len(contradictions) == 0
    
    @pytest.mark.asyncio
    async def test_validate_reasoning_inconsistent(self):
        """测试推理一致性验证（不一致的情况）"""
        from app.agent.validators import ReasoningValidator
        
        # Mock LLM
        mock_llm = AsyncMock()
        mock_response = Mock()
        mock_response.content = '''
{
    "has_contradiction": true,
    "contradictions": [
        {
            "type": "attribute_mismatch",
            "description": "用户要求现代风格，但生成了古典风格",
            "severity": "high"
        }
    ]
}
'''
        mock_llm.ainvoke.return_value = mock_response
        
        domain_context = {
            "domain_name": "测试领域",
            "contradiction_types": ["attribute_mismatch"]
        }
        
        validator = ReasoningValidator(mock_llm, domain_context)
        
        is_consistent, contradictions = await validator.validate_reasoning(
            reasoning_text="用户要求现代风格，所以生成古典风格的门",
            user_query="生成一个现代风格的门",
            output={"style": "classical", "type": "door"}
        )
        
        assert not is_consistent
        assert len(contradictions) > 0
        assert contradictions[0]["type"] == "attribute_mismatch"


class TestHybridRetriever:
    """测试混合检索功能"""
    
    def test_import_hybrid_retriever(self):
        """测试模块导入"""
        from app.agent.rag import HybridRetriever
        assert HybridRetriever is not None
    
    def test_hybrid_retriever_initialization(self):
        """测试混合检索器初始化"""
        from app.agent.rag import HybridRetriever
        
        # Mock vector store
        mock_vector_store = Mock()
        mock_retriever = Mock()
        mock_vector_store.as_retriever.return_value = mock_retriever
        
        # 不提供文档（仅向量检索）
        retriever = HybridRetriever(
            vector_store=mock_vector_store,
            documents=None,
            weights=[0.4, 0.6]
        )
        
        assert retriever.bm25 is None  # 没有文档，BM25 应该是 None
        assert retriever.vector_retriever is not None
        assert retriever.weights == [0.4, 0.6]
    
    def test_get_stats(self):
        """测试获取统计信息"""
        from app.agent.rag import HybridRetriever
        
        mock_vector_store = Mock()
        mock_retriever = Mock()
        mock_vector_store.as_retriever.return_value = mock_retriever
        
        retriever = HybridRetriever(
            vector_store=mock_vector_store,
            weights=[0.3, 0.7],
            bm25_k=5,
            vector_k=5
        )
        
        stats = retriever.get_stats()
        
        assert stats["weights"] == [0.3, 0.7]
        assert stats["bm25_k"] == 5
        assert stats["vector_k"] == 5
        assert "has_bm25" in stats
        assert "has_vector" in stats


if __name__ == "__main__":
    # 运行简单测试
    print("开始测试 P1 & P2 实施...")
    
    # 测试导入
    try:
        from app.agent.validators import (
            FactualValidator,
            ToolValidator,
            ReasoningValidator
        )
        from app.agent.rag import HybridRetriever
        print("✓ 所有模块导入成功")
    except Exception as e:
        print(f"✗ 模块导入失败: {e}")
        exit(1)
    
    # 测试事实验证
    try:
        import asyncio
        
        constraints = {
            "door": {
                "width": {"min": 0.7, "max": 3.0},
                "height": {"min": 1.8, "max": 3.5}
            }
        }
        
        validator = FactualValidator(constraints)
        
        # 测试合法实体
        valid_door = {"type": "door", "width": 1.0, "height": 2.2}
        is_valid, _ = asyncio.run(validator.validate_entity(valid_door))
        
        assert is_valid
        print("✓ 事实验证测试通过")
        
    except Exception as e:
        print(f"✗ 事实验证测试失败: {e}")
    
    print("\n使用 pytest 运行完整测试:")
    print("  cd wild-server && pytest tests/test_p1_p2_implementation.py -v")
