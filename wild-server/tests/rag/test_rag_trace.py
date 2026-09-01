"""RAGTrace 请求级观测测试。

阅读顺序建议：
1. ``with rag_trace_scope(...)`` 模拟一次用户请求；
2. ``record_*`` 模拟这次请求中发生的检索、上下文拼接和模型调用；
3. 最后的断言验证这些数据能否通过同一个 request_id 串起来。

这里使用 Mock 模拟 Chroma，不连接真实数据库，也不会消耗向量或大模型额度。
"""

import unittest
from unittest.mock import Mock

from app.agent.rag_trace import (
    get_current_rag_trace,
    make_query_trace,
    rag_trace_scope,
    record_rag_context,
    record_rag_error,
    record_rag_llm_call,
    record_rag_retrieval,
    record_rag_warning,
)
from app.spec.loader import RAGSpecLoader, RetrievedSpecChunk


class RAGTraceTest(unittest.TestCase):
    def test_one_request_collects_retrieval_context_and_tokens(self):
        """同一次请求的距离、上下文长度和 Token 应进入同一条追踪记录。"""
        hit = RetrievedSpecChunk(
            document="窗构件参数",
            metadata={
                "source": "components/windows.md",
                "heading": "基础静态窗 > 参数契约",
            },
            distance=0.18,
            id="chunk_windows_001",
        )

        with rag_trace_scope("req_trace_001", persist=False) as trace:
            # 当前异步/同步执行上下文中能拿到同一个 trace，实际 Loader 依赖这一点写记录。
            self.assertIs(get_current_rag_trace(), trace)
            record_rag_retrieval(
                operation="retrieve",
                queries=[make_query_trace("基础静态窗参数")],
                hits=[hit],
                elapsed_ms=12,
            )
            record_rag_context(
                operation="load",
                base_chars=100,
                retrieved_chars=6,
                context_chars=140,
                retrieved_count=1,
            )
            record_rag_llm_call(
                mode="invoke",
                elapsed_ms=80,
                token_usage={"input": 120, "output": 30, "total": 150},
            )

        data = trace.to_dict()
        self.assertEqual(data["request_id"], "req_trace_001")
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["retrievals"][0]["hits"][0]["chunk_id"], "chunk_windows_001")
        self.assertEqual(data["retrievals"][0]["hits"][0]["raw_distance"], 0.18)
        self.assertEqual(data["summary"]["max_context_chars"], 140)
        self.assertEqual(data["summary"]["token_usage"]["total"], 150)
        self.assertIsNone(get_current_rag_trace())

    def test_record_helpers_are_noop_without_request_scope(self):
        """命令行分片预览等非请求代码没有 trace 时，记录函数不应报错。"""
        self.assertFalse(record_rag_retrieval("retrieve", [], [], 0))
        self.assertFalse(record_rag_context("load", 0, 0, 0, 0))
        self.assertFalse(record_rag_llm_call("invoke", 0, None))
        self.assertFalse(record_rag_warning("code", "message"))

    def test_warning_is_recorded_into_trace(self):
        """hash 降级等告警应进入 Trace 的 warnings 列表，供离线排查。"""
        with rag_trace_scope("req_warning_001", persist=False) as trace:
            self.assertTrue(record_rag_warning(
                "hash_embedding_fallback",
                "当前使用 hash fallback embedding，仅适合本地 smoke test",
            ))
        data = trace.to_dict()
        self.assertEqual(data["warnings"][0]["code"], "hash_embedding_fallback")
        self.assertIn("hash fallback embedding", data["warnings"][0]["message"])

    def test_hash_retrieval_records_warning_in_trace(self):
        """hash 模式检索应在请求 trace 中标记 hash_embedding_fallback。"""
        collection = Mock()
        collection.count.return_value = 1
        collection.query.return_value = {
            "documents": [["villa content"]],
            "metadatas": [[{"content_hash": "villa"}]],
            "distances": [[0.1]],
        }
        loader = object.__new__(RAGSpecLoader)
        loader._namespace = "test"
        loader._top_k = 1
        loader._last_results = []
        loader._retrieval_cache = {}
        loader._last_sync_stats = {"total": 1, "updated": 0, "deleted": 0}
        loader._get_collection = Mock(return_value=collection)
        loader._query_rewrite_enabled = False

        with rag_trace_scope("req_hash_warning_001", persist=False) as trace:
            loader.retrieve("别墅怎么生成")
        data = trace.to_dict()
        self.assertEqual(data["warnings"][0]["code"], "hash_embedding_fallback")

    def test_handled_error_event_keeps_trace_error_status(self):
        with rag_trace_scope("req_error_001", persist=False) as trace:
            record_rag_error("处理失败", error_type="HandledError")
        self.assertEqual(trace.status, "error")
        self.assertEqual(trace.error_type, "HandledError")

    def test_loader_keeps_real_chroma_id_and_does_not_change_distance(self):
        """Loader 应原样返回 Chroma 的 ID 和距离，观测层不能改变召回结果。"""
        collection = Mock()
        collection.count.return_value = 1
        collection.query.return_value = {
            "ids": [["chunk_door_001"]],
            "documents": [["门构件参数"]],
            "metadatas": [[{
                "content_hash": "door-contract",
                "source": "components/doors.md",
                "heading": "门构件 > 参数契约",
            }]],
            "distances": [[0.23]],
        }

        # object.__new__ 绕过正式初始化，避免测试创建真实 Chroma 客户端。
        loader = object.__new__(RAGSpecLoader)
        loader._namespace = "test"
        loader._top_k = 1
        loader._last_results = []
        loader._get_collection = Mock(return_value=collection)

        with rag_trace_scope("req_loader_001", persist=False) as trace:
            results = loader.retrieve("门有哪些参数", {"entity_type": "door"})

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "chunk_door_001")
        self.assertEqual(results[0].distance, 0.23)
        self.assertEqual(trace.retrievals[0]["hits"][0]["chunk_id"], "chunk_door_001")
        self.assertEqual(trace.retrievals[0]["hits"][0]["raw_distance"], 0.23)
        effective_filter = trace.retrievals[0]["queries"][0]["effective_filter"]
        self.assertIn({"entity_type": "door"}, effective_filter["$and"])


if __name__ == "__main__":
    unittest.main()
