import unittest
from unittest.mock import Mock, patch

from app.spec.loader import RAGSpecLoader, SpecChunk


class APITimeoutError(Exception):
    """测试用超时类型；Loader 只依赖异常类型名，避免发起真实网络请求。"""


def make_chunk(chunk_id: str) -> SpecChunk:
    return SpecChunk(
        id=chunk_id,
        document=f"content:{chunk_id}",
        metadata={"namespace": "test", "content_hash": chunk_id},
    )


def make_loader(
    existing_ids: list[str],
    chunks: list[SpecChunk],
    existing_metadatas: list[dict] | None = None,
):
    collection = Mock()
    collection.get.return_value = {
        "ids": existing_ids,
        "metadatas": existing_metadatas or [],
    }

    loader = object.__new__(RAGSpecLoader)
    loader._namespace = "test"
    loader._last_sync_stats = {"total": 0, "updated": 0, "deleted": 0}
    loader._embedding_function = Mock()
    loader._embedding_function.embed_documents.side_effect = (
        lambda documents: [[float(index)] for index, _ in enumerate(documents)]
    )
    loader._get_collection = Mock(return_value=collection)
    loader._build_chunks = Mock(return_value=chunks)
    return loader, collection


class RAGIndexSyncTest(unittest.TestCase):
    def test_timeout_batch_is_deferred_and_retried_after_other_batches(self):
        loader, collection = make_loader([], [make_chunk(str(i)) for i in range(11)])
        calls = 0

        def embed(documents):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise APITimeoutError("temporary timeout")
            return [[float(index)] for index, _ in enumerate(documents)]

        loader._embedding_function.embed_documents.side_effect = embed
        with patch("app.spec.loader.logger") as log:
            self.assertEqual(loader.sync_index(), 11)

        self.assertEqual([len(call.kwargs["ids"]) for call in collection.upsert.call_args_list], [1, 10])
        warning_messages = [call.args[0] for call in log.warning.call_args_list]
        self.assertTrue(any("已延后" in message for message in warning_messages))
        self.assertTrue(any("开始重试" in message for message in warning_messages))

    def test_retry_timeout_keeps_failed_batch_pending_without_disabling_rag(self):
        loader, collection = make_loader([], [make_chunk(str(i)) for i in range(11)])
        calls = 0

        def embed(documents):
            nonlocal calls
            calls += 1
            if calls in {1, 3}:
                raise APITimeoutError("persistent timeout")
            return [[float(index)] for index, _ in enumerate(documents)]

        loader._embedding_function.embed_documents.side_effect = embed
        with patch("app.spec.loader.logger") as log:
            self.assertEqual(loader.sync_index(), 1)

        self.assertEqual(collection.upsert.call_count, 1)
        self.assertEqual(loader.last_sync_stats, {"total": 11, "updated": 1, "deleted": 0})
        self.assertEqual(loader.last_sync_pending, 10)
        warning_messages = [
            call.args[0].format(*call.args[1:])
            for call in log.warning.call_args_list
        ]
        self.assertTrue(any("完成但仍有 10 块待同步" in message for message in warning_messages))

    def test_progress_advances_only_after_each_batch_succeeds(self):
        loader, collection = make_loader([], [make_chunk(str(i)) for i in range(11)])
        messages = []
        progress_at_upsert = []

        def capture(message, *args):
            messages.append(message.format(*args))

        def upsert(**kwargs):
            progress_at_upsert.append(next(
                message for message in reversed(messages)
                if message.startswith("RAG 向量化 [")
            ))

        collection.upsert.side_effect = upsert
        with patch("app.spec.loader.logger") as log:
            log.info.side_effect = capture
            self.assertEqual(loader.sync_index(), 11)

        self.assertIn("0/11 块", progress_at_upsert[0])
        self.assertIn("第 1/2 批：请求 Embedding", progress_at_upsert[0])
        self.assertIn("10/11 块", progress_at_upsert[1])
        self.assertIn("第 2/2 批：请求 Embedding", progress_at_upsert[1])
        self.assertTrue(any("[####################] 100% 11/11 块" in m for m in messages))
        self.assertIn("RAG 索引同步完成", messages[-1])

    def test_progress_reports_no_embedding_for_unchanged_index(self):
        chunk = make_chunk("a")
        loader, collection = make_loader(["a"], [chunk], [chunk.metadata])
        with patch("app.spec.loader.logger") as log:
            self.assertEqual(loader.sync_index(), 0)
        log.info.assert_any_call("RAG 索引同步：无需重新向量化")
        collection.upsert.assert_not_called()

    def test_failed_batch_reports_last_successful_progress_and_reraises(self):
        loader, collection = make_loader([], [make_chunk(str(i)) for i in range(11)])
        error = RuntimeError("{'error': 'upstream unavailable'}")
        collection.upsert.side_effect = [None, error]
        with patch("app.spec.loader.logger") as log:
            with self.assertRaises(RuntimeError) as caught:
                loader.sync_index()
        self.assertIs(caught.exception, error)
        log.error.assert_called_once()
        self.assertEqual(log.error.call_args.args[1:5], (2, 2, 10, 11))
        messages = [call.args[0].format(*call.args[1:]) for call in log.info.call_args_list]
        self.assertFalse(any("100%" in m or "RAG 索引同步完成" in m for m in messages))

    def test_supported_maintainer_chunk_can_outrank_nearby_experimental_chunk(self):
        collection = Mock()
        collection.count.return_value = 2
        collection.query.return_value = {
            "documents": [["short experiment", "maintained pattern"]],
            "metadatas": [[
                {
                    "source": "experiment.md",
                    "content_hash": "experiment",
                    "status": "experimental",
                    "authority": "domain",
                },
                {
                    "source": "pattern.md",
                    "content_hash": "pattern",
                    "status": "supported",
                    "authority": "maintainer",
                },
            ]],
            "distances": [[0.10, 0.14]],
        }
        loader = object.__new__(RAGSpecLoader)
        loader._namespace = "test"
        loader._last_results = []
        loader._get_collection = Mock(return_value=collection)

        results = loader.retrieve_many(["复杂建筑"], per_query=1)

        self.assertEqual(results[0].metadata["source"], "pattern.md")

    def test_retrieve_many_keeps_one_result_per_query(self):
        collection = Mock()
        collection.count.return_value = 4
        collection.query.return_value = {
            "documents": [
                ["villa content", "fallback content"],
                ["window content", "other content"],
            ],
            "metadatas": [
                [
                    {"source": "villas.md", "content_hash": "villa"},
                    {"source": "fallback.md", "content_hash": "fallback"},
                ],
                [
                    {"source": "windows.md", "content_hash": "window"},
                    {"source": "other.md", "content_hash": "other"},
                ],
            ],
            "distances": [[0.1, 0.2], [0.1, 0.2]],
        }
        loader = object.__new__(RAGSpecLoader)
        loader._namespace = "test"
        loader._last_results = []
        loader._get_collection = Mock(return_value=collection)

        results = loader.retrieve_many(["villa", "window"], per_query=1)

        self.assertEqual(
            [result.metadata["source"] for result in results],
            ["villas.md", "windows.md"],
        )
        self.assertEqual(
            collection.query.call_args.kwargs["query_texts"],
            ["villa", "window"],
        )

    def test_retrieve_many_expands_adjacent_parent_parts(self):
        collection = Mock()
        collection.count.return_value = 3
        collection.query.return_value = {
            "documents": [["part one"]],
            "metadatas": [[{
                "source": "windows.md",
                "body_hash": "part-1",
                "parent_chunk_id": "parent",
                "part_index": 1,
            }]],
            "distances": [[0.1]],
        }
        collection.get.return_value = {
            "ids": ["p0", "p1", "p2"],
            "documents": ["part zero", "part one", "part two"],
            "metadatas": [
                {"source": "windows.md", "body_hash": "part-0", "parent_chunk_id": "parent", "part_index": 0},
                {"source": "windows.md", "body_hash": "part-1", "parent_chunk_id": "parent", "part_index": 1},
                {"source": "windows.md", "body_hash": "part-2", "parent_chunk_id": "parent", "part_index": 2},
            ],
        }
        loader = object.__new__(RAGSpecLoader)
        loader._namespace = "test"
        loader._last_results = []
        loader._get_collection = Mock(return_value=collection)

        results = loader.retrieve_many(["支摘窗"], per_query=1)

        self.assertEqual(
            [result.metadata["part_index"] for result in results],
            [0, 1, 2],
        )
        collection.get.assert_called_once()

    def test_unchanged_chunks_skip_embedding_upsert(self):
        chunks = [make_chunk("a"), make_chunk("b")]
        loader, collection = make_loader(
            ["a", "b"],
            chunks,
            [chunk.metadata for chunk in chunks],
        )

        updated = loader.sync_index()

        self.assertEqual(updated, 0)
        self.assertEqual(loader.last_sync_pending, 0)
        collection.upsert.assert_not_called()
        collection.update.assert_not_called()
        collection.delete.assert_not_called()
        self.assertEqual(
            loader.last_sync_stats,
            {"total": 2, "updated": 0, "deleted": 0},
        )

    def test_metadata_change_updates_without_reembedding(self):
        chunk = make_chunk("a")
        loader, collection = make_loader(
            ["a"],
            [chunk],
            [{"namespace": "test", "content_hash": "a", "doc_type": "knowledge"}],
        )

        updated = loader.sync_index()

        self.assertEqual(updated, 1)
        collection.update.assert_called_once_with(
            ids=["a"],
            metadatas=[chunk.metadata],
        )
        collection.upsert.assert_not_called()
        collection.delete.assert_not_called()

    def test_changed_chunk_deletes_old_id_and_upserts_new_id(self):
        loader, collection = make_loader(["old"], [make_chunk("new")])

        updated = loader.sync_index()

        self.assertEqual(updated, 1)
        collection.delete.assert_called_once_with(ids=["old"])
        collection.upsert.assert_called_once()
        self.assertEqual(collection.upsert.call_args.kwargs["ids"], ["new"])
        self.assertEqual(collection.upsert.call_args.kwargs["embeddings"], [[0.0]])
        self.assertEqual(
            loader.last_sync_stats,
            {"total": 1, "updated": 1, "deleted": 1},
        )

    def test_removed_document_deletes_stale_chunks(self):
        loader, collection = make_loader(["removed"], [])

        updated = loader.sync_index()

        self.assertEqual(updated, 0)
        collection.delete.assert_called_once_with(ids=["removed"])
        collection.upsert.assert_not_called()
        self.assertEqual(
            loader.last_sync_stats,
            {"total": 0, "updated": 0, "deleted": 1},
        )


if __name__ == "__main__":
    unittest.main()
