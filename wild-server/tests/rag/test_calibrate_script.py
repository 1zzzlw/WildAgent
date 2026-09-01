"""检索门禁校准脚本测试（JSON 模式 + 样本抽取）。"""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.rag.calibrate_retrieval_gate import _samples_from_eval_results


class CalibrateScriptTest(unittest.TestCase):
    def test_samples_extract_answer_and_reject_with_distance(self):
        results = [
            {"id": "a", "expectedAction": "answer", "hits": [{"distance": 0.1}]},
            {"id": "b", "expectedAction": "reject", "hits": [{"distance": 0.9}]},
        ]
        samples = _samples_from_eval_results(results)
        self.assertEqual(samples, [
            {"id": "a", "should_answer": True, "distance": 0.1},
            {"id": "b", "should_answer": False, "distance": 0.9},
        ])

    def test_empty_hits_become_none_distance(self):
        results = [{"id": "c", "expectedAction": "answer", "hits": []}]
        samples = _samples_from_eval_results(results)
        self.assertIsNone(samples[0]["distance"])

    def test_error_result_counts_as_empty_recall(self):
        results = [{"id": "d", "expectedAction": "answer", "error": "boom", "hits": []}]
        samples = _samples_from_eval_results(results)
        self.assertIsNone(samples[0]["distance"])

    def test_json_mode_writes_report(self):
        """main 的 JSON 模式应生成阈值报告并写入 --output。"""
        import io
        import sys
        from unittest.mock import patch

        from scripts.rag.calibrate_retrieval_gate import main

        payload = {
            "results": [
                {"id": "q1", "expectedAction": "answer", "hits": [{"distance": 0.15}]},
                {"id": "q2", "expectedAction": "reject", "hits": [{"distance": 0.55}]},
            ],
            "run": {"embedding": "test", "index_signature": "sig"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            eval_path = Path(tmp) / "eval.json"
            eval_path.write_text(json.dumps(payload), encoding="utf-8")
            out_path = Path(tmp) / "report.json"
            with patch.object(sys, "argv", ["calibrate", str(eval_path), "--output", str(out_path)]):
                code = main()
            self.assertEqual(code, 0)
            report = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(report["positive_samples"], 1)
            self.assertEqual(report["negative_samples"], 1)
            self.assertEqual(report["embedding"], "test")
            self.assertIn("RAG__RETRIEVAL_GATE__MAX_DISTANCE", report["config_example"])


if __name__ == "__main__":
    unittest.main()
