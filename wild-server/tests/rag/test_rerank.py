"""rerank 纯规则重排测试。"""

import unittest

from app.spec.loader import RetrievedSpecChunk


def _chunk(
    document: str,
    *,
    authority: str = "domain",
    distance: float = 0.5,
    source: str = "doc.md",
) -> RetrievedSpecChunk:
    return RetrievedSpecChunk(
        document=document,
        metadata={"authority": authority, "source": source},
        distance=distance,
        id=source,
    )


class RerankTest(unittest.TestCase):
    def test_authority_ranks_before_lower_authority(self):
        from app.spec.loader import RAGSpecLoader

        loader = object.__new__(RAGSpecLoader)
        chunks = [
            _chunk("experimental content", authority="inferred"),
            _chunk("schema definition", authority="schema"),
        ]
        reranked = loader._rerank_retrieved(chunks, "schema")
        self.assertEqual(reranked[0].metadata["authority"], "schema")
        self.assertEqual(reranked[1].metadata["authority"], "inferred")

    def test_higher_overlap_ranks_first_within_same_authority(self):
        from app.spec.loader import RAGSpecLoader

        loader = object.__new__(RAGSpecLoader)
        chunks = [
            # 与查询"雨棚橱窗"重叠度更高（雨棚、棚橱、橱窗三处双字）。
            _chunk("雨棚橱窗布置说明", authority="verified"),
            _chunk("一般商业空间概述", authority="verified"),
        ]
        reranked = loader._rerank_retrieved(chunks, "雨棚橱窗")
        self.assertIn("雨棚", reranked[0].document)
        self.assertIn("商业空间", reranked[1].document)

    def test_single_chunk_is_returned_unchanged(self):
        from app.spec.loader import RAGSpecLoader

        loader = object.__new__(RAGSpecLoader)
        chunk = _chunk("only result")
        reranked = loader._rerank_retrieved([chunk], "query")
        self.assertEqual(reranked, [chunk])


if __name__ == "__main__":
    unittest.main()
