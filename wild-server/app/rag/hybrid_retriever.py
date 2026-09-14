"""
混合检索模块 (Hybrid Retriever)

P1 方案：BM25 + 向量检索融合（领域无关）

用法:
    retriever = HybridRetriever(vector_store, documents, weights=[0.4, 0.6])
    results = await retriever.retrieve(query, entity_type)
"""
from typing import Any
from loguru import logger


class HybridRetriever:
    """
    混合检索器：结合 BM25 关键词和向量语义（领域无关）
    
    特性：
    - BM25 精确关键词匹配
    - 向量语义相似度
    - 可调权重融合
    - 实体类型重排序
    """
    
    def __init__(
        self, 
        vector_store: Any,
        documents: list[Any] = None,
        weights: list[float] = None,
        bm25_k: int = 3,
        vector_k: int = 3
    ):
        """
        Args:
            vector_store: 向量存储（支持 as_retriever）
            documents: 文档列表（用于 BM25）
            weights: 权重 [BM25权重, 向量权重]，默认 [0.4, 0.6]
            bm25_k: BM25 返回数量
            vector_k: 向量检索返回数量
        """
        self.vector_store = vector_store
        self.weights = weights or [0.4, 0.6]
        self.bm25_k = bm25_k
        self.vector_k = vector_k
        
        # 初始化 BM25（如果有文档）
        self.bm25 = None
        if documents:
            try:
                from langchain_community.retrievers import BM25Retriever
                self.bm25 = BM25Retriever.from_documents(documents)
                self.bm25.k = bm25_k
                logger.info(f"[混合检索] BM25 初始化成功: {len(documents)} 个文档")
            except ImportError:
                logger.warning(
                    "[混合检索] BM25Retriever 未安装，仅使用向量检索"
                )
            except Exception as e:
                logger.warning(f"[混合检索] BM25 初始化失败: {e}")
        
        # 向量检索器
        self.vector_retriever = vector_store.as_retriever(
            search_kwargs={"k": vector_k}
        )
    
    async def retrieve(
        self, 
        query: str, 
        entity_type: str = None,
        metadata_filter: dict = None
    ) -> list[Any]:
        """
        混合检索
        
        Args:
            query: 查询字符串
            entity_type: 实体类型（用于重排序）
            metadata_filter: 元数据过滤
            
        Returns:
            检索结果列表
        """
        results = []
        
        # 1. BM25 检索（关键词精确匹配）
        if self.bm25:
            try:
                bm25_results = await self._retrieve_bm25(query)
                results.extend([(doc, "bm25") for doc in bm25_results])
                logger.debug(f"[混合检索] BM25 返回 {len(bm25_results)} 个结果")
            except Exception as e:
                logger.warning(f"[混合检索] BM25 检索失败: {e}")
        
        # 2. 向量检索（语义相似）
        try:
            vector_results = await self._retrieve_vector(query, metadata_filter)
            results.extend([(doc, "vector") for doc in vector_results])
            logger.debug(f"[混合检索] 向量检索返回 {len(vector_results)} 个结果")
        except Exception as e:
            logger.warning(f"[混合检索] 向量检索失败: {e}")
        
        # 3. 融合和去重
        fused_results = self._fuse_results(results)
        
        # 4. 重排序（根据实体类型相关性）
        if entity_type:
            fused_results = self._rerank_by_relevance(fused_results, entity_type)
        
        return fused_results
    
    async def _retrieve_bm25(self, query: str) -> list[Any]:
        """BM25 检索"""
        if not self.bm25:
            return []
        
        # BM25Retriever 可能不支持 async
        try:
            # 尝试 async
            results = await self.bm25.ainvoke(query)
        except AttributeError:
            # 回退到 sync
            results = self.bm25.invoke(query)
        
        return results
    
    async def _retrieve_vector(
        self, 
        query: str,
        metadata_filter: dict = None
    ) -> list[Any]:
        """向量检索"""
        search_kwargs = {"k": self.vector_k}
        
        if metadata_filter:
            search_kwargs["filter"] = metadata_filter
        
        try:
            results = await self.vector_retriever.ainvoke(query)
        except AttributeError:
            results = self.vector_retriever.invoke(query)
        
        return results
    
    def _fuse_results(self, results: list[tuple[Any, str]]) -> list[Any]:
        """
        融合 BM25 和向量检索结果
        
        使用倒数排名融合 (Reciprocal Rank Fusion)
        """
        # 分离不同来源的结果
        bm25_docs = [doc for doc, source in results if source == "bm25"]
        vector_docs = [doc for doc, source in results if source == "vector"]
        
        # 计算每个文档的融合分数
        doc_scores = {}
        
        # BM25 分数（基于排名）
        for i, doc in enumerate(bm25_docs):
            doc_id = self._get_doc_id(doc)
            score = self.weights[0] / (i + 1)  # 倒数排名
            doc_scores[doc_id] = doc_scores.get(doc_id, 0) + score
        
        # 向量检索分数（基于排名）
        for i, doc in enumerate(vector_docs):
            doc_id = self._get_doc_id(doc)
            score = self.weights[1] / (i + 1)  # 倒数排名
            doc_scores[doc_id] = doc_scores.get(doc_id, 0) + score
        
        # 合并并按分数排序
        all_docs = {}
        for doc, _ in results:
            doc_id = self._get_doc_id(doc)
            if doc_id not in all_docs:
                all_docs[doc_id] = doc
        
        sorted_docs = sorted(
            all_docs.values(),
            key=lambda d: doc_scores.get(self._get_doc_id(d), 0),
            reverse=True
        )
        
        return sorted_docs[:max(self.bm25_k, self.vector_k)]
    
    def _get_doc_id(self, doc: Any) -> str:
        """获取文档唯一标识"""
        # 尝试多种方式获取文档 ID
        if hasattr(doc, 'metadata'):
            metadata = doc.metadata
            if isinstance(metadata, dict):
                return metadata.get('id') or metadata.get('source') or str(hash(doc.page_content))
        
        if hasattr(doc, 'id'):
            return doc.id
        
        # 使用内容哈希作为 ID
        content = getattr(doc, 'page_content', str(doc))
        return str(hash(content))
    
    def _rerank_by_relevance(self, results: list[Any], entity_type: str) -> list[Any]:
        """
        根据实体类型相关性重排序（领域无关）
        
        Args:
            results: 检索结果
            entity_type: 目标实体类型
            
        Returns:
            重排序后的结果
        """
        def relevance_score(doc):
            if not hasattr(doc, 'metadata'):
                return 0.5
            
            metadata = doc.metadata
            if not isinstance(metadata, dict):
                return 0.5
            
            # 精确匹配得分最高
            if metadata.get("entity_type") == entity_type:
                return 1.0
            
            # 相关实体得分次之
            related = metadata.get("related_entities", [])
            if isinstance(related, list) and entity_type in related:
                return 0.7
            
            # 默认得分
            return 0.5
        
        return sorted(results, key=relevance_score, reverse=True)
    
    def get_stats(self) -> dict:
        """获取检索器统计信息"""
        return {
            "has_bm25": self.bm25 is not None,
            "has_vector": self.vector_retriever is not None,
            "weights": self.weights,
            "bm25_k": self.bm25_k,
            "vector_k": self.vector_k,
        }


# 简化的接口函数
async def hybrid_retrieve(
    query: str,
    vector_store: Any,
    documents: list[Any] = None,
    entity_type: str = None,
    weights: list[float] = None
) -> list[Any]:
    """
    简化的混合检索接口
    
    Args:
        query: 查询字符串
        vector_store: 向量存储
        documents: 文档列表（用于 BM25）
        entity_type: 实体类型
        weights: 权重 [BM25, 向量]
        
    Returns:
        检索结果
    """
    retriever = HybridRetriever(vector_store, documents, weights)
    return await retriever.retrieve(query, entity_type)
