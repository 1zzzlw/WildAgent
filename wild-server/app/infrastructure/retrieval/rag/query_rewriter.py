"""
查询改写模块 (Query Rewriter)

P0 方案：将用户自然语言改写为结构化查询，提升 RAG 检索准确率（领域无关）

用法:
    rewriter = QueryRewriter(llm, domain_schema)
    structured_query = await rewriter.rewrite(user_query)
"""
import json
from typing import Any
from loguru import logger


class QueryRewriter:
    """
    查询改写：将自然语言改写为结构化查询（领域无关）
    
    核心功能：
    1. 识别实体类型 (entity_type)
    2. 提取属性约束 (attributes)
    3. 识别特性需求 (features)
    4. 生成检索关键词 (keywords)
    """
    
    def __init__(self, llm: Any, domain_schema: dict):
        """
        Args:
            llm: LLM 实例
            domain_schema: 领域 Schema（从配置文件加载）
                {
                    "domain": "architecture",
                    "entity_types": [...],
                    "attributes": [...],
                    "features": [...]
                }
        """
        self.llm = llm
        self.domain_schema = domain_schema
    
    async def rewrite(self, user_query: str) -> dict:
        """
        改写用户查询为结构化查询
        
        Args:
            user_query: 用户自然语言查询
            
        Returns:
            结构化查询:
            {
                "entity_type": "实体类型",
                "attributes": {"key": "value"},
                "features": ["特性列表"],
                "constraints": {"key": "constraint"},
                "keywords": ["检索关键词"]
            }
        """
        try:
            rewrite_prompt = self._build_rewrite_prompt(user_query)
            
            response = await self.llm.ainvoke([
                {"role": "system", "content": "你是一个查询结构化专家。"},
                {"role": "user", "content": rewrite_prompt}
            ])
            
            # 解析 JSON 结果
            structured = self._parse_json(response.content)
            
            if structured:
                logger.info(
                    f"[查询改写] {user_query[:50]}... → "
                    f"entity_type={structured.get('entity_type')}, "
                    f"keywords={structured.get('keywords', [])[:3]}"
                )
            
            return structured or self._fallback_query(user_query)
            
        except Exception as e:
            logger.warning(f"[查询改写] 失败，使用回退策略: {e}")
            return self._fallback_query(user_query)
    
    def _build_rewrite_prompt(self, user_query: str) -> str:
        """构建改写提示词"""
        
        # 提取领域信息
        domain_name = self.domain_schema.get("domain", "未知领域")
        entity_types = self.domain_schema.get("entity_types", [])
        attributes = self.domain_schema.get("attributes", [])
        features = self.domain_schema.get("features", [])
        
        # 简化 schema 显示（避免过长）
        entity_type_list = [
            f"{et.get('type')} ({', '.join(et.get('aliases', [])[:3])})"
            for et in entity_types[:5]
        ]
        
        attribute_list = [
            f"{attr.get('name')}: {attr.get('values', attr.get('type', 'any'))}"
            for attr in attributes[:5]
        ]
        
        feature_list = [f.get('name') for f in features[:5]]
        
        return f"""
将用户需求改写为结构化查询，便于检索知识库。

领域: {domain_name}

用户需求：
{user_query}

领域 Schema（参考）：

实体类型:
{chr(10).join(f"- {et}" for et in entity_type_list)}

可用属性:
{chr(10).join(f"- {attr}" for attr in attribute_list)}

可用特性:
{chr(10).join(f"- {feat}" for feat in feature_list)}

输出 JSON 格式：
{{
    "entity_type": "实体类型（从 schema 中的 types，如果不确定则为 null）",
    "attributes": {{"属性名": "属性值"}},
    "features": ["特性列表"],
    "constraints": {{"约束名": "约束值"}},
    "keywords": ["关键检索词列表（5-10个）"]
}}

注意：
1. entity_type 必须从上面的实体类型中选择，不确定时为 null
2. keywords 应包含用户提到的关键术语、同义词和相关概念
3. 优先使用 schema 中的标准术语，但保留用户的原始关键词

只输出 JSON，不要其他文字。
"""
    
    def _parse_json(self, text: str) -> dict | None:
        """从 LLM 响应中提取 JSON"""
        import re
        
        # 尝试直接解析
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        
        # 尝试从 code fence 提取
        code_fence_match = re.search(r'```(?:json)?\s*(\{.+?\})\s*```', text, re.DOTALL)
        if code_fence_match:
            try:
                return json.loads(code_fence_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # 尝试查找第一个 JSON 对象
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        return None
    
    def _fallback_query(self, user_query: str) -> dict:
        """回退策略：基于简单规则生成查询"""
        
        # 简单关键词提取
        import re
        words = re.findall(r'\b\w+\b', user_query.lower())
        keywords = [w for w in words if len(w) > 2][:10]
        
        return {
            "entity_type": None,
            "attributes": {},
            "features": [],
            "constraints": {},
            "keywords": keywords or [user_query[:50]]
        }


class EnhancedRAGRetriever:
    """
    增强 RAG 检索器：集成查询改写和多维度检索
    
    使用查询改写提升检索准确率
    """
    
    def __init__(
        self,
        base_retriever: Any,
        query_rewriter: QueryRewriter | None = None
    ):
        """
        Args:
            base_retriever: 基础检索器（如 spec_loader）
            query_rewriter: 查询改写器（可选）
        """
        self.base_retriever = base_retriever
        self.query_rewriter = query_rewriter
    
    async def retrieve(
        self,
        user_query: str,
        metadata_filter: dict | None = None,
        use_rewriting: bool = True
    ) -> list:
        """
        增强检索：使用查询改写优化检索
        
        Args:
            user_query: 用户查询
            metadata_filter: 元数据过滤器
            use_rewriting: 是否使用查询改写
            
        Returns:
            检索结果列表
        """
        # 1. 查询改写（可选）
        if use_rewriting and self.query_rewriter:
            try:
                structured_query = await self.query_rewriter.rewrite(user_query)
                
                # 使用改写后的关键词构建查询
                keywords = structured_query.get("keywords", [])
                search_query = " ".join(keywords) if keywords else user_query
                
                # 合并元数据过滤器
                entity_type = structured_query.get("entity_type")
                if entity_type and not metadata_filter:
                    metadata_filter = {"entity_type": entity_type}
                elif entity_type and metadata_filter:
                    metadata_filter = {**metadata_filter, "entity_type": entity_type}
                
            except Exception as e:
                logger.warning(f"[增强检索] 查询改写失败，使用原始查询: {e}")
                search_query = user_query
        else:
            search_query = user_query
        
        # 2. 执行检索
        if hasattr(self.base_retriever, 'retrieve'):
            return self.base_retriever.retrieve(search_query, metadata_filter)
        else:
            # 兼容 spec_loader.load_many
            return self.base_retriever.load_many([search_query], per_query=2)
