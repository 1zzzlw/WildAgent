"""检查适配层的评分与数据传递，不调用模型、Chroma 或 LangSmith。"""
import unittest
from types import SimpleNamespace

from langsmith_tools.evaluate_rag import make_target, retrieval_scores


class EvaluationAdapterTests(unittest.TestCase):
    def test_missing_reference_is_not_reported_as_zero(self):
        for reference in (None, {}, {"expectedSources": []},
                          {"expectedSources": "a.md"}, {"expectedSources": [""]}):
            with self.subTest(reference=reference):
                with self.assertRaises(ValueError):
                    retrieval_scores({"hits": []}, reference)

    def test_scores_use_reference_source_paths(self):
        result = retrieval_scores({"hits": [
            {"source": "wrong.md"},
            {"path": "components/doors.md"},
        ]}, {"expectedSources": ["components/doors.md", "components/windows.md"]})
        scores = {item["key"]: item["score"] for item in result["results"]}
        self.assertEqual(scores, {
            "hit_at_k": 1, "recall_at_k": 0.5, "reciprocal_rank": 0.5,
        })

    def test_target_passes_filter_and_groups_neighbor_parts(self):
        calls = []

        def retrieve(query, metadata_filter=None):
            calls.append((query, metadata_filter))
            return [SimpleNamespace(
                id=str(i), document="test", distance=0.1,
                metadata={"source": source, "parent_chunk_id": parent},
            ) for i, (source, parent) in enumerate([
                ("a.md", "a"), ("a.md", "a"), ("b.md", "b"), ("c.md", "c"),
            ])]

        target = make_target(SimpleNamespace(retrieve=retrieve), top_k=2)
        result = target({"query": "门窗", "metadataFilter": {"doc_type": "component"}})
        self.assertEqual(calls, [("门窗", {"doc_type": "component"})])
        self.assertEqual([hit["source"] for hit in result["hits"]], ["a.md", "b.md"])


if __name__ == "__main__":
    unittest.main()
