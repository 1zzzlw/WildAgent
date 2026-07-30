"""
Spec Document Loader —— 规范文档加载器

职责：加载 WILD 语言规范文档，注入到 LLM System Prompt 中。

设计原则：
  - 调用方只依赖 load() 和 list_sources()
  - FileSpecLoader 保留为确定性兜底
  - RAGSpecLoader 使用 Chroma 对完整知识库做语义检索
"""
from __future__ import annotations

import hashlib
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _normalize_path(path: Path) -> str:
    try:
        return str(path.resolve()).casefold()
    except OSError:
        return str(path.absolute()).casefold()


def collect_markdown_paths(root: str | Path, exclude: list[str | Path] | None = None) -> list[Path]:
    """递归收集知识库 Markdown 文件，用于 RAG 建索引。"""
    root_path = Path(root)
    if not root_path.exists():
        return []

    excluded = {_normalize_path(Path(path)) for path in (exclude or [])}
    paths = [
        path
        for path in root_path.rglob("*.md")
        if path.is_file() and _normalize_path(path) not in excluded
    ]
    return sorted(paths, key=lambda path: path.relative_to(root_path).as_posix().casefold())


class SpecLoader:
    """规范文档加载器抽象基类"""

    def load(self, query: str = "") -> str:
        """加载规范文档，返回拼接后的文本"""
        raise NotImplementedError

    def list_sources(self) -> list[str]:
        """返回已加载的文档路径或来源标识"""
        raise NotImplementedError


class FileSpecLoader(SpecLoader):
    """从文件系统直接读取规范文档"""

    def __init__(self, paths: list[str]):
        self._paths = [Path(p) for p in paths]
        self._loaded_at: float | None = None

    def load(self, query: str = "") -> str:
        """读取所有文件并拼接；query 参数用于兼容 RAGSpecLoader。"""
        texts: list[str] = []
        for p in self._paths:
            if p.exists():
                text = p.read_text(encoding="utf-8")
                texts.append(f"## {p.stem}\n\n{text}")
            else:
                texts.append(
                    f"<!-- 警告：规范文档不存在: {p} -->\n"
                    f"## {p.stem}\n\n（文件缺失，请检查路径配置）"
                )
        self._loaded_at = time.time()
        return "\n\n---\n\n".join(texts)

    def list_sources(self) -> list[str]:
        return [str(p) for p in self._paths]

    @property
    def loaded_at(self) -> float | None:
        return self._loaded_at


@dataclass(frozen=True)
class SpecChunk:
    """写入 Chroma 的规范片段"""

    id: str
    document: str
    metadata: dict[str, str | int | float | bool]


@dataclass(frozen=True)
class RetrievedSpecChunk:
    """从 Chroma 检索出的规范片段"""

    document: str
    metadata: dict[str, Any]
    distance: float | None


class HashEmbeddingFunction:
    """开发环境兜底 embedding。

    只用于缺少 EMBEDDING API 配置时的本地 smoke test。它基于字符和二元片段做
    hash 向量化，能处理关键词重合，但不能替代真实语义 embedding。
    """

    def __init__(self, dimension: int = 256):
        self.dimension = dimension

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in input]

    def embed_query(self, input: list[str] | str) -> list[list[float]] | list[float]:
        if isinstance(input, str):
            return self._embed(input)
        return self(input)

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return self(input)

    @staticmethod
    def name() -> str:
        return "wild_hash_fallback"

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> "HashEmbeddingFunction":
        return HashEmbeddingFunction(dimension=int(config.get("dimension", 256)))

    def get_config(self) -> dict[str, Any]:
        return {"dimension": self.dimension}

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = self._tokens(text)
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            raw = int.from_bytes(digest, "big")
            index = raw % self.dimension
            sign = 1.0 if ((raw >> 8) & 1) else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            return vector
        return [v / norm for v in vector]

    def _tokens(self, text: str) -> list[str]:
        normalized = re.sub(r"\s+", "", text.lower())
        tokens = list(normalized)
        tokens.extend(normalized[i:i + 2] for i in range(max(0, len(normalized) - 1)))
        words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*|\d+(?:\.\d+)?", text)
        tokens.extend(word.lower() for word in words)
        return tokens


class OpenAICompatibleEmbeddingFunction:
    """OpenAI Compatible embedding function for Chroma."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str,
        batch_size: int = 10,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name
        self.batch_size = max(1, min(batch_size, 10))
        self._client: Any | None = None

    def __call__(self, input: list[str]) -> list[list[float]]:
        if not input:
            return []

        embeddings: list[list[float]] = []
        for start in range(0, len(input), self.batch_size):
            embeddings.extend(self._embed_batch(input[start:start + self.batch_size]))
        return embeddings

    def _embed_batch(self, input: list[str]) -> list[list[float]]:
        client = self._get_client()
        response = client.embeddings.create(model=self.model_name, input=input)
        sorted_data = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in sorted_data]

    def _get_client(self):
        if self._client is not None:
            return self._client

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("缺少 openai 依赖，请先安装 wild-server 依赖") from exc

        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url or None)
        return self._client

    def embed_query(self, input: list[str] | str) -> list[list[float]] | list[float]:
        if isinstance(input, str):
            return self([input])[0]
        return self(input)

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return self(input)

    @staticmethod
    def name() -> str:
        return "wild_openai_compatible"

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> "OpenAICompatibleEmbeddingFunction":
        return OpenAICompatibleEmbeddingFunction(
            api_key=str(config.get("api_key", "")),
            base_url=str(config.get("base_url", "")),
            model_name=str(config.get("model_name", "")),
            batch_size=int(config.get("batch_size", 10)),
        )

    def get_config(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "model_name": self.model_name,
            "batch_size": self.batch_size,
            "api_key": "",
        }


class MarkdownChunker:
    """面向规范文档的 Markdown 分片器。

    使用 LangChain 官方 splitter 做两阶段切分：
      1. MarkdownHeaderTextSplitter 按标题结构拆分并保留标题元数据
      2. RecursiveCharacterTextSplitter 对超长 section 做二次长度切分

    WildAgent 只保留业务层补充：小片段合并和 Chroma metadata 规范化。
    """

    def __init__(self, chunk_size: int = 900, chunk_overlap: int = 150):
        self.chunk_size = max(200, chunk_size)
        self.chunk_overlap = max(0, min(chunk_overlap, self.chunk_size // 2))
        try:
            from langchain_text_splitters import (
                MarkdownHeaderTextSplitter,
                RecursiveCharacterTextSplitter,
            )
        except ImportError as exc:
            raise RuntimeError(
                "缺少 langchain-text-splitters 依赖，请先安装 wild-server 依赖"
            ) from exc

        self._markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "h1"),
                ("##", "h2"),
                ("###", "h3"),
            ],
            strip_headers=False,
        )
        self._text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            is_separator_regex=False,
        )

    def split_file(
        self,
        path: Path,
        namespace: str,
        doc_scope: str = "system",
    ) -> list[SpecChunk]:
        if not path.exists():
            return []

        text = path.read_text(encoding="utf-8")
        documents = self._markdown_splitter.split_text(text)
        documents = self._text_splitter.split_documents(documents)
        documents = self._merge_small_chunks(documents, min_size=300)

        chunks: list[SpecChunk] = []
        mtime = path.stat().st_mtime
        source_path = path.resolve().as_posix()
        source_hash = hashlib.sha256(f"{namespace}:{source_path}".encode("utf-8")).hexdigest()[:12]

        for chunk_index, document in enumerate(documents):
            content = document.page_content.strip()
            if not content:
                continue
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
            chunk_id = f"{namespace}:{source_hash}:{chunk_index}:{content_hash}"
            chunks.append(SpecChunk(
                id=chunk_id,
                document=content,
                metadata={
                    "namespace": namespace,
                    "doc_scope": doc_scope,
                    "doc_type": self._infer_doc_type(path),
                    "source": path.name,
                    "path": source_path,
                    "_source": source_path,
                    "_extension": path.suffix.lower(),
                    "_file_name": path.name,
                    "heading": self._heading_from_metadata(document.metadata, path.stem),
                    "chunk_index": chunk_index,
                    "content_hash": content_hash,
                    "mtime": mtime,
                },
            ))

        return chunks

    def _infer_doc_type(self, path: Path) -> str:
        name = path.name.upper()
        if "BUILDING-TYPES" in name:
            return "building_reference"
        if "SPEC" in name:
            return "blueprint_spec"
        return "knowledge"

    def _heading_from_metadata(self, metadata: dict[str, Any], default_heading: str) -> str:
        headings = [
            str(metadata[key])
            for key in ("h1", "h2", "h3")
            if metadata.get(key)
        ]
        return " > ".join(headings) if headings else default_heading

    def _merge_small_chunks(self, documents: list[Any], min_size: int = 300) -> list[Any]:
        if not documents:
            return []

        merged: list[Any] = []
        current = documents[0]

        for document in documents[1:]:
            current_size = len(current.page_content)
            document_size = len(document.page_content)
            same_heading = current.metadata == document.metadata
            merged_size = current_size + 2 + document_size

            if document_size < min_size and same_heading and merged_size <= self.chunk_size:
                current.page_content = f"{current.page_content}\n\n{document.page_content}"
            else:
                merged.append(current)
                current = document

        merged.append(current)
        return merged


class RAGSpecLoader(SpecLoader):
    """基于 Chroma 的规范文档检索加载器。"""

    def __init__(
        self,
        base_paths: list[str],
        rag_paths: list[str],
        persist_dir: str,
        collection_name: str,
        embedding_function: Any,
        top_k: int = 6,
        chunk_size: int = 900,
        chunk_overlap: int = 150,
        max_context_chars: int = 18000,
        namespace: str = "wild_spec",
        auto_sync: bool = True,
    ):
        self._base_paths = [Path(p) for p in base_paths]
        self._rag_paths = [Path(p) for p in rag_paths]
        self._persist_dir = Path(persist_dir)
        self._collection_name = collection_name
        self._embedding_function = embedding_function
        self._top_k = max(1, top_k)
        self._max_context_chars = max(4000, max_context_chars)
        self._namespace = namespace
        self._chunker = MarkdownChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self._loaded_at: float | None = None
        self._last_results: list[RetrievedSpecChunk] = []
        self._client: Any | None = None
        self._collection: Any | None = None

        if auto_sync:
            self.sync_index()

    def load(self, query: str = "") -> str:
        base_text = self._load_base_text()
        retrieved = self.retrieve(query) if query.strip() else []
        rag_text = self._format_retrieved(retrieved)
        self._loaded_at = time.time()

        if not rag_text:
            return base_text

        spec_text = f"{base_text}\n\n---\n\n{rag_text}"
        if len(spec_text) <= self._max_context_chars:
            return spec_text

        allowed_rag_chars = max(0, self._max_context_chars - len(base_text) - 16)
        return f"{base_text}\n\n---\n\n{rag_text[:allowed_rag_chars]}\n\n<!-- RAG 上下文已按长度上限截断 -->"

    def list_sources(self) -> list[str]:
        return [str(p) for p in [*self._base_paths, *self._rag_paths]]

    @property
    def loaded_at(self) -> float | None:
        return self._loaded_at

    @property
    def last_results(self) -> list[RetrievedSpecChunk]:
        return self._last_results

    def sync_index(self) -> int:
        """重建当前 namespace 的 Chroma 索引，返回写入 chunk 数。"""
        collection = self._get_collection()
        chunks = self._build_chunks()

        try:
            collection.delete(where={"namespace": self._namespace})
        except Exception:
            # 空 collection 或不同 Chroma 版本的 delete 行为不应阻断重建。
            pass

        batch_size = 10
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start:start + batch_size]
            collection.upsert(
                ids=[chunk.id for chunk in batch],
                documents=[chunk.document for chunk in batch],
                metadatas=[chunk.metadata for chunk in batch],
            )

        return len(chunks)

    def retrieve(self, query: str) -> list[RetrievedSpecChunk]:
        collection = self._get_collection()
        count = collection.count()
        if count == 0:
            self._last_results = []
            return []

        n_results = min(self._top_k * 2, count)
        result = collection.query(
            query_texts=[query],
            n_results=n_results,
            where={"namespace": self._namespace},
            include=["documents", "metadatas", "distances"],
        )

        documents = result.get("documents", [[]])[0] or []
        metadatas = result.get("metadatas", [[]])[0] or []
        distances = result.get("distances", [[]])[0] or []
        retrieved: list[RetrievedSpecChunk] = []
        seen_hashes: set[str] = set()

        for index, document in enumerate(documents):
            metadata = metadatas[index] if index < len(metadatas) and metadatas[index] else {}
            content_hash = str(metadata.get("content_hash") or hashlib.sha256((document or "").encode("utf-8")).hexdigest()[:16])
            if content_hash in seen_hashes:
                continue
            seen_hashes.add(content_hash)
            retrieved.append(RetrievedSpecChunk(
                document=document or "",
                metadata=metadata,
                distance=distances[index] if index < len(distances) else None,
            ))
            if len(retrieved) >= self._top_k:
                break

        self._last_results = retrieved
        return retrieved

    def _get_collection(self):
        if self._collection is not None:
            return self._collection

        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError("缺少 chromadb 依赖，请先安装 wild-server 依赖") from exc

        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self._persist_dir))
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={
                "project": "WildAgent",
                "namespace": self._namespace,
                "version": "1",
            },
            embedding_function=self._embedding_function,
        )
        return self._collection

    def _load_base_text(self) -> str:
        return FileSpecLoader([str(p) for p in self._base_paths]).load()

    def _build_chunks(self) -> list[SpecChunk]:
        chunks: list[SpecChunk] = []
        for path in self._rag_paths:
            chunks.extend(self._chunker.split_file(
                path,
                namespace=self._namespace,
                doc_scope="system",
            ))
        return chunks

    def _format_retrieved(self, chunks: list[RetrievedSpecChunk]) -> str:
        if not chunks:
            return ""

        parts = ["## RAG 检索到的相关规范片段"]
        for index, chunk in enumerate(chunks, start=1):
            source = chunk.metadata.get("source", "unknown")
            heading = chunk.metadata.get("heading", "")
            distance = chunk.distance
            distance_text = f", distance={distance:.4f}" if isinstance(distance, float) else ""
            parts.append(
                f"### 片段 {index}: {source} / {heading}{distance_text}\n\n"
                f"{chunk.document}"
            )
        return "\n\n".join(parts)


def create_embedding_function(
    api_key: str,
    base_url: str,
    model_name: str,
    allow_hash_fallback: bool = True,
):
    """根据配置创建 Chroma embedding function。"""
    if api_key and model_name:
        return OpenAICompatibleEmbeddingFunction(
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            batch_size=10,
        )

    if allow_hash_fallback:
        return HashEmbeddingFunction()

    raise RuntimeError(
        "RAG 已启用，但缺少 EMBEDDING__API_KEY 或 EMBEDDING__NAME，且未允许 hash fallback"
    )
