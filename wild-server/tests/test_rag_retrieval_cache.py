"""RAG 检索缓存的缓存键单元测试。"""

import unittest

from app.spec.loader import RAGSpecLoader


class _DummyEmbedding:
    """占位 embedding，仅用于测试缓存键，不触发真实向量计算。"""


class RAGRetrievalCacheTest(unittest.TestCase):
    def _loader(self) -> RAGSpecLoader:
        return RAGSpecLoader(
            base_paths=[],
            rag_paths=[],
            persist_dir=":memory:",
            collection_name="test_cache",
            embedding_function=_DummyEmbedding(),
            auto_sync=False,
        )

    def test_cache_key_is_stable_for_identical_input(self):
        loader = self._loader()
        queries = [("门", {"entity_type": "door"}), ("窗", None)]
        self.assertEqual(
            loader._retrieval_cache_key(queries, 2),
            loader._retrieval_cache_key(queries, 2),
        )

    def test_cache_key_changes_with_filter(self):
        loader = self._loader()
        door = loader._retrieval_cache_key([("门", {"entity_type": "door"})], 2)
        window = loader._retrieval_cache_key([("门", {"entity_type": "window"})], 2)
        self.assertNotEqual(door, window)

    def test_cache_key_changes_with_per_query(self):
        loader = self._loader()
        queries = [("门", None)]
        self.assertNotEqual(
            loader._retrieval_cache_key(queries, 1),
            loader._retrieval_cache_key(queries, 2),
        )

    def test_cache_key_changes_with_knowledge_base_revision(self):
        loader = self._loader()
        queries = [("门", None)]
        before = loader._retrieval_cache_key(queries, 2)
        loader._last_sync_stats = {"total": 10, "updated": 1, "deleted": 0}
        after = loader._retrieval_cache_key(queries, 2)
        self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
