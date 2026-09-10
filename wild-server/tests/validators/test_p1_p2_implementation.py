"""
P2 方案测试

测试工具自检、推理自检和混合检索功能
"""
import pytest
from unittest.mock import AsyncMock, Mock


pytest_plugins = ('pytest_asyncio',)
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
