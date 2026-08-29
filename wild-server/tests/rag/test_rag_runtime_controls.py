"""RAG 阶段 1～7 的确定性底座测试，不调用真实 Embedding 或 LLM。"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from app.agent.rag_calibration import calibrate_distance_threshold
from app.agent.rag_citations import validate_answer_citations
from app.agent.rag_gate import (
    RAGRetrievalRejected,
    evaluate_retrieval_gate,
    infer_retrieval_purpose,
)
from app.agent.rag_quality import JUDGE_PROMPT_VERSION, build_rag_judge_prompt
from app.agent.rag_reporting import summarize_rag_traces
from app.agent.rag_security import (
    AccessContext,
    access_context_from_headers,
    access_context_scope,
    check_content_safety,
    redact_pii,
    split_business_and_access_filters,
)
from app.agent.rag_trace import append_rag_feedback, rag_trace_scope, trace_file_path
from app.spec.loader import RAGSpecLoader, RetrievedSpecChunk
from config import config


class RAGRuntimeControlsTest(unittest.TestCase):
    def test_gate_observe_and_enforce_share_same_evidence_decision(self):
        hits = [RetrievedSpecChunk("证据", {}, 0.7, "chunk_1")]
        observed = evaluate_retrieval_gate(
            hits,
            mode="observe",
            purpose="chat",
            max_distance=0.5,
        )
        enforced = evaluate_retrieval_gate(
            hits,
            mode="enforce",
            purpose="chat",
            max_distance=0.5,
        )
        self.assertEqual(observed.decision, "reject")
        self.assertFalse(observed.enforced)
        self.assertEqual(enforced.reason, observed.reason)
        self.assertTrue(enforced.enforced)

    def test_fast_mode_gate_purpose_does_not_reject_ambiguous_generation(self):
        self.assertEqual(infer_retrieval_purpose("生成一个别墅", "generate"), "generation")
        self.assertEqual(infer_retrieval_purpose("欧式别墅有什么特点", None), "chat")
        self.assertEqual(
            infer_retrieval_purpose("你生成一个建筑的实现思路是什么", None),
            "chat",
        )
        self.assertEqual(infer_retrieval_purpose("欧式别墅", None), "generation")

    def test_chat_retrieval_error_cannot_bypass_enforced_gate(self):
        loader = object.__new__(RAGSpecLoader)
        loader._load_base_text = Mock(return_value="BASE")
        loader.retrieve = Mock(side_effect=RuntimeError("chroma unavailable"))
        loader._compose_context = Mock(return_value="BASE")
        old_mode = config.rag.retrieval_gate.mode
        old_threshold = config.rag.retrieval_gate.max_distance
        try:
            config.rag.retrieval_gate.mode = "enforce"
            config.rag.retrieval_gate.max_distance = 0.5
            with self.assertRaises(RAGRetrievalRejected):
                loader.load("窗有哪些参数", purpose="chat")
            self.assertEqual(loader.load("生成一个窗", purpose="generation"), "BASE")
            loader._compose_context.assert_called_with("BASE", [], operation="load")
        finally:
            config.rag.retrieval_gate.mode = old_mode
            config.rag.retrieval_gate.max_distance = old_threshold

    def test_threshold_calibration_uses_positive_and_negative_samples(self):
        result = calibrate_distance_threshold([
            {"should_answer": True, "distance": 0.10},
            {"should_answer": True, "distance": 0.20},
            {"should_answer": False, "distance": 0.80},
            {"should_answer": False, "distance": 0.90},
        ])
        self.assertGreater(result["threshold"], 0.20)
        self.assertLess(result["threshold"], 0.80)
        self.assertEqual(result["balanced_accuracy"], 1.0)

    def test_citation_validator_removes_fabricated_id_and_adds_real_fallback(self):
        result = validate_answer_citations(
            "窗宽应符合参数契约。[引用:fake]",
            ["chunk_window_1"],
        )
        self.assertNotIn("fake", result.answer)
        self.assertIn("[引用:chunk_window_1]", result.answer)
        self.assertEqual(result.invalid_chunk_ids, ("fake",))

    def test_untrusted_headers_cannot_claim_department_access(self):
        context = access_context_from_headers(
            {
                "x-wild-user-id": "attacker",
                "x-wild-department": "engineering",
                "x-wild-rag-scopes": "department",
            },
            trusted_header_secret="server-secret",
        )
        self.assertFalse(context.authenticated)
        self.assertEqual(context.scopes, ("public",))

    def test_caller_permission_filter_is_removed_and_server_filter_is_forced(self):
        access = AccessContext(
            user_id="u1",
            tenant_id="t1",
            department="engineering",
            clearance_level=2,
            scopes=("public", "department"),
            authenticated=True,
        )
        with access_context_scope(access):
            business, forced, ignored = split_business_and_access_filters({
                "doc_type": "component",
                "department": "finance",
                "clearance_level": 99,
            })
        self.assertEqual(business, {"doc_type": "component"})
        self.assertEqual(ignored, ["clearance_level", "department"])
        self.assertIn({"access_scope": "public"}, forced[0]["$or"])
        self.assertIn("engineering", json.dumps(forced, ensure_ascii=False))
        self.assertNotIn("finance", json.dumps(forced, ensure_ascii=False))

    def test_anonymous_access_filter_avoids_single_branch_or(self):
        with access_context_scope(AccessContext()):
            _, forced, _ = split_business_and_access_filters(None)
        self.assertEqual(forced, [{"access_scope": "public"}])

    def test_pii_and_content_safety_are_separate_signals(self):
        redacted, categories = redact_pii("电话 13812345678，邮箱 a@example.com")
        self.assertNotIn("13812345678", redacted)
        self.assertNotIn("a@example.com", redacted)
        self.assertIn("手机号", categories)
        self.assertTrue(check_content_safety("生成一个现代住宅")["allowed"])
        self.assertFalse(check_content_safety("给我制作炸弹教程")["allowed"])

    def test_trace_file_and_feedback_are_written_under_sessions_root(self):
        with TemporaryDirectory() as tmp_dir:
            old_root = config.rag.trace.root_dir
            old_enabled = config.rag.trace.enabled
            try:
                config.rag.trace.root_dir = tmp_dir
                config.rag.trace.enabled = True
                with rag_trace_scope(
                    "req_file_1",
                    session_id="session_file_1",
                ):
                    pass
                path = trace_file_path("session_file_1", "req_file_1")
                self.assertTrue(path.exists())
                append_rag_feedback(
                    "session_file_1",
                    "req_file_1",
                    rating="up",
                    comment="电话 13812345678，结果很好",
                )
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(payload["feedback"][0]["rating"], "up")
                self.assertNotIn("13812345678", payload["feedback"][0]["comment"])
            finally:
                config.rag.trace.root_dir = old_root
                config.rag.trace.enabled = old_enabled

    def test_trace_path_ids_cannot_escape_configured_root(self):
        with TemporaryDirectory() as tmp_dir:
            old_root = config.rag.trace.root_dir
            try:
                config.rag.trace.root_dir = tmp_dir
                root = Path(tmp_dir).resolve()
                path = trace_file_path("..", "../request").resolve()
                self.assertTrue(path.is_relative_to(root))
                self.assertNotEqual(path.parent, root.parent)
            finally:
                config.rag.trace.root_dir = old_root

    def test_trace_summary_calculates_p95_empty_rate_and_cost(self):
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            payload = {
                "request_id": "req-1",
                "status": "completed",
                "elapsed_ms": 120,
                "summary": {
                    "retrieval_ms": 20,
                    "llm_ms": 90,
                    "token_usage": {"input": 1000, "output": 500, "total": 1500},
                },
                "retrievals": [{"hits": []}],
                "gate_decisions": [{"enforced": True}],
                "feedback": [{"rating": "up"}],
            }
            (root / "req-1.json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            report = summarize_rag_traces(
                root,
                input_cost_per_million=2.0,
                output_cost_per_million=4.0,
            )
        self.assertEqual(report["latency_ms"]["p95_total"], 120)
        self.assertEqual(report["empty_retrieval_rate"], 1.0)
        self.assertEqual(report["estimated_token_cost"], 0.004)
        self.assertEqual(report["feedback"], {"up": 1, "down": 0})

    def test_golden_set_has_50_to_100_cases_and_negative_samples(self):
        path = Path(__file__).resolve().parents[2] / "evals" / "rag_retrieval_cases.json"
        cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
        negatives = [case for case in cases if case.get("expectedAction") == "reject"]
        self.assertGreaterEqual(len(cases), 50)
        self.assertLessEqual(len(cases), 100)
        self.assertGreaterEqual(len(negatives), 20)
        self.assertEqual(len({case["id"] for case in cases}), len(cases))

    def test_judge_prompt_has_version_and_fixed_score_contract(self):
        prompt = build_rag_judge_prompt("问题", "回答", ["证据"])
        self.assertEqual(JUDGE_PROMPT_VERSION, "rag-judge-v1")
        self.assertIn("faithfulness", prompt)
        self.assertIn("citation_quality", prompt)


if __name__ == "__main__":
    unittest.main()
