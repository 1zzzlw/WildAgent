"""测试检索评测指标本身是否算对。

这个文件不测试 embedding 好不好，而是测试“评分尺子”有没有算错。
如果评分公式本身有 bug，那么后面得到的 Recall@K 再高也没有意义。
"""
import unittest

from scripts.rag.eval_retrieval import score_ranked_hits, select_ranked_parent_groups


class RetrievalMetricTest(unittest.TestCase):
    def test_hit_recall_and_mrr_for_two_expected_sources(self):
        """两个标准来源只召回一个：Hit=成功，Recall=1/2，首位命中所以 MRR=1。"""
        hits = [
            {"source": "windows-supported.md", "path": "components/windows-supported.md"},
            {"source": "walls.md", "path": "components/walls.md"},
        ]

        score = score_ranked_hits(
            hits,
            ["components/windows-supported.md", "components/doors-supported.md"],
        )

        self.assertIsNotNone(score)
        self.assertTrue(score["hit"])
        self.assertEqual(score["recall"], 0.5)
        self.assertEqual(score["reciprocal_rank"], 1.0)
        self.assertEqual(score["missing_sources"], ["components/doors-supported.md"])

    def test_mrr_uses_first_relevant_rank(self):
        """正确来源排第 2 时，倒数排名是 1/2。"""
        hits = [
            {"source": "walls.md", "path": "components/walls.md"},
            {"source": "doors-supported.md", "path": "components/doors-supported.md"},
        ]

        score = score_ranked_hits(hits, ["components/doors-supported.md"])

        self.assertEqual(score["first_relevant_rank"], 2)
        self.assertEqual(score["reciprocal_rank"], 0.5)

    def test_question_without_ground_truth_is_not_scored(self):
        """纯文本临时问题没有标准答案，应保留给人工看，而不是判成失败。"""
        self.assertIsNone(score_ranked_hits([], []))

    def test_neighbor_parts_count_as_one_ranked_parent(self):
        """同一父 section 的相邻片用于补上下文，不能占用两个 Top-K 名额。"""
        hits = [
            {"source": "windows.md", "parent_chunk_id": "window-section"},
            {"source": "windows.md", "parent_chunk_id": "window-section"},
            {"source": "doors.md", "parent_chunk_id": "door-section"},
        ]

        selected = select_ranked_parent_groups(hits, top_k=2)

        self.assertEqual([hit["source"] for hit in selected], ["windows.md", "doors.md"])


if __name__ == "__main__":
    unittest.main()
