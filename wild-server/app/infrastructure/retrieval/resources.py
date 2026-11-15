"""知识库加载器构建；调用方显式初始化，不在模块导入时创建资源。"""
from app.paths import SERVER_ROOT
from pathlib import Path
from loguru import logger
from config import config
from app.infrastructure.observability.trace import record_rag_warning
from app.infrastructure.retrieval.loader import FileSpecLoader
from app.infrastructure.retrieval.loader import RAGSpecLoader
from app.infrastructure.retrieval.loader import collect_markdown_paths
from app.infrastructure.retrieval.loader import create_embedding_function


_SERVER_ROOT = SERVER_ROOT  # wild-server/


_KB = _SERVER_ROOT / "storage" / "knowledge_base"


BASE_SPEC_PATHS = [
    _KB / "knowledge" / "protocol" / "blueprint-skeleton.md",
    _KB / "knowledge" / "protocol" / "generation-redlines.md",
]


def get_rag_spec_paths() -> list[Path]:
    """扫描知识库 Markdown，并排除已经完整注入的基础规范。"""
    return collect_markdown_paths(_KB, exclude=BASE_SPEC_PATHS)


def create_spec_loader():
    """按配置创建 RAG Loader，初始化失败时降级为基础文件 Loader。"""
    if config.rag.enabled:
        try:
            persist_dir = Path(config.rag.persist_dir)
            if not persist_dir.is_absolute():
                persist_dir = _SERVER_ROOT / persist_dir

            embedding_function = create_embedding_function(
                api_key=config.embedding.api_key,
                base_url=config.embedding.base_url,
                model_name=config.embedding.name,
                allow_hash_fallback=config.rag.allow_hash_fallback,
                timeout=config.embedding.timeout,
                max_retries=config.embedding.max_retries,
            )
            rag_spec_paths = get_rag_spec_paths()
            loader = RAGSpecLoader(
                base_paths=[str(p) for p in BASE_SPEC_PATHS],
                rag_paths=[str(p) for p in rag_spec_paths],
                persist_dir=str(persist_dir),
                collection_name=config.rag.collection_name,
                embedding_function=embedding_function,
                top_k=config.rag.top_k,
                chunk_size=config.rag.chunk_size,
                chunk_overlap=config.rag.chunk_overlap,
                max_context_chars=config.rag.max_context_chars,
                # 索引同步移出模块导入路径：Loader 构造只做本地切分，
                # 不发起任何 embedding 请求，服务可立即对外提供。
                auto_sync=False,
            )
            logger.info(
                f"RAGSpecLoader: 已启用 Chroma, persist_dir={persist_dir}, "
                f"collection={config.rag.collection_name}"
            )
            sync_stats = loader.last_sync_stats
            logger.info(
                "RAG 索引同步: "
                f"total={sync_stats['total']}, "
                f"updated={sync_stats['updated']}, "
                f"deleted={sync_stats['deleted']}"
                f"{'（将转入后台线程增量同步，不阻塞服务启动）' if config.rag.auto_sync else '（自动同步已关闭）'}"
            )
            if isinstance(embedding_function, object) and embedding_function.__class__.__name__ == "HashEmbeddingFunction":
                logger.warning("RAGSpecLoader: 当前使用 hash fallback embedding，仅适合本地 smoke test")
                record_rag_warning(
                    "hash_embedding_fallback",
                    "当前使用 hash fallback embedding；仅适合本地 smoke test，"
                    "检索门禁距离阈值在该模式下无效。",
                )
            if config.rag.auto_sync:
                # 后台线程完成增量同步；embedding 慢/超时不再阻塞服务启动。
                # 同步失败只留下"部分可用"索引，检索自动降级为基础规范。
                loader.start_background_sync()
            return loader
        except Exception as exc:
            logger.warning(
                "⚠️  RAG 向量索引不可用，已降级为全量文件注入模式（FileSpecLoader）。"
            )
            logger.warning(f"  原因: {type(exc).__name__}: {exc}")
            logger.warning(
                "  请检查: EMBEDDING__NAME / EMBEDDING__API_KEY / EMBEDDING__BASE_URL"
                " 配置是否正确，以及 embedding 服务是否可达。"
            )
            record_rag_warning(
                "rag_index_unavailable",
                f"RAG 向量索引不可用，已降级为全量文件注入模式：{type(exc).__name__}: {exc}",
            )
            logger.error(
                "RAGSpecLoader 初始化失败，退回 FileSpecLoader: {}: {}",
                type(exc).__name__, exc,
            )

    return FileSpecLoader([str(p) for p in BASE_SPEC_PATHS])
