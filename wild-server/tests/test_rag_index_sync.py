import unittest
from unittest.mock import Mock

from app.spec.loader import RAGSpecLoader, SpecChunk


def make_chunk(chunk_id: str) -> SpecChunk:
    return SpecChunk(
        id=chunk_id,
        document=f"content:{chunk_id}",
        metadata={"namespace": "test", "content_hash": chunk_id},
    )


def make_loader(existing_ids: list[str], chunks: list[SpecChunk]):
    collection = Mock()
    collection.get.return_value = {"ids": existing_ids, "metadatas": []}

    loader = object.__new__(RAGSpecLoader)
    loader._namespace = "test"
    loader._last_sync_stats = {"total": 0, "updated": 0, "deleted": 0}
    loader._get_collection = Mock(return_value=collection)
    loader._build_chunks = Mock(return_value=chunks)
    return loader, collection


class RAGIndexSyncTest(unittest.TestCase):
    def test_unchanged_chunks_skip_embedding_upsert(self):
        loader, collection = make_loader(["a", "b"], [make_chunk("a"), make_chunk("b")])

        updated = loader.sync_index()

        self.assertEqual(updated, 0)
        collection.upsert.assert_not_called()
        collection.delete.assert_not_called()
        self.assertEqual(
            loader.last_sync_stats,
            {"total": 2, "updated": 0, "deleted": 0},
        )

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
