r"""安全切换 Embedding 模型：先探针，再构建独立 Chroma 集合。

默认只发送一条最小 Embedding 请求，不写 Chroma：

    .\.venv\Scripts\python.exe -m scripts.rag.migrate_embedding_index probe

显式 build 才会全量向量化，并且目标集合不能是当前正式集合：

    .\.venv\Scripts\python.exe -m scripts.rag.migrate_embedding_index build `
      --collection-name wild_knowledge_base_qwen37_v1
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

SERVER_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_BASE = SERVER_ROOT / "storage" / "knowledge_base"
BASE_SPEC_PATHS = [KNOWLEDGE_BASE / "BLUEPRINT-SPEC-MINIMAL.md"]


@dataclass(frozen=True)
class CandidateConfig:
    model: str
    api_key: str
    base_url: str
    timeout: float
    current_collection: str
    persist_dir: Path
    chunk_size: int
    chunk_overlap: int


def _load_candidate_config() -> CandidateConfig:
    """只用标准库读取候选配置，使 probe 不依赖 Pydantic、Agent 或 asyncio。"""
    env_path = Path(os.environ.get("WILD_RUNTIME_ENV_FILE") or SERVER_ROOT / ".env")
    values: dict[str, str] = {}
    if env_path.is_file():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("'\"")

    def value(name: str, default: str = "") -> str:
        return os.environ.get(name, values.get(name, default)).strip()

    return CandidateConfig(
        model=value("EMBEDDING__NAME"),
        api_key=value("EMBEDDING__API_KEY"),
        base_url=value("EMBEDDING__BASE_URL"),
        timeout=float(value("EMBEDDING__TIMEOUT", "60")),
        current_collection=value("RAG__COLLECTION_NAME", "wild_knowledge_base"),
        persist_dir=Path(value("RAG__PERSIST_DIR", "storage/chroma")),
        chunk_size=int(value("RAG__CHUNK_SIZE", "900")),
        chunk_overlap=int(value("RAG__CHUNK_OVERLAP", "150")),
    )


def _safe_url(value: str) -> str:
    """移除代理 URL 中可能存在的用户名和密码。"""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "<invalid-url>"
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def _print_proxy_context() -> None:
    configured = [
        f"{name}={_safe_url(os.environ[name])}"
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")
        if os.environ.get(name)
    ]
    print("进程代理: " + (", ".join(configured) if configured else "未配置"))


def probe_embedding(candidate: CandidateConfig, *, no_proxy: bool = False) -> int:
    """用标准 ``POST /embeddings`` 验证当前候选配置，不接触向量库。"""
    model = candidate.model
    base_url = candidate.base_url.rstrip("/")
    api_key = candidate.api_key
    if not model or not base_url or not api_key:
        raise RuntimeError(
            "缺少 EMBEDDING__NAME / EMBEDDING__BASE_URL / EMBEDDING__API_KEY"
        )

    endpoint = f"{base_url}/embeddings"
    payload = json.dumps(
        {
            "model": model,
            "input": ["WildAgent Embedding model migration probe"],
            "encoding_format": "float",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    print(f"Embedding 模型: {model}")
    print(f"Embedding 地址: {_safe_url(endpoint)}")
    print(f"代理策略: {'强制直连' if no_proxy else '遵循当前进程/系统设置'}")
    started = time.perf_counter()
    try:
        opener = (
            urllib.request.build_opener(urllib.request.ProxyHandler({}))
            if no_proxy
            else urllib.request.build_opener()
        )
        with opener.open(request, timeout=candidate.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        response_text = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Embedding HTTP {exc.code}: {response_text}") from exc
    except Exception as exc:
        _print_proxy_context()
        raise RuntimeError(f"Embedding 连接失败: {type(exc).__name__}: {exc}") from exc

    data = body.get("data") or []
    vector = data[0].get("embedding") if data and isinstance(data[0], dict) else None
    if not isinstance(vector, list) or not vector:
        raise RuntimeError("Embedding 响应中没有有效 data[0].embedding")
    if not all(isinstance(value, (int, float)) for value in vector):
        raise RuntimeError("Embedding 响应不是浮点向量")

    elapsed = time.perf_counter() - started
    print(f"Embedding 探针成功: dimension={len(vector)}, elapsed={elapsed:.2f}s")
    return len(vector)


def _default_target_collection(candidate: CandidateConfig) -> str:
    model_slug = re.sub(r"[^a-z0-9]+", "_", candidate.model.casefold()).strip("_")
    return f"{candidate.current_collection}_{model_slug}_v1"


def _expected_index_signature(candidate: CandidateConfig) -> str:
    """复现 Loader 的签名计算，不导入项目运行时依赖。"""
    import hashlib

    payload = json.dumps(
        {
            "version": 3,
            "embedding_function": "OpenAICompatibleEmbeddingFunction",
            "embedding_config": {
                "base_url": candidate.base_url,
                "model_name": candidate.model,
                "batch_size": 10,
                "api_key": "",
            },
            "chunk_size": max(200, candidate.chunk_size),
            "chunk_overlap": max(
                0,
                min(candidate.chunk_overlap, max(200, candidate.chunk_size) // 2),
            ),
        },
        sort_keys=True,
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def inspect_local_index(candidate: CandidateConfig) -> bool:
    """只读审计 SQLite：不导入 Chroma，也不触发同步或网络请求。"""
    persist_dir = candidate.persist_dir
    if not persist_dir.is_absolute():
        persist_dir = SERVER_ROOT / persist_dir
    database_path = persist_dir / "chroma.sqlite3"
    if not database_path.is_file():
        raise RuntimeError(f"Chroma 数据库不存在: {database_path}")

    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        collection = connection.execute(
            "select id, dimension from collections where name = ?",
            (candidate.current_collection,),
        ).fetchone()
        if collection is None:
            raise RuntimeError(f"集合不存在: {candidate.current_collection}")
        collection_id, dimension = collection
        metadata_rows = connection.execute(
            "select key, str_value, int_value, float_value, bool_value "
            "from collection_metadata where collection_id = ?",
            (collection_id,),
        ).fetchall()
        metadata = {
            key: next(
                (value for value in (str_value, int_value, float_value, bool_value) if value is not None),
                None,
            )
            for key, str_value, int_value, float_value, bool_value in metadata_rows
        }
        indexed_count = connection.execute(
            "select count(distinct e.id) from embeddings e "
            "join segments s on s.id = e.segment_id where s.collection = ?",
            (collection_id,),
        ).fetchone()[0]
        indexed_path_rows = connection.execute(
            "select distinct em.string_value from embedding_metadata em "
            "join embeddings e on e.id = em.id "
            "join segments s on s.id = e.segment_id "
            "where s.collection = ? and em.key = 'path'",
            (collection_id,),
        ).fetchall()
    finally:
        connection.close()

    current_paths = {
        path.resolve().as_posix().casefold(): path.relative_to(KNOWLEDGE_BASE).as_posix()
        for path in KNOWLEDGE_BASE.rglob("*.md")
        if path.resolve() not in {base.resolve() for base in BASE_SPEC_PATHS}
    }
    indexed_paths = {
        Path(row[0]).resolve().as_posix().casefold(): row[0]
        for row in indexed_path_rows
        if row[0]
    }
    missing = [relative for key, relative in current_paths.items() if key not in indexed_paths]
    stale = [path for key, path in indexed_paths.items() if key not in current_paths]
    expected_signature = _expected_index_signature(candidate)
    actual_signature = str(metadata.get("index_signature") or "")

    print(f"数据库: {database_path}")
    print(f"集合: {candidate.current_collection}")
    print(f"配置模型: {candidate.model}")
    print(f"向量维度: {dimension}")
    print(f"已索引向量: {indexed_count}")
    print(f"候选知识文件: {len(current_paths)}")
    print(f"索引覆盖文件: {len(indexed_paths)}")
    print(f"配置签名: {expected_signature}")
    print(f"集合签名: {actual_signature or 'missing'}")
    print(f"签名一致: {expected_signature == actual_signature}")
    print(f"缺少文件: {len(missing)}")
    for path in missing:
        print(f"  + {path}")
    print(f"失效文件: {len(stale)}")
    for path in stale:
        print(f"  - {path}")
    complete = expected_signature == actual_signature and not missing and not stale
    print(f"完整性结论: {'complete' if complete else 'incomplete'}")
    return complete


def build_new_collection(
    candidate: CandidateConfig,
    collection_name: str,
    *,
    no_proxy: bool = False,
) -> None:
    if collection_name == candidate.current_collection:
        raise RuntimeError(
            "目标集合不能与当前 RAG__COLLECTION_NAME 相同。"
            "请使用新集合名，先保留旧索引用于回滚。"
        )

    probe_embedding(candidate, no_proxy=no_proxy)

    # 延迟导入：probe 命令只验证标准接口，不加载 Chroma、LangChain 或 Agent。
    from config import config
    from app.spec.loader import (
        RAGSpecLoader,
        collect_markdown_paths,
        create_embedding_function,
    )

    embedding = create_embedding_function(
        api_key=config.embedding.api_key,
        base_url=config.embedding.base_url,
        model_name=config.embedding.name,
        allow_hash_fallback=False,
        timeout=config.embedding.timeout,
        max_retries=config.embedding.max_retries,
    )
    rag_paths = collect_markdown_paths(KNOWLEDGE_BASE, exclude=BASE_SPEC_PATHS)
    persist_dir = Path(config.rag.persist_dir)
    if not persist_dir.is_absolute():
        persist_dir = SERVER_ROOT / persist_dir

    loader = RAGSpecLoader(
        base_paths=[str(path) for path in BASE_SPEC_PATHS],
        rag_paths=[str(path) for path in rag_paths],
        persist_dir=str(persist_dir),
        collection_name=collection_name,
        embedding_function=embedding,
        top_k=config.rag.top_k,
        chunk_size=config.rag.chunk_size,
        chunk_overlap=config.rag.chunk_overlap,
        max_context_chars=config.rag.max_context_chars,
        auto_sync=False,
        allow_destructive_rebuild=False,
    )

    print(f"开始构建独立集合: {collection_name}")
    loader.sync_index()
    if loader.last_sync_pending:
        raise RuntimeError(f"迁移未完成，仍有 {loader.last_sync_pending} 个文本块待同步")

    collection = loader._get_collection()
    indexed = collection.get(
        where={"namespace": loader._namespace},
        include=["metadatas"],
    )
    indexed_count = len(indexed.get("ids") or [])
    expected_count = loader.last_sync_stats["total"]
    if indexed_count != expected_count:
        raise RuntimeError(
            f"迁移数量校验失败: expected={expected_count}, indexed={indexed_count}"
        )

    print(f"新集合构建完成: chunks={indexed_count}")
    print(f"索引签名: {loader._index_signature()}")
    print("验证召回效果后，将下面一行写入 .env 并重启服务：")
    print(f"RAG__COLLECTION_NAME={collection_name}")
    print("回滚时必须把 Embedding 配置和旧 collection 名一起恢复。")


def parse_args(candidate: CandidateConfig) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    probe_parser = subparsers.add_parser("probe", help="只发送一条最小向量请求")
    probe_parser.add_argument("--no-proxy", action="store_true", help="本次探针强制直连")

    subparsers.add_parser(
        "status",
        help="纯离线读取 Chroma SQLite，检查签名、数量和文件覆盖",
    )

    build_parser = subparsers.add_parser("build", help="全量构建一个独立的新集合")
    build_parser.add_argument(
        "--collection-name",
        default=_default_target_collection(candidate),
        help="新集合名；禁止与当前正式集合相同",
    )
    build_parser.add_argument("--no-proxy", action="store_true", help="探针阶段强制直连")
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    candidate = _load_candidate_config()
    args = parse_args(candidate)
    try:
        if args.command == "probe":
            probe_embedding(candidate, no_proxy=args.no_proxy)
        elif args.command == "status":
            return 0 if inspect_local_index(candidate) else 2
        else:
            build_new_collection(
                candidate,
                args.collection_name,
                no_proxy=args.no_proxy,
            )
    except Exception as exc:
        print(f"失败: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
