import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from app.spec.loader import MarkdownChunker, RAGSpecLoader, RetrievedSpecChunk


class RAGSemanticChunkingTest(unittest.TestCase):
    def _split(self, filename: str, text: str, chunk_size: int = 240):
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / filename
            path.write_text(text, encoding="utf-8")
            return MarkdownChunker(
                chunk_size=chunk_size,
                chunk_overlap=40,
            ).split_file(path, namespace="test")

    def test_heading_path_and_entity_metadata_reach_every_length_part(self):
        chunks = self._split(
            "windows.md",
            """---
doc_type: component
doc_scope: generation
knowledge_layer: architecture
entity_type: window
entity_name: window_family
topic: assembly
wild_version: "1.1"
status: supported
authority: schema
source: components/windows.md
keywords:
  - 窗
  - window
---
# 窗构件

## 支摘窗

<!-- rag-meta
entity_type: window
entity_name: zhizhai_window
topic: constraints
status: supported
authority: verified_example
keywords: 支摘窗, zhizhai window, opening
-->

### 支摘窗参数与空间约束

支摘窗必须先建立 opening，再使用当前引擎支持的构件表达细节。"""
            + "参数说明。" * 90,
        )

        parameter_chunks = [
            chunk for chunk in chunks
            if "支摘窗参数与空间约束" in chunk.metadata["heading"]
        ]
        self.assertGreater(len(parameter_chunks), 1)
        parent_ids = {chunk.metadata["parent_chunk_id"] for chunk in parameter_chunks}
        self.assertEqual(len(parent_ids), 1)
        self.assertEqual(
            [chunk.metadata["part_index"] for chunk in parameter_chunks],
            list(range(len(parameter_chunks))),
        )
        for chunk in parameter_chunks:
            self.assertEqual(chunk.metadata["doc_type"], "component")
            self.assertEqual(chunk.metadata["entity_type"], "window")
            self.assertEqual(chunk.metadata["entity_name"], "zhizhai_window")
            self.assertEqual(chunk.metadata["topic"], "constraints")
            self.assertIn("窗构件 > 支摘窗 > 支摘窗参数与空间约束", chunk.document)
            self.assertNotIn("rag-meta", chunk.document)

    def test_length_fallback_keeps_json_and_table_structurally_complete(self):
        long_value = "x" * 420
        rows = "\n".join(f"| 窗型{i} | opening | {i} |" for i in range(18))
        chunks = self._split(
            "atomic.md",
            f"""# 窗构件

## 落地窗示例

以下是完整 JSON 示例。

```json
{{"id": "window", "type": "opening", "description": "{long_value}"}}
```

| 名称 | WILD type | 数量 |
|---|---|---|
{rows}
""",
            chunk_size=240,
        )

        json_chunks = [chunk for chunk in chunks if "```json" in chunk.document]
        self.assertEqual(len(json_chunks), 1)
        self.assertEqual(json_chunks[0].document.count("```"), 2)
        json_text = json_chunks[0].document.split("```json", 1)[1].split("```", 1)[0]
        json.loads(json_text)

        table_chunks = [chunk for chunk in chunks if "| 名称 | WILD type | 数量 |" in chunk.document]
        self.assertGreater(len(table_chunks), 1)
        for chunk in table_chunks:
            self.assertIn("|---|---|---|", chunk.document)

    def test_readme_is_inferred_as_index_scope(self):
        chunks = self._split(
            "README.md",
            """# 构件索引

## 当前拆分

这里仅用于导航，不应进入普通建筑生成检索。
""",
        )

        self.assertTrue(chunks)
        self.assertTrue(all(chunk.metadata["doc_type"] == "index" for chunk in chunks))
        self.assertTrue(all(chunk.metadata["doc_scope"] == "index" for chunk in chunks))

    def test_empty_container_heading_is_not_indexed(self):
        chunks = self._split(
            "public.md",
            """# 公共建筑

## 二、公共建筑

---

### 教育建筑

教育建筑需要明确教室、走廊和楼梯等业务构件。
""",
        )

        headings = [chunk.metadata["heading"] for chunk in chunks]
        self.assertNotIn("公共建筑 > 二、公共建筑", headings)
        self.assertTrue(any("教育建筑" in heading for heading in headings))

    def test_body_hash_ignores_repeated_knowledge_path_prefix(self):
        first = self._split(
            "first.md",
            """# 屋顶构件

## 屋顶类型速查

| 类型 | roofType |
|---|---|
| 人字坡顶 | gable |
""",
        )[-1]
        second = self._split(
            "second.md",
            """# 风格配方

## 屋顶类型速查

| 类型 | roofType |
|---|---|
| 人字坡顶 | gable |
""",
        )[-1]

        self.assertNotEqual(first.metadata["content_hash"], second.metadata["content_hash"])
        self.assertEqual(first.metadata["body_hash"], second.metadata["body_hash"])

    def test_retrieve_combines_namespace_scope_and_business_filters(self):
        collection = Mock()
        collection.count.return_value = 3
        collection.query.return_value = {
            "documents": [["window content"]],
            "metadatas": [[{"content_hash": "window"}]],
            "distances": [[0.1]],
        }
        loader = object.__new__(RAGSpecLoader)
        loader._namespace = "test"
        loader._top_k = 2
        loader._last_results = []
        loader._get_collection = Mock(return_value=collection)

        loader.retrieve(
            "支摘窗",
            metadata_filter={"doc_type": "component", "entity_type": "window"},
        )

        self.assertEqual(
            collection.query.call_args.kwargs["where"],
            {
                "$and": [
                    {"namespace": "test"},
                    {"doc_scope": {"$ne": "index"}},
                    {"status": {"$ne": "proposed"}},
                    {"authority": {"$ne": "inferred"}},
                    {"doc_type": "component"},
                    {"entity_type": "window"},
                ]
            },
        )

    def test_context_limit_keeps_retrieved_chunks_atomic(self):
        loader = object.__new__(RAGSpecLoader)
        loader._max_context_chars = 360
        loader._loaded_at = None
        chunks = [
            RetrievedSpecChunk(
                document="```json\n{\"id\": \"one\", \"value\": \"" + "x" * 90 + "\"}\n```",
                metadata={
                    "source": "one.md",
                    "heading": "示例一",
                    "doc_type": "component",
                    "entity_name": "one",
                    "status": "supported",
                    "authority": "schema",
                },
                distance=0.1,
            ),
            RetrievedSpecChunk(
                document="```json\n{\"id\": \"two\", \"value\": \"" + "y" * 180 + "\"}\n```",
                metadata={
                    "source": "two.md",
                    "heading": "示例二",
                    "doc_type": "component",
                    "entity_name": "two",
                    "status": "supported",
                    "authority": "schema",
                },
                distance=0.2,
            ),
        ]

        context = loader._compose_context("BASE", chunks)

        self.assertIn('"id": "one"', context)
        self.assertNotIn('"id": "two"', context)
        self.assertIn("status=supported", context)
        self.assertIn("authority=schema", context)
        self.assertEqual(context.count("```"), 2)
        self.assertIn("完整片段数量受上下文上限限制", context)


if __name__ == "__main__":
    unittest.main()
