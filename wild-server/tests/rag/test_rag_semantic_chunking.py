"""把 Markdown 分片规则写成可重复验证的例子。

阅读建议：每个测试都遵循“准备输入 → 调用真实代码 → 检查结果”三步。
这里故意使用临时文件和 Mock（假对象），不会读取或修改正式知识库与 Chroma。
"""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from app.spec.loader import MarkdownChunker, RAGSpecLoader, RetrievedSpecChunk


class RAGSemanticChunkingTest(unittest.TestCase):
    def _split(self, filename: str, text: str, chunk_size: int = 240):
        """把一段测试 Markdown 写进临时文件，再交给生产 MarkdownChunker。"""
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / filename
            path.write_text(text, encoding="utf-8")
            return MarkdownChunker(
                chunk_size=chunk_size,
                chunk_overlap=40,
            ).split_file(path, namespace="test")

    def test_heading_path_and_entity_metadata_reach_every_length_part(self):
        """长章节拆成多片后，每片仍应知道自己属于哪个实体和标题路径。"""
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
primary_terms:
  - 窗
  - opening
synonyms:
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
primary_terms:
  - 支摘窗
  - opening
synonyms:
  - zhizhai window
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
            self.assertEqual(chunk.metadata["primary_terms"], "支摘窗, opening")
            self.assertEqual(chunk.metadata["synonyms"], "zhizhai window")
            self.assertIn("窗构件 > 支摘窗 > 支摘窗参数与空间约束", chunk.document)
            self.assertNotIn("rag-meta", chunk.document)

    def test_path_config_supplies_defaults_but_frontmatter_has_final_say(self):
        """路径配置减少重复字段，文件头仍可覆盖特例。"""
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_path = root / "config.yaml"
            config_path.write_text(
                """defaults:
  wild_version: "1.1"
mapping_rules:
  - path_pattern: "components/*.md"
    metadata:
      doc_type: component
      doc_scope: generation
      status: deprecated
""",
                encoding="utf-8",
            )
            document_path = root / "components" / "example.md"
            document_path.parent.mkdir()
            document_path.write_text(
                """---
doc_type: recipe
status: supported
---
# 示例

这里是用于测试路径 metadata 合并顺序的正文。
""",
                encoding="utf-8",
            )

            chunks = MarkdownChunker(
                chunk_size=240,
                chunk_overlap=40,
                metadata_config_path=config_path,
            ).split_file(document_path, namespace="test")

        self.assertTrue(chunks)
        self.assertEqual(chunks[0].metadata["wild_version"], "1.1")
        self.assertEqual(chunks[0].metadata["doc_scope"], "generation")
        self.assertEqual(chunks[0].metadata["doc_type"], "recipe")
        self.assertEqual(chunks[0].metadata["status"], "supported")

    def test_legacy_keywords_are_exposed_through_new_term_fields(self):
        """Loader 只为外部旧文档保留兼容，不要求它们一次性同步迁移。"""
        chunks = self._split(
            "legacy.md",
            """---
keywords: 旧主词, old alias
---
# 旧文档

这是一份尚未迁移的外部知识文档。
""",
        )

        self.assertEqual(chunks[0].metadata["keywords"], "旧主词, old alias")
        self.assertEqual(chunks[0].metadata["primary_terms"], "旧主词, old alias")
        self.assertEqual(chunks[0].metadata["synonyms"], "")

    def test_length_fallback_keeps_json_and_table_structurally_complete(self):
        """长度兜底可以拆普通文本和表格行，但不能从中间切断 JSON。"""
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
        """README 只负责导航，必须标成 index，避免污染建筑生成召回。"""
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
        """只有标题和分隔线的空章节不应浪费一个向量。"""
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
        """正文相同但父标题不同的内容应有相同 body_hash，供跨文件判重。"""
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
        """检索条件必须同时包含索引隔离、安全过滤和调用方业务过滤。"""
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
                    {"access_scope": "public"},
                    {"doc_type": "component"},
                    {"entity_type": "window"},
                ]
            },
        )

    def test_context_limit_keeps_retrieved_chunks_atomic(self):
        """Prompt 放不下所有结果时，应舍弃整片，不能截断 JSON 片段。"""
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
