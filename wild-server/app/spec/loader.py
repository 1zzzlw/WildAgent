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
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from loguru import logger
from app.agent.knowledge_policy import (
    GENERATION_ROLES, KNOWLEDGE_GUIDANCE, KNOWLEDGE_REVISION,
    knowledge_hit_applies, restrict_building_query,
)

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
    record_rag_warning,
)
from app.spec.query_planner import build_alias_catalog, build_query_plan
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

    def load_many(self, queries: list, per_query: int = 1, *, purpose: str = "generation") -> str:
        """向量不可用时各节点仍获得固定协议；不补入建筑案例。"""
        return self.load()

    @property
    def last_results(self) -> list:
        return []

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


def _without_derived_entity_name(
    original_filter: dict[str, Any] | None,
    planned_filter: dict[str, Any],
) -> dict[str, Any]:
    """剔除 query_planner 推导出的 entity_name，保留调用方显式指定的 entity_name。

    planner 把别名命中的实体名当作硬过滤，但知识库实体命名粒度常与别名不完全
    一致（如"别墅"覆盖 villa / modern_villa / chinese_traditional_villa），
    硬过滤会漏召回。调用方显式传的 entity_name 是用户意图，必须保留。
    """
    result = dict(planned_filter or {})
    explicit = dict(original_filter or {})
    if "entity_name" in result and "entity_name" not in explicit:
        result.pop("entity_name", None)
    # 同一术语可同时有参数、约束和组装章节，别名不是主题硬过滤依据。
    if "topic" not in explicit:
        result.pop("topic", None)
    return result


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
        timeout: float = 60.0,
        max_retries: int = 1,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name
        # 上游兼容服务可能限制单批数量，因此即使配置更大也收敛到 10。
        self.batch_size = max(1, min(batch_size, 10))
        self.timeout = max(1.0, float(timeout))
        self.max_retries = max(0, int(max_retries))
        # 延迟创建客户端，使配置与索引对象初始化时不立即发起外部连接。
        self._client: Any | None = None

    def __call__(self, input: list[str]) -> list[list[float]]:
        if not input:
            return []

        embeddings: list[list[float]] = []
        index = 0
        slice_size = self.batch_size
        while index < len(input):
            # 分批调用既遵守服务限制，也避免一次请求携带过多文本。
            batch = input[index:index + slice_size]
            try:
                embeddings.extend(self._embed_batch(batch))
                index += len(batch)
            except Exception as exc:
                # 不同网关/模型的单批条数限制可能比配置更低：遇到"输入类 400"
                # 时把本批减半重试，而不是让整批报废（参考百炼 20 条限制类问题）。
                # 网络类错误（超时/连接）仍按 _embed_batch 内的重试处理，不在这里消化。
                message = str(exc).lower()
                is_input_limit = (
                    type(exc).__name__ in {"BadRequestError", "InvalidRequestError", "InvalidParameter"}
                    or "invalidparameter" in message
                ) and ("input" in message or "条" in message or "batch" in message)
                if not is_input_limit or len(batch) <= 1:
                    raise
                reduced = max(1, len(batch) // 2)
                if reduced >= len(batch):
                    raise
                logger.warning(
                    "Embedding 单批请求被网关拒绝（{}），疑似单批条数限制低于 {}；"
                    "本批 {}/{} 条减半为 {} 条重试",
                    type(exc).__name__, slice_size, len(batch), slice_size, reduced,
                )
                slice_size = reduced
                # 注意：不推进 index；只缩小本轮切片的条数后原地重试。
        return embeddings

    def _embed_batch(self, input: list[str]) -> list[list[float]]:
        # SDK 的 max_retries 只重试部分可恢复错误（连接类重试对 timeout 常不生效），
        # 这里对超时/连接错误做指数退避的有限重试，兼容"代理冷连接首请求慢"场景。
        # 请求在 helper 线程内执行，等待期间每 20s 打一条心跳日志，避免
        # 后台索引同步长时间无输出被误判为"服务卡死"。
        client = self._get_client()
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._embed_with_heartbeat(client, input, attempt)
                # 部分兼容服务不保证 data 顺序，按响应 index 恢复成输入顺序。
                sorted_data = sorted(response.data, key=lambda item: item.index)
                return [list(item.embedding) for item in sorted_data]
            except Exception as exc:  # noqa: BLE001 - 按异常名识别可重试错误
                error_name = type(exc).__name__
                retryable = error_name in {"APITimeoutError", "APIConnectionError"} or (
                    error_name == "ReadTimeout"
                )
                if not retryable or attempt >= self.max_retries:
                    if attempt >= self.max_retries:
                        logger.error(
                            "Embedding 请求已耗尽 {} 次重试：{}。若持续超时，可在 .env "
                            "调小 EMBEDDING__TIMEOUT/EMBEDDING__MAX_RETRIES 以快速失败，"
                            "或检查代理/网络；索引保持部分可用，不影响服务启动。",
                            self.max_retries + 1, exc,
                        )
                    raise
                last_error = exc
                delay = min(1.5 * (2 ** attempt), 8.0)
                logger.warning(
                    "Embedding 请求失败（{}），第 {} 次重试，{}s 后继续：{}",
                    error_name, attempt + 1, round(delay, 1), exc,
                )
                time.sleep(delay)
        # 理论不可达：max_retries >= 0 时循环内已处理全部失败路径。
        assert last_error is not None
        raise last_error

    def _embed_with_heartbeat(self, client: Any, input: list[str], attempt: int) -> Any:
        """在工作线程里执行一次 embedding 请求，主线程按 20s 心跳打日志。

        请求本身仍受 ``self.timeout`` 约束；心跳只解决"等待期无日志"的
        可观测性问题，不改变任何超时/重试语义。
        """
        box: dict[str, Any] = {}

        def work() -> None:
            try:
                box["result"] = client.embeddings.create(
                    model=self.model_name,
                    input=input,
                    # 百炼兼容接口明确支持 float；显式指定可避免 SDK 默认请求 base64。
                    encoding_format="float",
                )
            except BaseException as exc:  # noqa: BLE001 - 跨线程搬运异常
                box["error"] = exc

        worker = threading.Thread(target=work, name="embedding-request", daemon=True)
        worker.start()
        waited = 0.0
        while worker.is_alive():
            worker.join(timeout=20.0)
            if worker.is_alive():
                waited += 20.0
                logger.info(
                    "Embedding 请求仍在等待响应（第 {} 次尝试，已等待 {:.0f}s，"
                    "单次超时上限 {:.0f}s）……",
                    attempt + 1, waited, self.timeout,
                )
        error = box.get("error")
        if error is not None:
            raise error
        return box["result"]

    def _get_client(self):
        if self._client is not None:
            return self._client

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("缺少 openai 依赖，请先安装 wild-server 依赖") from exc

        # base_url 为空时传 None，让 OpenAI 客户端使用默认服务地址。
        # 注意：SDK 内部重试必须关闭（max_retries=0），否则 SDK 会按同样的
        # 次数静默重试超时请求，与 _embed_batch 的手动重试叠加成
        # (max_retries+1)^2 倍的等待时间；重试统一由手动循环带心跳执行。
        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url or None,
            timeout=self.timeout,
            max_retries=0,
        )
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
        "knowledge_revision",
        "knowledge_role",
        "applies_to",
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
            "knowledge_revision": KNOWLEDGE_REVISION,
            "knowledge_role": "capability",
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
            metadata.update({"doc_type": "building_type", "entity_type": "building", "knowledge_role": "identity"})
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
        allow_destructive_rebuild: bool = False,
    ):
        self._base_paths = [Path(p) for p in base_paths]
        self._rag_paths = [Path(p) for p in rag_paths]
        self._persist_dir = Path(persist_dir)
        self._collection_name = collection_name
        self._embedding_function = embedding_function
        self._top_k = max(1, top_k)
        self._max_context_chars = max(4000, max_context_chars)
        self._namespace = namespace
        # 模型切换时默认保护旧集合。只有迁移/维护命令显式授权，才允许原地删库重建。
        self._allow_destructive_rebuild = bool(allow_destructive_rebuild)
        self._chunker = MarkdownChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self._loaded_at: float | None = None
        # 保存最近一次检索和同步状态，供 AgentService 写诊断日志。
        self._last_results: list[RetrievedSpecChunk] = []
        self._last_sync_stats = {"total": 0, "updated": 0, "deleted": 0}
        self._last_sync_pending = 0
        self._client: Any | None = None
        self._collection: Any | None = None
        self._retrieval_cache: dict[str, list[RetrievedSpecChunk]] = {}
        # 别名目录按知识库版本惰性构建并缓存，供 build_query_plan 使用。
        self._alias_catalog_cache: dict[str, Any] | None = None
        self._alias_catalog_revision: tuple[int, int, int] | None = None
        # hash fallback 只用于开发 smoke test，其 bigram 向量空间里英文别名是噪声，
        # 因此关闭别名改写；真实语义 embedding 下启用。
        embedding_name = getattr(embedding_function, "__class__", None)
        self._query_rewrite_enabled = (
            embedding_name is None
            or embedding_name.__name__ != "HashEmbeddingFunction"
        )
        # 后台同步的一次性调度状态：进程内单飞 + 跨进程文件锁，避免 dev reload
        # 的父/子进程或重复构造同时写同一份 Chroma。
        self._sync_guard = threading.RLock()
        self._sync_thread_started = False
        self._sync_thread: threading.Thread | None = None
        self._sync_status: dict[str, Any] = {
            "phase": "pending",  # pending | syncing | ok | degraded
            "attempts": 0,
            "last_error": None,
            "last_success_at": None,
            "pending_chunks": 0,
        }

        if auto_sync:
            # 默认在 Loader 构造时同步一次，保证第一次查询即可命中新文档。
            # 需要避免阻塞启动的调用方应传 auto_sync=False 并显式调用
            # start_background_sync()（AgentService 使用该路径）。
            self.sync_index()

    # ── 后台同步（不阻塞服务启动）───────────────────────────────────────
    # 背景：模块导入路径上同步执行 sync_index 会让服务在 embedding 服务
    # 慢/超时时阻塞数分钟。这里提供"构造完成后由守护线程后台同步"的路径，
    # 并配进程级文件锁，防止 dev reload 父/子进程同时写同一份 Chroma。
    _PROCESS_LOCK_NAME = ".wild_rag_sync.lock"
    _PROCESS_LOCK_WAIT = 1.0   # 拿不到锁时的轮询间隔（秒）

    def start_background_sync(
        self,
        *,
        attempts: int = 3,
        backoff_seconds: tuple[float, ...] = (15.0, 60.0, 300.0),
    ) -> bool:
        """启动一次后台索引同步（进程内单飞）。

        返回 False 表示本轮已经有一个后台同步线程在跑（幂等）。
        同步失败不会让 loader 抛异常：索引保持"部分可用"，检索自动降级
        为基础规范上下文；错误通过日志和 self.sync_status 暴露。
        """
        with self._sync_guard:
            if self._sync_thread_started:
                return False
            self._sync_thread_started = True
            thread = threading.Thread(
                target=self._background_sync_worker,
                args=(max(1, int(attempts)), tuple(backoff_seconds)),
                name="rag-index-sync",
                daemon=True,
            )
            self._sync_thread = thread
        thread.start()
        logger.info("RAG 索引同步：已在后台线程启动（不影响服务启动）")
        return True

    @property
    def sync_status(self) -> dict[str, Any]:
        """后台同步的观测状态（phase/attempts/last_error/last_success_at）。"""
        return dict(getattr(self, "_sync_status", {}) or {})

    def _background_sync_worker(
        self,
        attempts: int,
        backoff_seconds: tuple[float, ...],
    ) -> None:
        for attempt in range(1, attempts + 1):
            lock_handle = None
            try:
                lock_handle = self._try_process_lock()
                if lock_handle is None:
                    logger.info(
                        "RAG 索引同步：另一进程正在同步，按退避等待后重试（第 {}/{} 次）",
                        attempt, attempts,
                    )
                    if attempt < attempts:
                        delay = backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)]
                        time.sleep(delay)
                    continue
                status = self._sync_status
                status["phase"] = "syncing"
                status["attempts"] = attempt
                status["last_error"] = None
                # 3 连超时不再整体失败：剩余批次保留待同步，已有批次保持可用。
                self.sync_index(raise_on_stall=False)
                pending_chunks = self.last_sync_pending
                if pending_chunks:
                    error_text = f"仍有 {pending_chunks} 个文本块待同步"
                    status.update(
                        phase="degraded",
                        last_error=error_text,
                        pending_chunks=pending_chunks,
                    )
                    if attempt >= attempts:
                        logger.error(
                            "RAG 索引同步：后台已耗尽 {}/{} 次尝试，{}；"
                            "保持 degraded，等待手动同步或下次启动补齐",
                            attempt, attempts, error_text,
                        )
                        return
                    logger.warning(
                        "RAG 索引同步：后台第 {}/{} 次未完成，{}；将按退避策略重试",
                        attempt, attempts, error_text,
                    )
                    # 退避等待期间不要占用跨进程锁，让 dev reload 的另一个健康
                    # 进程有机会接手同步。
                    self._release_process_lock(lock_handle)
                    lock_handle = None
                    delay = backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)]
                    time.sleep(delay)
                    continue
                status["phase"] = "ok"
                status["last_success_at"] = time.time()
                status["pending_chunks"] = 0
                logger.info("RAG 索引同步：后台同步完成")
                return
            except Exception as exc:
                # 只有真正的本地/结构性错误（如 Chroma 打不开）会走到这里；
                # embedding 超时已被 sync_index 内部消化为"待同步"。
                error_text = f"{type(exc).__name__}: {exc}"
                self._sync_status.update(phase="degraded", last_error=error_text)
                logger.error(
                    "RAG 索引同步失败（后台，第 {}/{} 次），索引保持部分可用：{}",
                    attempt, attempts, error_text,
                )
                if attempt >= attempts:
                    return
                self._release_process_lock(lock_handle)
                lock_handle = None
                delay = backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)]
                time.sleep(delay)
            finally:
                if lock_handle is not None:
                    self._release_process_lock(lock_handle)

    def _try_process_lock(self) -> Any | None:
        """非阻塞获取跨进程同步锁；返回文件句柄，失败（锁被占用）返回 None。"""
        try:
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            handle = open(self._persist_dir / self._PROCESS_LOCK_NAME, "a+b")  # noqa: SIM115
        except OSError as exc:
            logger.warning("RAG 索引同步：无法创建进程锁文件（{}），跳过本轮同步", exc)
            return None
        try:
            if os.name == "nt":
                import msvcrt
                # msvcrt.locking 从当前文件位置开始锁定；固定锁第 0 个字节，避免
                # a+b 的初始指针位于文件末尾而导致不同进程锁住不同区域。
                handle.seek(0)
                if not handle.read(1):
                    handle.seek(0)
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return None
        # 写入持有者标记便于排查；锁释放后文件仍保留但不再上锁。
        handle.seek(0)
        handle.write(f"pid={os.getpid()} at={time.time():.0f}".encode("utf-8"))
        handle.truncate()
        handle.flush()
        return handle

    def _release_process_lock(self, handle: Any) -> None:
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            try:
                handle.close()
            except OSError:
                pass

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

    @property
    def last_sync_pending(self) -> int:
        """最近一次同步结束后仍未写入的正文块数。"""
        return int(getattr(self, "_last_sync_pending", 0) or 0)

    def sync_index(
        self,
        *,
        raise_on_stall: bool = True,
        budget_seconds: float | None = None,
    ) -> int:
        """增量同步当前 namespace，返回本次新增或变化的 chunk 数。

        ``raise_on_stall``：连续 3 批请求超时后是否抛出异常。默认抛出以保留
        历史"整体降级"语义；后台同步路径传 False，只停止本轮并把剩余批次
        保留为待同步，已写入批次继续可用，不中断服务。

        ``budget_seconds``：可选总时间预算（不含删除/元数据等本地步骤）；
        超预算立即收尾，剩余批次保留待下次同步。
        """
        started = time.perf_counter()
        logger.info("RAG 索引同步：正在打开向量集合……")
        collection = self._get_collection()
        logger.info("RAG 索引同步：正在读取并切分知识库文档……")
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

        # 每批与 EmbeddingFunction 的上限保持一致；成功后立即持久化，重启时
        # 可以从尚未入库的块继续同步。
        batch_size = 10
        total = len(pending_chunks)
        self._last_sync_pending = total
        if hasattr(self, "_sync_status"):
            self._sync_status["pending_chunks"] = total
        batch_count = math.ceil(total / batch_size)
        logger.info(
            "RAG 索引同步：共 {} 块，待向量化 {} 块（{} 批），待删除 {} 块，待更新元数据 {} 块",
            len(chunks), total, batch_count, len(stale_ids), len(metadata_only_chunks),
        )
        if not total:
            logger.info("RAG 索引同步：无需重新向量化")

        def log_progress(completed: int, status: str) -> None:
            # 只按成功写入的块推进；等待接口时保留上一批的实际进度。
            filled = completed * 20 // total
            logger.info(
                "RAG 向量化 [{}{}] {:.0f}% {}/{} 块 | {} | 累计 {:.1f}s",
                "#" * filled, "-" * (20 - filled), completed * 100 / total,
                completed, total, status, time.perf_counter() - started,
            )

        def describe_batch(batch: list[SpecChunk]) -> str:
            sources = sorted({
                str(chunk.metadata.get("source_file") or chunk.metadata.get("source") or "unknown")
                for chunk in batch
            })
            source_preview = ", ".join(sources[:3])
            if len(sources) > 3:
                source_preview += f" 等 {len(sources)} 个文件"
            input_chars = sum(len(chunk.document) for chunk in batch)
            return f"{len(batch)} 块/{input_chars} 字符（{source_preview}）"

        def embed_and_upsert(batch: list[SpecChunk], label: str) -> None:
            documents = [chunk.document for chunk in batch]
            embeddings = self._embedding_function.embed_documents(documents)
            logger.info(
                "RAG 向量化：{} 已收到 {} 个向量，正在写入 Chroma……",
                label, len(embeddings),
            )
            collection.upsert(
                ids=[chunk.id for chunk in batch],
                documents=documents,
                embeddings=embeddings,
                metadatas=[chunk.metadata for chunk in batch],
            )

        for start in range(0, len(stale_ids), batch_size):
            # 删除已移除文件、已改变内容或因重新分片而失效的旧 ID。
            collection.delete(ids=stale_ids[start:start + batch_size])

        completed = 0
        deferred_batches: list[tuple[int, list[SpecChunk]]] = []
        consecutive_timeouts = 0
        stalled = False
        budget_exceeded = False
        for start in range(0, len(pending_chunks), batch_size):
            if (
                budget_seconds is not None
                and time.perf_counter() - started >= budget_seconds
            ):
                budget_exceeded = True
                logger.warning(
                    "RAG 索引同步：已达到时间预算（{:.0f}s），剩余 {} 块保留为待同步",
                    budget_seconds, total - completed,
                )
                break
            batch = pending_chunks[start:start + batch_size]
            batch_number = start // batch_size + 1
            batch_description = describe_batch(batch)
            log_progress(
                completed,
                f"第 {batch_number}/{batch_count} 批：请求 Embedding，"
                f"{batch_description}",
            )
            batch_started = time.perf_counter()
            try:
                # 显式拆开远程向量计算与本地 Chroma 写入，避免 upsert 内部调用
                # 把网络等待和数据库等待混在同一个不可观测步骤中。
                embed_and_upsert(batch, f"第 {batch_number}/{batch_count} 批")
            except Exception as exc:
                if type(exc).__name__ == "APITimeoutError":
                    consecutive_timeouts += 1
                    deferred_batches.append((batch_number, batch))
                    logger.warning(
                        "RAG 向量化超时：第 {}/{} 批已延后，将继续处理后续批次；"
                        "本批 {}，耗时 {:.1f}s",
                        batch_number, batch_count, batch_description,
                        time.perf_counter() - batch_started,
                    )
                    if consecutive_timeouts >= 3:
                        # 服务整体不可用时及时停止，避免每一批都等待完整超时。
                        if raise_on_stall:
                            logger.error("RAG 连续 3 批请求超时，停止本次索引同步")
                            raise
                        stalled = True
                        logger.error(
                            "RAG 向量化连续 3 批请求超时，停止本次同步；"
                            "已写入部分保持可用，剩余 {} 块保留为待同步",
                            total - completed,
                        )
                        break
                    continue
                logger.error(
                    "RAG 向量化失败：第 {}/{} 批，已完成 {}/{} 块，本批耗时 {:.1f}s，错误类型 {}",
                    batch_number, batch_count, completed, total,
                    time.perf_counter() - batch_started, type(exc).__name__,
                )
                raise
            consecutive_timeouts = 0
            completed += len(batch)
            self._last_sync_pending = total - completed
            if hasattr(self, "_sync_status"):
                self._sync_status["pending_chunks"] = self._last_sync_pending
            log_progress(
                completed,
                f"第 {batch_number}/{batch_count} 批完成，耗时 {time.perf_counter() - batch_started:.1f}s",
            )

        if deferred_batches and not stalled and not budget_exceeded:
            logger.warning("RAG 索引同步：开始重试 {} 个超时批次", len(deferred_batches))
        for batch_number, batch in deferred_batches:
            if stalled or budget_exceeded:
                # 服务不可用或预算耗尽时不再重试延后批次，避免无意义的长时间等待；
                # 它们与未处理的批次一样保留为待同步。
                break
            batch_started = time.perf_counter()
            try:
                embed_and_upsert(batch, f"重试原第 {batch_number}/{batch_count} 批")
            except Exception as exc:
                if type(exc).__name__ != "APITimeoutError":
                    raise
                logger.error(
                    "RAG 超时批次重试失败：原第 {}/{} 批，本次保留为待同步，"
                    "不影响其余索引使用；失败 {} 块，耗时 {:.1f}s",
                    batch_number, batch_count, len(batch),
                    time.perf_counter() - batch_started,
                )
                continue
            completed += len(batch)
            self._last_sync_pending = total - completed
            if hasattr(self, "_sync_status"):
                self._sync_status["pending_chunks"] = self._last_sync_pending
            log_progress(
                completed,
                f"原第 {batch_number}/{batch_count} 批重试成功，耗时 "
                f"{time.perf_counter() - batch_started:.1f}s",
            )

        for start in range(0, len(metadata_only_chunks), batch_size):
            batch = metadata_only_chunks[start:start + batch_size]
            collection.update(
                ids=[chunk.id for chunk in batch],
                metadatas=[chunk.metadata for chunk in batch],
            )

        self._last_sync_stats = {
            "total": len(chunks),
            "updated": completed + len(metadata_only_chunks),
            "deleted": len(stale_ids),
        }
        # 索引内容变化后使检索缓存失效，避免命中过期的召回结果。
        retrieval_cache = getattr(self, "_retrieval_cache", None)
        if retrieval_cache is not None:
            retrieval_cache.clear()

        elapsed = time.perf_counter() - started
        pending_remaining = total - completed
        self._last_sync_pending = pending_remaining
        if hasattr(self, "_sync_status"):
            self._sync_status["pending_chunks"] = pending_remaining
        if budget_exceeded or stalled:
            logger.warning(
                "RAG 索引同步：本轮停止，索引部分可用；仍有 {} 块待同步，"
                "后续启动或手动同步将自动补齐（本轮耗时 {:.1f}s）",
                pending_remaining, elapsed,
            )
        elif pending_remaining:
            logger.warning(
                "RAG 索引同步完成但仍有 {} 块待同步；下次启动将自动重试，耗时 {:.1f}s",
                pending_remaining, elapsed,
            )
        else:
            logger.info("RAG 索引同步完成，耗时 {:.1f}s", elapsed)
        return completed + len(metadata_only_chunks)

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
        if not getattr(self, "_query_rewrite_enabled", True):
            # 检索发生时（请求上下文内）标记 hash 降级，便于 trace 里看到距离阈值失效。
            record_rag_warning(
                "hash_embedding_fallback",
                "当前使用 hash fallback embedding；仅适合本地 smoke test，"
                "检索门禁距离阈值在该模式下无效。",
            )

        # 用别名命中补全粗粒度过滤（doc_type/entity_type），但剔除 entity_name：
        # 别名命中的实体名常与知识库实体命名粒度不一致（如"别墅"有 villa、
        # modern_villa 多个变体），做硬过滤会漏召回。查询文本保持原文。
        # hash 模式不启用。
        if getattr(self, "_query_rewrite_enabled", True):
            planned = build_query_plan(
                query,
                metadata_filter,
                alias_catalog=self._alias_catalog(),
                include_topic_hints=False,
            )
            query_text = query
            effective_filter = _without_derived_entity_name(
                metadata_filter,
                planned.metadata_filter,
            )
        else:
            query_text = query
            effective_filter = metadata_filter

        # 多取一倍候选，为后面的精确内容去重留出补位空间。
        effective_filter = restrict_building_query(query, effective_filter, self._alias_catalog())
        n_results = min(self._top_k * 2, count)
        result = collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=self._query_where(effective_filter),
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
            if not knowledge_hit_applies(query, metadata):
                continue
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

        retrieved = [hit for hit in self._expand_parent_neighbors(collection, retrieved)
                     if knowledge_hit_applies(query, hit.metadata)]
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
        """批量检索多个意图，每个意图保留固定数量并全局去重。

        携带显式 metadata_filter 的 SpecQuery 会先经 build_query_plan 做别名过滤
        补全，再执行向量检索；查询文本保持原文，过滤补全不改变安全过滤。
        纯 str 查询保持原样，不引入别名目录构建开销。
        """
        rewrite_enabled = getattr(self, "_query_rewrite_enabled", True)
        has_spec_query = any(isinstance(query, SpecQuery) for query in queries)
        alias_catalog = self._alias_catalog() if (has_spec_query and rewrite_enabled) else {}
        normalized_queries: list[tuple[str, dict[str, Any] | None]] = []
        for query in queries:
            if isinstance(query, SpecQuery):
                text = query.text.strip()
                metadata_filter = query.metadata_filter
            else:
                text = query.strip()
                metadata_filter = None
            if text:
                if isinstance(query, SpecQuery) and rewrite_enabled:
                    planned = build_query_plan(
                        text,
                        metadata_filter,
                        alias_catalog=alias_catalog,
                        include_topic_hints=False,
                    )
                    # 查询文本保持原文；只采纳粗粒度过滤补全（剔除推导的
                    # entity_name），调用方显式条件始终优先。
                    normalized_queries.append(
                        (text, _without_derived_entity_name(
                            metadata_filter,
                            planned.metadata_filter,
                        ))
                    )
                else:
                    normalized_queries.append((text, metadata_filter))

        normalized_queries = [
            (text, restrict_building_query(text, metadata, self._alias_catalog()))
            for text, metadata in normalized_queries
        ]
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
            query_text = normalized_queries[query_index][0]
            selected = 0
            ranked_indices = sorted(
                range(len(documents or [])),
                key=lambda index: _retrieval_priority_score(
                    distances[index] if index < len(distances) else None,
                    metadatas[index] if index < len(metadatas) and metadatas[index] else {},
                ),
            )
            query_chunks: list[RetrievedSpecChunk] = []
            for index in ranked_indices:
                document = documents[index]
                metadata = metadatas[index] if index < len(metadatas) and metadatas[index] else {}
                if not knowledge_hit_applies(query_text, metadata):
                    continue
                dedupe_hash = self._retrieval_hash(document or "", metadata)
                if dedupe_hash in seen_hashes:
                    continue
                seen_hashes.add(dedupe_hash)
                query_chunks.append(RetrievedSpecChunk(
                    document=document or "",
                    metadata=metadata,
                    distance=distances[index] if index < len(distances) else None,
                    id=str(ids[index]) if index < len(ids) else None,
                ))
                selected += 1
                # 每个查询最多贡献 limit 个尚未被其他查询选中的片段。
                if selected >= limit:
                    break
            # 组内重排只影响本查询片段的先后顺序，不改变跨查询的返回顺序。
            if config.rag.rerank_enabled:
                query_chunks = self._rerank_retrieved(query_chunks, query_text)
            retrieved.extend(query_chunks)

        retrieved = [hit for hit in self._expand_parent_neighbors(collection, retrieved)
                     if any(knowledge_hit_applies(text, hit.metadata)
                            for text, _ in normalized_queries)]
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

    def _rerank_retrieved(
        self,
        retrieved: list[RetrievedSpecChunk],
        query_terms: str,
    ) -> list[RetrievedSpecChunk]:
        """纯规则重排：知识权威性优先，其次按与查询的检索词重叠度。

        只调整已去重片段的先后顺序，不改变召回集合与数量。权威性取自 chunk
        metadata 的 authority 字段；重叠度用查询文本与片段的字符 bigram 交集
        度量（中文无需分词即可捕捉"雨棚/橱窗"这类双字术语）。
        """
        if len(retrieved) <= 1:
            return retrieved

        authority_rank = {
            "schema": 0,
            "engine": 0,
            "verified": 1,
            "maintainer": 2,
            "domain": 3,
            "imported": 4,
            "inferred": 5,
        }
        query_terms = (query_terms or "").strip()
        query_bigrams: set[str] = set()
        if query_terms:
            query_bigrams = {
                query_terms[i:i + 2]
                for i in range(max(0, len(query_terms) - 1))
                if query_terms[i:i + 2].strip()
            }

        def _bigrams(text: str) -> set[str]:
            text = (text or "").strip()
            return {
                text[i:i + 2]
                for i in range(max(0, len(text) - 1))
                if text[i:i + 2].strip()
            }

        def rank(chunk: RetrievedSpecChunk) -> tuple[int, int, float, int]:
            metadata = chunk.metadata or {}
            authority = str(metadata.get("authority") or "").lower()
            authority_key = authority_rank.get(authority, 4)
            chunk_bigrams = _bigrams(chunk.document)
            overlap = len(query_bigrams & chunk_bigrams) if chunk_bigrams else 0
            distance = chunk.distance
            distance_key = float(distance) if isinstance(distance, (int, float)) else 999.0
            # 权威性 → 重叠度（越多越靠前）→ 原始距离 → 稳定次序。
            return (authority_key, -overlap, distance_key, id(chunk))

        return sorted(retrieved, key=rank)

    def _alias_catalog(self) -> dict[str, Any]:
        """按知识库版本惰性构建别名目录，供 build_query_plan 做实体别名改写。

        目录从已索引 chunk 的 entity_name/primary_terms/synonyms 构建。构建失败
        时降级为空目录：通用规则仍可检索，自动类型路由不放行任何类型。手工构造的测试
        Loader 可能缺少这些属性，统一用 getattr 防御。
        """
        cached = getattr(self, "_alias_catalog_cache", None)
        cached_revision = getattr(self, "_alias_catalog_revision", None)
        stats = getattr(self, "_last_sync_stats", None) or {}
        revision = (stats.get("total", 0), stats.get("updated", 0), stats.get("deleted", 0))
        if cached is not None and cached_revision == revision:
            return cached
        catalog: dict[str, Any] = {}
        try:
            collection = self._get_collection()
            if collection is not None and collection.count() > 0:
                batch = collection.get(where=self._query_where(), include=["metadatas"])
                metadatas = batch.get("metadatas", []) or []
                catalog = build_alias_catalog(metadatas)
        except Exception as exc:
            # 失败时类型路由关闭，通用规则仍可使用。
            logger.warning(f"[RAG] 别名目录构建失败，本次不做别名改写: {exc}")
            catalog = {}
        self._alias_catalog_cache = catalog
        self._alias_catalog_revision = revision
        return catalog

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
            {"knowledge_revision": KNOWLEDGE_REVISION},
        ]
        # 新版本知识未同步时返回空知识，不能退回旧建筑模板。
        if "doc_scope" not in business_filter:
            conditions.append({"doc_scope": "generation"})
        if "knowledge_role" not in business_filter and business_filter.get("doc_scope") != "reference":
            conditions.append({"knowledge_role": {"$in": list(GENERATION_ROLES)}})
        if "status" not in business_filter:
            conditions.append({"status": {"$in": ["supported", "experimental"]}})
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
            if not self._allow_destructive_rebuild:
                raise RuntimeError(
                    "当前 Embedding 模型或切分配置与已有 Chroma 集合签名不一致。"
                    "为保护旧索引，运行时不会自动删除集合；请为新模型设置新的 "
                    "RAG__COLLECTION_NAME，或使用显式迁移命令构建并验证新集合。"
                )
            # 只有显式维护命令可以走原地重建；普通服务启动永远不会自动删旧索引。
            logger.warning("已显式授权：RAG 模型或切分配置变化，将原地重建向量集合")
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

        parts = ["## RAG 检索到的相关规范片段", KNOWLEDGE_GUIDANCE]
        for index, chunk in enumerate(chunks, start=1):
            source = chunk.metadata.get(
                "source_file",
                chunk.metadata.get("source", "unknown"),
            )
            heading = chunk.metadata.get("heading", "")
            metadata_text = ", ".join(
                f"{key}={chunk.metadata[key]}"
                for key in ("doc_type", "entity_name", "topic", "knowledge_role", "status", "authority")
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
    timeout: float = 60.0,
    max_retries: int = 1,
):
    """根据配置创建 Chroma embedding function。

    ``timeout``/``max_retries`` 控制单批向量请求的网络超时与重试；
    两者只在索引同步（后台线程）中使用，不影响任何用户请求延迟。
    """
    if api_key and model_name:
        # 同时具备密钥和模型名时优先使用真实语义 embedding。
        return OpenAICompatibleEmbeddingFunction(
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            batch_size=10,
            timeout=timeout,
            max_retries=max_retries,
        )

    if allow_hash_fallback:
        # 无网络开发环境可继续启动，但召回能力仅接近关键词匹配。
        return HashEmbeddingFunction()

    raise RuntimeError(
        "RAG 已启用，但缺少 EMBEDDING__API_KEY 或 EMBEDDING__NAME，且未允许 hash fallback"
    )
