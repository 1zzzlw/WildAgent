"""
Spec Document Loader —— 规范文档加载器

职责：加载 WILD 语言规范文档，注入到 LLM System Prompt 中。

设计原则：
  - 调用方只依赖 load() 和 list_sources()
  - FileSpecLoader 保留为确定性兜底
  - RAGSpecLoader 使用 Chroma 对完整知识库做语义检索

主数据流：
  Markdown 路径扫描 → 标题/业务实体分块 → 受限长度兜底 → Chroma 增量同步
  → 向量召回 → 按精确内容哈希去重 → 与基础规范拼接。

这里的“去重”仅发生在检索结果中；不同文件里的相同片段仍可同时存在于索引。
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from loguru import logger

from app.agent.rag_gate import (
    RAGRetrievalRejected,
    evaluate_retrieval_gate,
)
from app.agent.rag_security import split_business_and_access_filters
from app.agent.rag_trace import (
    make_query_trace,
    record_rag_context,
    record_rag_gate,
    record_rag_retrieval,
)
from config import config


def _normalize_path(path: Path) -> str:
    """生成用于路径比较的绝对、大小写不敏感字符串。"""
    try:
        # resolve() 同时消解 ``..`` 和符号链接，避免同一路径有多种写法。
        return str(path.resolve()).casefold()
    except OSError:
        # 文件暂时无法解析时仍返回可比较的绝对路径，不中断知识库扫描。
        return str(path.absolute()).casefold()


def collect_markdown_paths(root: str | Path, exclude: list[str | Path] | None = None) -> list[Path]:
    """递归收集知识库 Markdown 文件，用于 RAG 建索引。"""
    root_path = Path(root)
    if not root_path.exists():
        return []

    # exclude 是“精确路径排除”而不是内容去重，当前用于排除直接注入的最小规范。
    excluded = {_normalize_path(Path(path)) for path in (exclude or [])}
    paths = [
        path
        for path in root_path.rglob("*.md")
        if path.is_file() and _normalize_path(path) not in excluded
    ]
    # 固定排序让同一知识库每次都按相同文件顺序分片，便于复现和测试。
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
        # 在构造时转成 Path，后续读文件和列出来源使用同一组对象。
        self._paths = [Path(p) for p in paths]
        self._loaded_at: float | None = None

    def load(self, query: str = "") -> str:
        """读取所有文件并拼接；query 参数用于兼容 RAGSpecLoader。"""
        texts: list[str] = []
        for p in self._paths:
            if p.exists():
                text = p.read_text(encoding="utf-8")
                # 文件名作为二级标题，便于 LLM 区分拼接后的规范来源。
                texts.append(f"## {p.stem}\n\n{text}")
            else:
                # 缺失文件作为显式警告写进上下文，而不是静默丢失基础规范。
                texts.append(
                    f"<!-- 警告：规范文档不存在: {p} -->\n"
                    f"## {p.stem}\n\n（文件缺失，请检查路径配置）"
                )
        self._loaded_at = time.time()
        # Markdown 分隔线防止相邻文件的标题层级意外粘连。
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
    # Chroma 的真实分片 ID，用于日志追踪和后续引用闭环。
    id: str | None = None


@dataclass(frozen=True)
class SpecQuery:
    """一次带可选业务 metadata 过滤条件的 RAG 查询。"""

    text: str
    metadata_filter: dict[str, Any] | None = None


def _retrieval_priority_score(
    distance: float | None,
    metadata: dict[str, Any],
) -> float:
    """在语义距离上施加有限的知识成熟度惩罚，不让实验片段轻易挤掉规范片段。"""
    status_penalty = {
        "supported": 0.0,
        "experimental": 0.06,
        "proposed": 0.12,
        "deprecated": 0.18,
    }.get(str(metadata.get("status") or "").lower(), 0.04)
    authority_penalty = {
        "schema": 0.0,
        "engine": 0.0,
        "verified": 0.005,
        "maintainer": 0.01,
        "domain": 0.025,
        "imported": 0.04,
        "inferred": 0.10,
    }.get(str(metadata.get("authority") or "").lower(), 0.03)
    semantic_distance = float(distance) if isinstance(distance, (int, float)) else 999.0
    return semantic_distance + status_penalty + authority_penalty


class HashEmbeddingFunction:
    """开发环境兜底 embedding。

    只用于缺少 EMBEDDING API 配置时的本地 smoke test。它基于字符和二元片段做
    hash 向量化，能处理关键词重合，但不能替代真实语义 embedding。
    """

    def __init__(self, dimension: int = 256):
        # 较小维度只为本地测试换取速度和零外部依赖，不追求真实语义质量。
        self.dimension = dimension

    def __call__(self, input: list[str]) -> list[list[float]]:
        # Chroma 的 embedding function 协议要求批量输入、批量输出。
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
            # 稳定哈希把 token 投影到固定维度，并用一位哈希值决定正负方向。
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            raw = int.from_bytes(digest, "big")
            index = raw % self.dimension
            sign = 1.0 if ((raw >> 8) & 1) else -1.0
            vector[index] += sign

        # 单位化后可以用向量距离比较关键词重合程度。
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            return vector
        return [v / norm for v in vector]

    def _tokens(self, text: str) -> list[str]:
        # 字符和二元字符片段兼顾中文；单词正则补充英文标识符与数值。
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
        # 上游兼容服务可能限制单批数量，因此即使配置更大也收敛到 10。
        self.batch_size = max(1, min(batch_size, 10))
        # 延迟创建客户端，使配置与索引对象初始化时不立即发起外部连接。
        self._client: Any | None = None

    def __call__(self, input: list[str]) -> list[list[float]]:
        if not input:
            return []

        embeddings: list[list[float]] = []
        for start in range(0, len(input), self.batch_size):
            # 分批调用既遵守服务限制，也避免一次请求携带过多文本。
            embeddings.extend(self._embed_batch(input[start:start + self.batch_size]))
        return embeddings

    def _embed_batch(self, input: list[str]) -> list[list[float]]:
        client = self._get_client()
        response = client.embeddings.create(model=self.model_name, input=input)
        # 部分兼容服务不保证 data 顺序，按响应 index 恢复成输入顺序。
        sorted_data = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in sorted_data]

    def _get_client(self):
        if self._client is not None:
            return self._client

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("缺少 openai 依赖，请先安装 wild-server 依赖") from exc

        # base_url 为空时传 None，让 OpenAI 客户端使用默认服务地址。
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
        # 索引签名需要模型配置，但绝不能把 API key 持久化进 Chroma metadata。
        return {
            "base_url": self.base_url,
            "model_name": self.model_name,
            "batch_size": self.batch_size,
            "api_key": "",
        }


class MarkdownChunker:
    """按标题和业务实体分块，并只对普通长文本执行长度兜底。"""

    _DOCUMENT_METADATA_FIELDS = (
        "doc_type",
        "doc_scope",
        "knowledge_layer",
        "entity_type",
        "entity_name",
        "topic",
        "wild_version",
        "status",
        "authority",
        "primary_terms",
        "synonyms",
        # 兼容尚未迁移的外部文档；正式知识库不再写 legacy keywords。
        "keywords",
    )
    _HEADING_PATTERN = re.compile(r"^(#{1,5})\s+(.+?)\s*#*\s*$")
    _FENCE_PATTERN = re.compile(r"^\s*(```+|~~~+)")
    _TABLE_ROW_PATTERN = re.compile(r"^\s*\|.*\|\s*$")
    _TABLE_SEPARATOR_PATTERN = re.compile(
        r"^\s*\|(?:\s*:?-{3,}:?\s*\|)+\s*$"
    )

    def __init__(
        self,
        chunk_size: int = 900,
        chunk_overlap: int = 150,
        metadata_config_path: str | Path | None = None,
    ):
        self.chunk_size = max(200, chunk_size)
        # overlap 最多为分片长度的一半，避免相邻分片几乎完全重复。
        self.chunk_overlap = max(0, min(chunk_overlap, self.chunk_size // 2))
        self._metadata_config_path = (
            Path(metadata_config_path) if metadata_config_path is not None else None
        )
        self._metadata_config: dict[str, Any] | None = None
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
            # 标题内容会保留在 page_content 中，同时标题值写入 metadata。
            headers_to_split_on=[
                ("#", "h1"),
                ("##", "h2"),
                ("###", "h3"),
                ("####", "h4"),
                ("#####", "h5"),
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
        doc_scope: str = "generation",
    ) -> list[SpecChunk]:
        if not path.exists():
            return []

        text = path.read_text(encoding="utf-8")
        frontmatter, body = self._extract_frontmatter(text)
        body, entity_metadata = self._extract_entity_metadata(body)
        # 第一阶段只按标题边界切分，不在不同标题或业务实体之间合并。
        documents = self._markdown_splitter.split_text(body)
        inferred_metadata = self._infer_document_metadata(path, doc_scope)
        # 配置只提供路径级默认值；文档 frontmatter 始终拥有最高优先级。
        inferred_metadata.update(self._path_rule_metadata(path))
        declared_source = frontmatter.get("source")
        for field in self._DOCUMENT_METADATA_FIELDS:
            if field in frontmatter:
                inferred_metadata[field] = frontmatter[field]
        self._normalize_term_metadata(inferred_metadata)

        chunks: list[SpecChunk] = []
        # mtime 仅供追踪来源状态，不参与分片 ID 或判重。
        # Chroma 会把浮点 metadata 归一化到约 6 位小数；预先对齐可避免每次启动
        # 都把仅有亚微秒差异的 mtime 误判为 metadata 变化。
        mtime = round(path.stat().st_mtime, 6)
        source_path = path.resolve().as_posix()
        # source_hash 区分不同文件；相同内容位于不同文件时仍会拥有不同 ID。
        source_hash = hashlib.sha256(f"{namespace}:{source_path}".encode("utf-8")).hexdigest()[:12]

        chunk_index = 0
        for section_index, document in enumerate(documents):
            heading_path = self._heading_path(document.metadata)
            heading = " > ".join(heading_path) if heading_path else path.stem
            section_metadata = dict(inferred_metadata)
            # 实体 metadata 按标题层级继承；更深层标题上的声明覆盖祖先声明。
            for depth in range(1, len(heading_path) + 1):
                section_metadata.update(entity_metadata.get(heading_path[:depth], {}))
            self._normalize_term_metadata(section_metadata)

            context_line = f"> 知识路径：{heading}"
            section_parts = [
                part
                for part in self._split_section(document.page_content, context_line)
                if self._has_meaningful_payload(part)
            ]
            parent_digest = hashlib.sha256(
                f"{namespace}:{source_path}:{section_index}:{heading}".encode("utf-8")
            ).hexdigest()[:16]
            parent_chunk_id = f"{namespace}:{source_hash}:section:{parent_digest}"

            for part_index, part in enumerate(section_parts):
                # 每个长度子片都重复标题路径，让脱离相邻片段后仍有完整语义上下文。
                content = f"{context_line}\n\n{part.strip()}".strip()
                if not content:
                    continue
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
                # body_hash 忽略祖先标题路径，但保留当前标题，识别跨文件重复业务正文。
                body_hash_source = self._body_hash_source(part, heading_path)
                body_hash = hashlib.sha256(body_hash_source.encode("utf-8")).hexdigest()[:16]
                chunk_id = f"{parent_chunk_id}:{part_index}:{content_hash}"
                metadata: dict[str, str | int | float | bool] = {
                    "namespace": namespace,
                    "source": path.name,
                    "source_file": path.name,
                    "path": source_path,
                    "_source": source_path,
                    "_extension": path.suffix.lower(),
                    "_file_name": path.name,
                    "heading": heading,
                    "heading_path": " > ".join(heading_path),
                    "parent_chunk_id": parent_chunk_id,
                    "part_index": part_index,
                    "chunk_index": chunk_index,
                    "content_hash": content_hash,
                    "body_hash": body_hash,
                    "mtime": mtime,
                }
                if declared_source:
                    metadata["declared_source"] = self._metadata_scalar(declared_source)
                for key, value in section_metadata.items():
                    metadata[key] = self._metadata_scalar(value)
                chunks.append(SpecChunk(id=chunk_id, document=content, metadata=metadata))
                chunk_index += 1

        return chunks

    def _extract_frontmatter(self, text: str) -> tuple[dict[str, Any], str]:
        """提取文件级 YAML 子集；不引入额外 YAML 运行时依赖。"""
        match = re.match(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", text, re.DOTALL)
        if not match:
            return {}, text
        return self._parse_metadata_lines(match.group(1).splitlines()), text[match.end():]

    def _extract_entity_metadata(
        self,
        text: str,
    ) -> tuple[str, dict[tuple[str, ...], dict[str, Any]]]:
        """移除 ``rag-meta`` 注释，并把它绑定到出现位置的标题路径。"""
        output: list[str] = []
        metadata_by_heading: dict[tuple[str, ...], dict[str, Any]] = {}
        heading_stack: list[str] = []
        lines = text.splitlines()
        index = 0
        active_fence: str | None = None

        while index < len(lines):
            line = lines[index]
            fence_match = self._FENCE_PATTERN.match(line)
            if fence_match:
                fence_char = fence_match.group(1)[0]
                if active_fence is None:
                    active_fence = fence_char
                elif fence_char == active_fence:
                    active_fence = None
                output.append(line)
                index += 1
                continue
            if active_fence is not None:
                output.append(line)
                index += 1
                continue

            heading_match = self._HEADING_PATTERN.match(line)
            if heading_match:
                level = len(heading_match.group(1))
                heading_stack = heading_stack[:level - 1]
                heading_stack.append(heading_match.group(2).strip())
                output.append(line)
                index += 1
                continue

            if line.strip().startswith("<!-- rag-meta"):
                metadata_lines: list[str] = []
                # 允许起始标记同行存在字段，也兼容规范模板中的独占一行写法。
                first_line = line.split("<!-- rag-meta", 1)[1]
                if "-->" in first_line:
                    metadata_lines.append(first_line.split("-->", 1)[0])
                    index += 1
                else:
                    if first_line.strip():
                        metadata_lines.append(first_line)
                    index += 1
                    while index < len(lines) and "-->" not in lines[index]:
                        metadata_lines.append(lines[index])
                        index += 1
                    if index < len(lines):
                        metadata_lines.append(lines[index].split("-->", 1)[0])
                        index += 1
                key = tuple(heading_stack)
                metadata_by_heading.setdefault(key, {}).update(
                    self._parse_metadata_lines(metadata_lines)
                )
                continue

            output.append(line)
            index += 1

        return "\n".join(output), metadata_by_heading

    def _parse_metadata_lines(self, lines: list[str]) -> dict[str, Any]:
        """解析 Skill 约定的扁平 ``key: value`` 和列表语法。"""
        result: dict[str, Any] = {}
        active_list_key: str | None = None
        for raw_line in lines:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("- ") and active_list_key:
                result.setdefault(active_list_key, []).append(
                    self._parse_metadata_scalar(stripped[2:])
                )
                continue
            if ":" not in stripped:
                active_list_key = None
                continue
            key, raw_value = stripped.split(":", 1)
            key = key.strip()
            raw_value = raw_value.strip()
            if not key:
                continue
            if not raw_value:
                result[key] = []
                active_list_key = key
            else:
                result[key] = self._parse_metadata_scalar(raw_value)
                active_list_key = None
        return result

    def _parse_metadata_scalar(self, value: str) -> Any:
        value = value.strip()
        if value == "[]":
            return []
        if value.startswith("[") and value.endswith("]"):
            return [
                item.strip().strip("'\"")
                for item in value[1:-1].split(",")
                if item.strip()
            ]
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        lowered = value.casefold()
        if lowered in {"true", "false"}:
            return lowered == "true"
        if "," in value:
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    def _normalize_term_metadata(self, metadata: dict[str, Any]) -> None:
        """把 legacy keywords 暴露为新字段，供旧的外部文档平滑迁移。"""
        if "keywords" not in metadata:
            return
        if "primary_terms" not in metadata and "synonyms" not in metadata:
            metadata["primary_terms"] = metadata["keywords"]
            metadata["synonyms"] = []

    def _path_rule_metadata(self, path: Path) -> dict[str, Any]:
        """按 config.yaml 合并 defaults 和命中的 mapping_rules。"""
        config_path = self._resolve_metadata_config_path(path)
        if config_path is None:
            return {}
        if self._metadata_config is None:
            try:
                import yaml

                loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
                self._metadata_config = loaded if isinstance(loaded, dict) else {}
            except Exception as exc:
                logger.warning(f"[RAG] 无法读取知识库 metadata 配置 {config_path}: {exc}")
                self._metadata_config = {}

        config = self._metadata_config
        defaults = config.get("defaults", {})
        resolved = dict(defaults) if isinstance(defaults, dict) else {}
        try:
            relative_path = path.resolve().relative_to(config_path.parent.resolve()).as_posix()
        except ValueError:
            return resolved

        rules = config.get("mapping_rules", [])
        if not isinstance(rules, list):
            logger.warning(f"[RAG] {config_path} 的 mapping_rules 必须是列表")
            return resolved
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            pattern = str(rule.get("path_pattern") or "").strip()
            rule_metadata = rule.get("metadata", {})
            if (
                pattern
                and isinstance(rule_metadata, dict)
                and PurePosixPath(relative_path).match(pattern)
            ):
                resolved.update(rule_metadata)
        return resolved

    def _resolve_metadata_config_path(self, path: Path) -> Path | None:
        if self._metadata_config_path is not None:
            return self._metadata_config_path if self._metadata_config_path.is_file() else None
        # 直接使用 MarkdownChunker 的脚本也能自动发现最近的知识库配置。
        for parent in path.resolve().parents:
            candidate = parent / "config.yaml"
            if candidate.is_file():
                self._metadata_config_path = candidate
                return candidate
        return None

    def _infer_document_metadata(self, path: Path, doc_scope: str) -> dict[str, Any]:
        """为旧文档提供可过滤的最小 metadata，新文档可用 frontmatter 覆盖。"""
        path_text = path.as_posix().casefold()
        stem = path.stem.casefold().replace("_", "-")
        metadata: dict[str, Any] = {
            "doc_type": "knowledge",
            "doc_scope": doc_scope,
            "knowledge_layer": "generation",
            "entity_type": "general",
            "entity_name": path.stem,
            "topic": "general",
        }
        if path.name.casefold() == "readme.md":
            metadata.update({
                "doc_type": "index",
                "doc_scope": "index",
                "knowledge_layer": "navigation",
                "entity_type": "index",
                "topic": "navigation",
            })
            return metadata
        if "building_types" in path_text or "building-types" in path_text:
            metadata.update({"doc_type": "building_type", "entity_type": "building"})
            # 根据目录路径推断 building_category
            if "residential" in path_text:
                metadata["building_category"] = "residential"
            elif "public" in path_text:
                # public 目录下需要进一步判断
                if any(keyword in stem for keyword in ["commercial", "shopping", "retail", "商业", "商场", "商铺"]):
                    metadata["building_category"] = "commercial"
                else:
                    metadata["building_category"] = "public"
            elif "industrial" in path_text:
                metadata["building_category"] = "industrial"
            elif "agricultural" in path_text:
                metadata["building_category"] = "agricultural"
        elif "recipes" in path_text:
            metadata.update({"doc_type": "recipe", "entity_type": "assembly"})
        elif "patterns" in path_text:
            metadata.update({"doc_type": "pattern", "entity_type": "pattern"})
        elif "components" in path_text:
            metadata["doc_type"] = "component"
        elif "spec" in stem:
            metadata.update({
                "doc_type": "blueprint_spec",
                "knowledge_layer": "wild_schema",
                "entity_type": "schema",
            })

        entity_aliases = {
            "window": ("window", "windows", "窗"),
            "door": ("door", "doors", "门"),
            "wall": ("wall", "walls", "墙"),
            "roof": ("roof", "roofs", "屋顶"),
            "stair": ("stair", "stairs", "楼梯"),
            "railing": ("railing", "railings", "栏杆"),
            "opening": ("opening", "openings", "洞口"),
            "material": ("material", "materials", "材质"),
        }
        filename = path.name.casefold()
        for entity_type, aliases in entity_aliases.items():
            if any(alias in filename for alias in aliases):
                metadata["entity_type"] = entity_type
                break
        return metadata

    def _heading_path(self, metadata: dict[str, Any]) -> tuple[str, ...]:
        return tuple(
            str(metadata[key])
            for key in ("h1", "h2", "h3", "h4", "h5")
            if metadata.get(key)
        )

    def _split_section(self, text: str, context_line: str) -> list[str]:
        """把标题 section 拆成 Markdown 逻辑块，再进行受限的长度兜底。"""
        budget = max(80, self.chunk_size - len(context_line) - 2)
        logical_blocks = self._markdown_blocks(text.strip())
        parts: list[str] = []
        current: list[str] = []

        def flush() -> None:
            if current:
                parts.append("\n\n".join(current).strip())
                current.clear()

        for block_type, block in logical_blocks:
            candidates = (
                self._split_table(block, budget)
                if block_type == "table"
                else [block]
                if block_type == "code"
                else self._split_normal_block(block, budget)
            )
            for candidate in candidates:
                # 超长代码块作为原子知识单元保留；由文档 linter 提示作者重构。
                if len(candidate) > budget:
                    flush()
                    parts.append(candidate.strip())
                    continue
                combined = "\n\n".join([*current, candidate]).strip()
                if current and len(combined) > budget:
                    flush()
                current.append(candidate.strip())
        flush()
        return [part for part in parts if part]

    def _has_meaningful_payload(self, text: str) -> bool:
        """过滤只有标题、空行或 Markdown 分隔线的目录壳 section。"""
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or self._HEADING_PATTERN.match(stripped):
                continue
            if re.fullmatch(r"(?:-{3,}|\*{3,}|_{3,})", stripped):
                continue
            return True
        return False

    def _body_hash_source(self, text: str, heading_path: tuple[str, ...]) -> str:
        payload_lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not self._HEADING_PATTERN.match(line.strip())
        ]
        current_heading = heading_path[-1] if heading_path else ""
        return f"{current_heading}\n{'\n'.join(payload_lines)}".strip()

    def _markdown_blocks(self, text: str) -> list[tuple[str, str]]:
        """识别 fenced code、表格和普通段落，保护结构化内容不被字符切断。"""
        if not text:
            return []
        lines = text.splitlines()
        blocks: list[tuple[str, str]] = []
        normal_lines: list[str] = []
        index = 0

        def flush_normal() -> None:
            if normal_lines:
                value = "\n".join(normal_lines).strip()
                if value:
                    blocks.append(("normal", value))
                normal_lines.clear()

        while index < len(lines):
            fence_match = self._FENCE_PATTERN.match(lines[index])
            if fence_match:
                flush_normal()
                fence = fence_match.group(1)
                code_lines = [lines[index]]
                index += 1
                while index < len(lines):
                    code_lines.append(lines[index])
                    if re.match(rf"^\s*{re.escape(fence[0])}{{{len(fence)},}}\s*$", lines[index]):
                        index += 1
                        break
                    index += 1
                blocks.append(("code", "\n".join(code_lines).strip()))
                continue

            if (
                index + 1 < len(lines)
                and self._TABLE_ROW_PATTERN.match(lines[index])
                and self._TABLE_SEPARATOR_PATTERN.match(lines[index + 1])
            ):
                flush_normal()
                table_lines = [lines[index], lines[index + 1]]
                index += 2
                while index < len(lines) and self._TABLE_ROW_PATTERN.match(lines[index]):
                    table_lines.append(lines[index])
                    index += 1
                blocks.append(("table", "\n".join(table_lines).strip()))
                continue

            if not lines[index].strip():
                flush_normal()
            else:
                normal_lines.append(lines[index])
            index += 1
        flush_normal()
        return blocks

    def _split_normal_block(self, block: str, budget: int) -> list[str]:
        if len(block) <= budget:
            return [block]
        splitter = self._text_splitter
        if budget != self.chunk_size:
            from langchain_text_splitters import RecursiveCharacterTextSplitter

            splitter = RecursiveCharacterTextSplitter(
                chunk_size=budget,
                chunk_overlap=min(self.chunk_overlap, budget // 2),
                length_function=len,
                is_separator_regex=False,
            )
        return [part for part in splitter.split_text(block) if part.strip()]

    def _split_table(self, table: str, budget: int) -> list[str]:
        lines = table.splitlines()
        if len(lines) < 3 or len(table) <= budget:
            return [table]
        header = lines[:2]
        parts: list[str] = []
        current = list(header)
        for row in lines[2:]:
            candidate = "\n".join([*current, row])
            if len(candidate) > budget and len(current) > 2:
                parts.append("\n".join(current))
                current = [*header, row]
            else:
                current.append(row)
        if len(current) > 2:
            parts.append("\n".join(current))
        return parts or [table]

    def _metadata_scalar(self, value: Any) -> str | int | float | bool:
        """Chroma metadata 只接受标量，列表统一存为逗号分隔字符串。"""
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)
        return json.dumps(value, ensure_ascii=False, sort_keys=True)


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
        # 保存最近一次检索和同步状态，供 AgentService 写诊断日志。
        self._last_results: list[RetrievedSpecChunk] = []
        self._last_sync_stats = {"total": 0, "updated": 0, "deleted": 0}
        self._client: Any | None = None
        self._collection: Any | None = None
        self._retrieval_cache: dict[str, list[RetrievedSpecChunk]] = {}

        if auto_sync:
            # 默认在 Loader 构造时同步一次，保证第一次查询即可命中新文档。
            self.sync_index()

    def load(self, query: str = "", *, purpose: str = "generation") -> str:
        # 基础规范始终完整注入；扩展知识只在有查询时按需召回。
        base_text = self._load_base_text()
        try:
            retrieved = self.retrieve(query) if query.strip() else []
            retrieved = self._apply_retrieval_gate(retrieved, purpose=purpose)
        except RAGRetrievalRejected:
            raise
        except Exception as exc:
            # Chroma 检索失败时降级为基础规范上下文，避免单个查询让整条链路崩溃。
            logger.warning(f"[RAG] 检索失败，已降级为基础规范上下文: {exc}")
            # observe 仍需记录“证据为空”的结论；enforce 下知识问答不能绕过
            # Gate 后继续让 LLM 根据基础规范猜答，建筑生成则照常降级。
            retrieved = self._apply_retrieval_gate([], purpose=purpose)
        return self._compose_context(base_text, retrieved, operation="load")

    # per_query 参数控制每个检索意图返回的片段数，避免建筑类型文档挤掉组件文档。
    def load_many(
        self,
        queries: list[str | SpecQuery],
        per_query: int = 1,
        *,
        purpose: str = "generation",
    ) -> str:
        """按多个检索意图各取片段，避免建筑类型文档挤掉组件文档。"""
        base_text = self._load_base_text()
        try:
            retrieved = self.retrieve_many(queries, per_query=per_query)
            retrieved = self._apply_retrieval_gate(retrieved, purpose=purpose)
        except RAGRetrievalRejected:
            raise
        except Exception as exc:
            logger.warning(f"[RAG] 检索失败，已降级为基础规范上下文: {exc}")
            retrieved = self._apply_retrieval_gate([], purpose=purpose)
        return self._compose_context(base_text, retrieved, operation="load_many")

    def _apply_retrieval_gate(
        self,
        retrieved: list[RetrievedSpecChunk],
        *,
        purpose: str,
    ) -> list[RetrievedSpecChunk]:
        gate = config.rag.retrieval_gate
        decision = evaluate_retrieval_gate(
            retrieved,
            mode=gate.mode,
            purpose=purpose,
            max_distance=gate.max_distance,
            min_hits=gate.min_hits,
        )
        record_rag_gate(decision.to_dict())
        if not decision.enforced:
            return retrieved
        if purpose == "chat":
            raise RAGRetrievalRejected(gate.refusal_message, decision)
        # 建筑生成不因可选知识不足而整体失败，只降级为基础规范。
        return []

    def _compose_context(
        self,
        base_text: str,
        retrieved: list[RetrievedSpecChunk],
        operation: str = "compose",
    ) -> str:
        rag_text = self._format_retrieved(retrieved)
        self._loaded_at = time.time()

        if not rag_text:
            context = base_text
            selected: list[RetrievedSpecChunk] = []
            self._record_composed_context(operation, base_text, selected, context)
            return context

        spec_text = f"{base_text}\n\n---\n\n{rag_text}"
        if len(spec_text) <= self._max_context_chars:
            self._record_composed_context(operation, base_text, retrieved, spec_text)
            return spec_text

        # 基础规范和单个 RAG chunk 都不可截断；按排名贪心选择能完整放入预算的片段。
        marker = "<!-- RAG 完整片段数量受上下文上限限制 -->"
        selected: list[RetrievedSpecChunk] = []
        for chunk in retrieved:
            candidate = self._format_retrieved([*selected, chunk])
            composed = f"{base_text}\n\n---\n\n{candidate}\n\n{marker}"
            if len(composed) <= self._max_context_chars:
                selected.append(chunk)

        if not selected:
            context = f"{base_text}\n\n{marker}"
            self._record_composed_context(operation, base_text, [], context)
            return context
        context = f"{base_text}\n\n---\n\n{self._format_retrieved(selected)}\n\n{marker}"
        self._record_composed_context(operation, base_text, selected, context)
        return context

    def _record_composed_context(
        self,
        operation: str,
        base_text: str,
        selected: list[RetrievedSpecChunk],
        context: str,
    ) -> None:
        record_rag_context(
            operation=operation,
            base_chars=len(base_text),
            retrieved_chars=sum(len(item.document) for item in selected),
            context_chars=len(context),
            retrieved_count=len(selected),
            injected_chunk_ids=[item.id for item in selected if item.id],
        )

    def list_sources(self) -> list[str]:
        return [str(p) for p in [*self._base_paths, *self._rag_paths]]

    @property
    def loaded_at(self) -> float | None:
        return self._loaded_at

    @property
    def last_results(self) -> list[RetrievedSpecChunk]:
        return self._last_results

    @property
    def last_sync_stats(self) -> dict[str, int]:
        return dict(self._last_sync_stats)

    def sync_index(self) -> int:
        """增量同步当前 namespace，返回本次新增或变化的 chunk 数。"""
        collection = self._get_collection()
        chunks = self._build_chunks()
        # 字典键保证同一次构建中相同 ID 只保留一个；ID 本身包含来源、序号和内容。
        chunks_by_id = {chunk.id: chunk for chunk in chunks}

        # 只读取当前 namespace，避免同步操作误删集合中的其他逻辑索引。
        existing = collection.get(
            where={"namespace": self._namespace},
            include=["metadatas"],
        )
        existing_id_list = existing.get("ids") or []
        existing_metadata_list = existing.get("metadatas") or []
        existing_ids = set(existing_id_list)
        existing_metadata_by_id = {
            chunk_id: (
                existing_metadata_list[index]
                if index < len(existing_metadata_list) and existing_metadata_list[index]
                else {}
            )
            for index, chunk_id in enumerate(existing_id_list)
        }
        current_ids = set(chunks_by_id)

        # 集合差得到两类最小变更：索引中多出的旧块，以及本地新出现的块。
        stale_ids = sorted(existing_ids - current_ids)
        pending_chunks = [
            chunks_by_id[chunk_id]
            for chunk_id in sorted(current_ids - existing_ids)
        ]
        # chunk ID 只由来源、位置和正文决定；分类 metadata 改变时无需重新 embedding。
        metadata_only_chunks = [
            chunks_by_id[chunk_id]
            for chunk_id in sorted(current_ids & existing_ids)
            if existing_metadata_by_id.get(chunk_id) != chunks_by_id[chunk_id].metadata
        ]

        batch_size = 10
        for start in range(0, len(stale_ids), batch_size):
            # 删除已移除文件、已改变内容或因重新分片而失效的旧 ID。
            collection.delete(ids=stale_ids[start:start + batch_size])

        for start in range(0, len(pending_chunks), batch_size):
            batch = pending_chunks[start:start + batch_size]
            # upsert 会调用 collection 的 embedding function 计算并持久化向量。
            collection.upsert(
                ids=[chunk.id for chunk in batch],
                documents=[chunk.document for chunk in batch],
                metadatas=[chunk.metadata for chunk in batch],
            )

        for start in range(0, len(metadata_only_chunks), batch_size):
            batch = metadata_only_chunks[start:start + batch_size]
            collection.update(
                ids=[chunk.id for chunk in batch],
                metadatas=[chunk.metadata for chunk in batch],
            )

        self._last_sync_stats = {
            "total": len(chunks),
            "updated": len(pending_chunks) + len(metadata_only_chunks),
            "deleted": len(stale_ids),
        }
        # 索引内容变化后使检索缓存失效，避免命中过期的召回结果。
        retrieval_cache = getattr(self, "_retrieval_cache", None)
        if retrieval_cache is not None:
            retrieval_cache.clear()
        
        return len(pending_chunks) + len(metadata_only_chunks)

    def retrieve(
        self,
        query: str,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[RetrievedSpecChunk]:
        """执行单意图检索，并把耗时、过滤条件和原始距离写入当前 RAGTrace。"""
        started = time.perf_counter()
        business_filter, _, ignored_access_keys = split_business_and_access_filters(
            metadata_filter
        )
        query_trace = make_query_trace(
            query,
            metadata_filter=business_filter,
            effective_filter=self._query_where(metadata_filter),
            index_signature=self._trace_index_signature(),
            ignored_access_filter_keys=ignored_access_keys,
        )
        try:
            retrieved = self._retrieve(query, metadata_filter=metadata_filter)
        except Exception as exc:
            record_rag_retrieval(
                operation="retrieve",
                queries=[query_trace],
                hits=[],
                elapsed_ms=round((time.perf_counter() - started) * 1000),
                error_type=type(exc).__name__,
            )
            raise
        record_rag_retrieval(
            operation="retrieve",
            queries=[query_trace],
            hits=retrieved,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
        )
        return retrieved

    def _retrieve(
        self,
        query: str,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[RetrievedSpecChunk]:
        collection = self._get_collection()
        count = collection.count()
        if count == 0:
            self._last_results = []
            return []

        # 多取一倍候选，为后面的精确内容去重留出补位空间。
        n_results = min(self._top_k * 2, count)
        result = collection.query(
            query_texts=[query],
            n_results=n_results,
            where=self._query_where(metadata_filter),
            include=["documents", "metadatas", "distances"],
        )

        documents = result.get("documents", [[]])[0] or []
        metadatas = result.get("metadatas", [[]])[0] or []
        distances = result.get("distances", [[]])[0] or []
        ids = result.get("ids", [[]])[0] or []
        retrieved: list[RetrievedSpecChunk] = []
        # 去重键不包含文件路径，因此相同内容来自不同文件时只返回排名最高的一份。
        seen_hashes: set[str] = set()

        ranked_indices = sorted(
            range(len(documents)),
            key=lambda index: _retrieval_priority_score(
                distances[index] if index < len(distances) else None,
                metadatas[index] if index < len(metadatas) and metadatas[index] else {},
            ),
        )
        for index in ranked_indices:
            document = documents[index]
            metadata = metadatas[index] if index < len(metadatas) and metadatas[index] else {}
            # 兼容旧索引：没有 content_hash metadata 时现场按同样规则补算。
            dedupe_hash = self._retrieval_hash(document or "", metadata)
            if dedupe_hash in seen_hashes:
                continue
            seen_hashes.add(dedupe_hash)
            retrieved.append(RetrievedSpecChunk(
                document=document or "",
                metadata=metadata,
                distance=distances[index] if index < len(distances) else None,
                id=str(ids[index]) if index < len(ids) else None,
            ))
            # 去重后达到 top_k 就停止；顺序已综合语义距离和知识成熟度。
            if len(retrieved) >= self._top_k:
                break

        retrieved = self._expand_parent_neighbors(collection, retrieved)
        self._last_results = retrieved
        return retrieved

    def retrieve_many(
        self,
        queries: list[str | SpecQuery],
        per_query: int = 1,
    ) -> list[RetrievedSpecChunk]:
        """执行多意图检索，并把每个意图和全部命中写入当前 RAGTrace。"""
        started = time.perf_counter()
        query_traces: list[dict[str, Any]] = []
        for query in queries:
            if isinstance(query, SpecQuery):
                text = query.text.strip()
                metadata_filter = query.metadata_filter
            else:
                text = query.strip()
                metadata_filter = None
            if text:
                business_filter, _, ignored_access_keys = (
                    split_business_and_access_filters(metadata_filter)
                )
                query_traces.append(make_query_trace(
                    text,
                    metadata_filter=business_filter,
                    effective_filter=self._query_where(metadata_filter),
                    index_signature=self._trace_index_signature(),
                    ignored_access_filter_keys=ignored_access_keys,
                ))
        try:
            retrieved = self._retrieve_many(queries, per_query=per_query)
        except Exception as exc:
            record_rag_retrieval(
                operation="retrieve_many",
                queries=query_traces,
                hits=[],
                elapsed_ms=round((time.perf_counter() - started) * 1000),
                error_type=type(exc).__name__,
            )
            raise
        record_rag_retrieval(
            operation="retrieve_many",
            queries=query_traces,
            hits=retrieved,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
        )
        return retrieved

    def _trace_index_signature(self) -> str | None:
        """测试假 Loader 可能没有完整 embedding/chunker；观测字段缺失不能影响检索。"""
        try:
            return self._index_signature()
        except (AttributeError, TypeError, ValueError):
            return None

    def _retrieve_many(
        self,
        queries: list[str | SpecQuery],
        per_query: int = 1,
    ) -> list[RetrievedSpecChunk]:
        """批量检索多个意图，每个意图保留固定数量并全局去重。"""
        normalized_queries: list[tuple[str, dict[str, Any] | None]] = []
        for query in queries:
            if isinstance(query, SpecQuery):
                text = query.text.strip()
                metadata_filter = query.metadata_filter
            else:
                text = query.strip()
                metadata_filter = None
            if text:
                normalized_queries.append((text, metadata_filter))

        if not normalized_queries:
            self._last_results = []
            return []

        cache_key = None
        retrieval_cache = getattr(self, "_retrieval_cache", None)
        if retrieval_cache is not None:
            cache_key = self._retrieval_cache_key(normalized_queries, per_query)
            if cache_key in retrieval_cache:
                self._last_results = list(retrieval_cache[cache_key])
                return self._last_results

        collection = self._get_collection()
        count = collection.count()
        if count == 0:
            self._last_results = []
            return []

        limit = max(1, per_query)
        # 每个意图也多取候选，避免第一个结果已被其他意图选中过后无内容可补。
        n_results = min(max(limit * 2, 2), count)
        # Chroma 一次 query 调用只能使用一组 where；相同过滤条件的查询仍批量执行。
        grouped_queries: dict[str, dict[str, Any]] = {}
        for query_index, (text, metadata_filter) in enumerate(normalized_queries):
            group_key = json.dumps(
                metadata_filter or {},
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
            group = grouped_queries.setdefault(
                group_key,
                {"filter": metadata_filter, "items": []},
            )
            group["items"].append((query_index, text))

        raw_results: dict[
            int,
            tuple[list[Any], list[Any], list[Any], list[Any]],
        ] = {}
        for group in grouped_queries.values():
            items = group["items"]
            result = collection.query(
                query_texts=[text for _, text in items],
                n_results=n_results,
                where=self._query_where(group["filter"]),
                include=["documents", "metadatas", "distances"],
            )
            document_groups = result.get("documents", []) or []
            metadata_groups = result.get("metadatas", []) or []
            distance_groups = result.get("distances", []) or []
            id_groups = result.get("ids", []) or []
            for group_index, (query_index, _) in enumerate(items):
                raw_results[query_index] = (
                    document_groups[group_index] if group_index < len(document_groups) else [],
                    metadata_groups[group_index] if group_index < len(metadata_groups) else [],
                    distance_groups[group_index] if group_index < len(distance_groups) else [],
                    id_groups[group_index] if group_index < len(id_groups) else [],
                )

        retrieved: list[RetrievedSpecChunk] = []
        # 集合定义在查询循环外，因此多个查询意图之间也按内容全局去重。
        seen_hashes: set[str] = set()

        # 即使查询因过滤条件分组执行，最终结果仍按调用方原始查询顺序排列。
        for query_index in range(len(normalized_queries)):
            documents, metadatas, distances, ids = raw_results.get(
                query_index,
                ([], [], [], []),
            )
            selected = 0
            ranked_indices = sorted(
                range(len(documents or [])),
                key=lambda index: _retrieval_priority_score(
                    distances[index] if index < len(distances) else None,
                    metadatas[index] if index < len(metadatas) and metadatas[index] else {},
                ),
            )
            for index in ranked_indices:
                document = documents[index]
                metadata = metadatas[index] if index < len(metadatas) and metadatas[index] else {}
                dedupe_hash = self._retrieval_hash(document or "", metadata)
                if dedupe_hash in seen_hashes:
                    continue
                seen_hashes.add(dedupe_hash)
                retrieved.append(RetrievedSpecChunk(
                    document=document or "",
                    metadata=metadata,
                    distance=distances[index] if index < len(distances) else None,
                    id=str(ids[index]) if index < len(ids) else None,
                ))
                selected += 1
                # 每个查询最多贡献 limit 个尚未被其他查询选中的片段。
                if selected >= limit:
                    break

        retrieved = self._expand_parent_neighbors(collection, retrieved)
        self._last_results = retrieved
        if retrieval_cache is not None and cache_key is not None:
            retrieval_cache[cache_key] = list(retrieved)
        return retrieved

    def _retrieval_cache_key(
        self,
        normalized_queries: list[tuple[str, dict[str, Any] | None]],
        per_query: int,
    ) -> str:
        """以查询 + 过滤 + 知识库版本 + embedding 版本构造稳定缓存键。"""
        stats = getattr(self, "_last_sync_stats", {}) or {}
        revision = (
            stats.get("total", 0),
            stats.get("updated", 0),
            stats.get("deleted", 0),
        )
        embedding_function = getattr(self, "_embedding_function", None)
        payload = json.dumps({
            "queries": [
                (text, json.dumps(filt or {}, sort_keys=True, ensure_ascii=True))
                for text, filt in normalized_queries
            ],
            "per_query": per_query,
            "revision": revision,
            "embedding": type(embedding_function).__name__ if embedding_function is not None else "none",
        }, ensure_ascii=True, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _retrieval_hash(self, document: str, metadata: dict[str, Any]) -> str:
        """优先按无知识路径前缀的正文哈希去重，兼容旧索引 metadata。"""
        return str(
            metadata.get("body_hash")
            or metadata.get("content_hash")
            or hashlib.sha256(document.encode("utf-8")).hexdigest()[:16]
        )

    def _expand_parent_neighbors(
        self,
        collection: Any,
        chunks: list[RetrievedSpecChunk],
        neighbor_parts: int = 1,
    ) -> list[RetrievedSpecChunk]:
        """命中长度子片时补充同一父块的相邻 part，避免说明与示例脱节。"""
        expanded: list[RetrievedSpecChunk] = []
        seen_hashes: set[str] = set()

        for hit in chunks:
            parent_id = hit.metadata.get("parent_chunk_id")
            part_index = hit.metadata.get("part_index")
            candidates = [hit]
            if parent_id and isinstance(part_index, int):
                try:
                    siblings = collection.get(
                        where=self._query_where({"parent_chunk_id": parent_id}),
                        include=["documents", "metadatas"],
                    )
                except Exception as exc:
                    # 单个分片的相邻查找失败时仅跳过扩展，不影响整条检索结果。
                    logger.warning(f"[RAG] 相邻分片检索失败，跳过扩展: {exc}")
                    siblings = None
                if isinstance(siblings, dict):
                    documents = siblings.get("documents") or []
                    metadatas = siblings.get("metadatas") or []
                    ids = siblings.get("ids") or []
                    candidates = []
                    for index, document in enumerate(documents):
                        metadata = (
                            metadatas[index]
                            if index < len(metadatas) and metadatas[index]
                            else {}
                        )
                        sibling_index = metadata.get("part_index")
                        if (
                            isinstance(sibling_index, int)
                            and abs(sibling_index - part_index) <= neighbor_parts
                        ):
                            candidates.append(RetrievedSpecChunk(
                                document=document or "",
                                metadata=metadata,
                                distance=hit.distance if sibling_index == part_index else None,
                                id=str(ids[index]) if index < len(ids) else None,
                            ))
                    candidates.sort(key=lambda item: int(item.metadata.get("part_index") or 0))
                    if not candidates:
                        candidates = [hit]

            for candidate in candidates:
                dedupe_hash = self._retrieval_hash(
                    candidate.document,
                    candidate.metadata,
                )
                if dedupe_hash in seen_hashes:
                    continue
                seen_hashes.add(dedupe_hash)
                expanded.append(candidate)
        return expanded

    def _query_where(
        self,
        metadata_filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """组合索引隔离、导航文档排除和调用方业务过滤条件。"""
        business_filter, access_conditions, _ = split_business_and_access_filters(
            metadata_filter
        )
        conditions: list[dict[str, Any]] = [
            {"namespace": self._namespace},
            {"doc_scope": {"$ne": "index"}},
        ]
        if "status" not in business_filter:
            conditions.append({"status": {"$ne": "proposed"}})
        if "authority" not in business_filter:
            conditions.append({"authority": {"$ne": "inferred"}})
        conditions.extend(access_conditions)
        conditions.extend(
            {key: value}
            for key, value in business_filter.items()
        )
        return {"$and": conditions}

    def _get_collection(self):
        if self._collection is not None:
            # Loader 生命周期内复用同一 Chroma collection 与持久化客户端。
            return self._collection

        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError("缺少 chromadb 依赖，请先安装 wild-server 依赖") from exc

        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self._persist_dir))
        # index_signature 描述会影响向量兼容性的配置，写入集合 metadata。
        collection_metadata = {
            "project": "WildAgent",
            "namespace": self._namespace,
            "version": "3",
            "index_signature": self._index_signature(),
        }
        collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata=collection_metadata,
            embedding_function=self._embedding_function,
        )

        existing_signature = (collection.metadata or {}).get("index_signature")
        if existing_signature != collection_metadata["index_signature"]:
            # embedding 或分片策略变化后旧向量不可复用，直接重建整个集合。
            self._client.delete_collection(name=self._collection_name)
            collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata=collection_metadata,
                embedding_function=self._embedding_function,
            )

        self._collection = collection
        return self._collection

    def _index_signature(self) -> str:
        get_config = getattr(self._embedding_function, "get_config", None)
        embedding_config = get_config() if callable(get_config) else {}
        # 只纳入会改变向量或分片边界的参数；top_k 等查询参数无需重建索引。
        signature_data = {
            "version": 3,
            "embedding_function": self._embedding_function.__class__.__name__,
            "embedding_config": embedding_config,
            "chunk_size": self._chunker.chunk_size,
            "chunk_overlap": self._chunker.chunk_overlap,
        }
        # 排序后的 JSON 保证相同配置跨进程生成相同签名。
        payload = json.dumps(signature_data, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _load_base_text(self) -> str:
        # 复用文件加载器，确保 RAG 与非 RAG 模式的基础规范格式一致。
        return FileSpecLoader([str(p) for p in self._base_paths]).load()

    def _build_chunks(self) -> list[SpecChunk]:
        chunks: list[SpecChunk] = []
        for path in self._rag_paths:
            # README 等索引文档会由 chunker 改为 index scope，并在普通检索时排除。
            chunks.extend(self._chunker.split_file(
                path,
                namespace=self._namespace,
                doc_scope="generation",
            ))
        return chunks

    def _format_retrieved(self, chunks: list[RetrievedSpecChunk]) -> str:
        if not chunks:
            return ""

        parts = ["## RAG 检索到的相关规范片段"]
        for index, chunk in enumerate(chunks, start=1):
            source = chunk.metadata.get(
                "source_file",
                chunk.metadata.get("source", "unknown"),
            )
            heading = chunk.metadata.get("heading", "")
            metadata_text = ", ".join(
                f"{key}={chunk.metadata[key]}"
                for key in ("doc_type", "entity_name", "topic", "status", "authority")
                if chunk.metadata.get(key)
            )
            distance = chunk.distance
            # 展示原始距离；实际排序还叠加了有限的 status/authority 成熟度惩罚。
            distance_text = f", distance={distance:.4f}" if isinstance(distance, float) else ""
            chunk_id_text = chunk.id or "unknown"
            parts.append(
                f"### 片段 {index}: {source} / {heading}{distance_text}\n\n"
                f"[chunk_id={chunk_id_text}]\n\n"
                f"> metadata: {metadata_text}\n\n"
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
        # 同时具备密钥和模型名时优先使用真实语义 embedding。
        return OpenAICompatibleEmbeddingFunction(
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            batch_size=10,
        )

    if allow_hash_fallback:
        # 无网络开发环境可继续启动，但召回能力仅接近关键词匹配。
        return HashEmbeddingFunction()

    raise RuntimeError(
        "RAG 已启用，但缺少 EMBEDDING__API_KEY 或 EMBEDDING__NAME，且未允许 hash fallback"
    )
