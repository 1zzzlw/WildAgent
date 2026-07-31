import unittest
from unittest.mock import Mock

from app.spec.loader import RAGSpecLoader, SpecChunk


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
    loader._get_collection = Mock(return_value=collection)
    loader._build_chunks = Mock(return_value=chunks)
    return loader, collection


class RAGIndexSyncTest(unittest.TestCase):
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

    def test_unchanged_chunks_skip_embedding_upsert(self):
        chunks = [make_chunk("a"), make_chunk("b")]
        loader, collection = make_loader(
            ["a", "b"],
            chunks,
            [chunk.metadata for chunk in chunks],
        )

        updated = loader.sync_index()

        self.assertEqual(updated, 0)
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
