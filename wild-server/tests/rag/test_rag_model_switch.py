"""切换 Embedding 模型时的集合保护回归。"""

import sys
import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.spec.loader import RAGSpecLoader


def make_loader(*, allow_destructive_rebuild: bool):
    loader = object.__new__(RAGSpecLoader)
    loader._persist_dir = Path(".rag_model_switch_test")
    loader._collection_name = "wild_knowledge_base"
    loader._namespace = "test_model_switch"
    loader._embedding_function = Mock()
    loader._collection = None
    loader._client = None
    loader._allow_destructive_rebuild = allow_destructive_rebuild
    loader._index_signature = Mock(return_value="new-signature")
    return loader


class RAGModelSwitchTest(unittest.TestCase):
    def tearDown(self):
        shutil.rmtree(".rag_model_switch_test", ignore_errors=True)

    def test_runtime_refuses_to_delete_old_collection_on_signature_mismatch(self):
        loader = make_loader(allow_destructive_rebuild=False)
        old_collection = SimpleNamespace(metadata={"index_signature": "old-signature"})
        client = Mock()
        client.get_or_create_collection.return_value = old_collection
        chromadb = SimpleNamespace(PersistentClient=Mock(return_value=client))

        with patch.dict(sys.modules, {"chromadb": chromadb}):
            with self.assertRaisesRegex(RuntimeError, "保护旧索引"):
                loader._get_collection()

        client.delete_collection.assert_not_called()

    def test_explicit_maintenance_path_can_rebuild_collection(self):
        loader = make_loader(allow_destructive_rebuild=True)
        old_collection = SimpleNamespace(metadata={"index_signature": "old-signature"})
        new_collection = SimpleNamespace(metadata={"index_signature": "new-signature"})
        client = Mock()
        client.get_or_create_collection.side_effect = [old_collection, new_collection]
        chromadb = SimpleNamespace(PersistentClient=Mock(return_value=client))

        with patch.dict(sys.modules, {"chromadb": chromadb}):
            result = loader._get_collection()

        self.assertIs(result, new_collection)
        client.delete_collection.assert_called_once_with(name="wild_knowledge_base")


if __name__ == "__main__":
    unittest.main()
