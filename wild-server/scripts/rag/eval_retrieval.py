"""
RAG 检索评测工具

功能：
1. 使用项目真实检索链路（app.spec.loader.RAGSpecLoader + config 中的
   embedding 配置）对内置或外部问题集逐条执行检索
2. 输出每条问题的 Top-K 命中分片：距离/分数、来源文件、标题路径、实体、内容摘要
3. 有标准答案时计算 Hit@K、Recall@K、MRR；同时保留距离、空召回等诊断指标
4. 生成 Markdown 评测报告到 scripts/reports/（eval_retrieval_<时间戳>.md），
   控制台输出通过 Tee 双写保存日志（eval_console_<时间戳>.txt）

运行方式（需在 wild-server 根目录）：

    $env:PYTHONPATH="."
    .\\.venv\\Scripts\\python.exe scripts\\rag\\eval_retrieval.py
    $env:PYTHONPATH="."; uv run --no-project python scripts/rag/eval_retrieval.py

说明：
- 默认只读已有的 storage/chroma 索引，不会自动同步或改写它。只有显式传入
  --sync-index 才会先按当前知识库同步线上索引。
- --embedding hash 会改用本地 HashEmbeddingFunction + 临时目录重建一个临时
  索引（不读线上向量，不污染 storage/chroma），仅用于离线 smoke 场景。
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

# 设置输出编码为 UTF-8（解决 Windows PowerShell 中文乱码），与 inspect 脚本保持一致
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SERVER_ROOT = Path(__file__).resolve().parents[2]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.spec.loader import (
    RAGSpecLoader,
    collect_markdown_paths,
    create_embedding_function,
)

# 与 app/services/agent_service.py 保持一致的路径与排除规则
_KB = SERVER_ROOT / "storage" / "knowledge_base"
BASE_SPEC_PATHS = [
    _KB / "BLUEPRINT-SPEC-MINIMAL.md",
]
DEFAULT_CASES_PATH = SERVER_ROOT / "evals" / "rag_retrieval_cases.json"


def get_rag_spec_paths() -> list[Path]:
    return collect_markdown_paths(_KB, exclude=BASE_SPEC_PATHS)


# ── 控制台输出双写（Tee），风格与 inspect_knowledge_chunks.py 保持一致 ──────────


class Tee:
    """将写入内容同时分发到多个流（控制台 + 日志文件），每次写入后 flush 保证双端一致。"""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            s.write(data)
            s.flush()

    def flush(self):
        for s in self.streams:
            s.flush()

    def isatty(self):
        return self.streams[0].isatty()

    def fileno(self):
        return self.streams[0].fileno()

    def __getattr__(self, name):
        return getattr(self.streams[0], name)


# ── 无 JSON 文件时的只读后备问题集 ───────────────────────────────────
# 正常评测使用 evals/rag_retrieval_cases.json；这里仅保证文件意外缺失时，
# 脚本仍能展示召回结果。后备问题没有 expectedSources，因此不会伪造 Recall@K。
DEFAULT_QUESTIONS: list[dict[str, str]] = [
    # 建筑类型
    {"id": "bt_pavilion", "query": "生成一个中式四角凉亭", "topic": "建筑类型-凉亭"},
    {"id": "bt_villa", "query": "现代风格的度假别墅怎么生成", "topic": "建筑类型-别墅"},
    {"id": "bt_tower", "query": "塔楼 tower 的生成语义入口与默认结构", "topic": "建筑类型-塔楼"},
    {"id": "bt_cabin", "query": "小木屋 cabins 的默认生成方式", "topic": "建筑类型-木屋"},
    {"id": "bt_courtyard", "query": "合院 courtyard 建筑如何生成", "topic": "建筑类型-合院"},
    {"id": "bt_residential", "query": "三层独栋住宅的默认构件与布局", "topic": "建筑类型-住宅"},
    {"id": "bt_dorm_hotel", "query": "宿舍楼和酒店这类居住建筑怎么配置", "topic": "建筑类型-居住"},
    {"id": "bt_office_school", "query": "办公楼和学校的建筑类型语义入口", "topic": "建筑类型-公共"},
    {"id": "bt_commercial", "query": "商业综合体、体育场馆等公共建筑怎么生成", "topic": "建筑类型-公共"},
    {"id": "bt_factory", "query": "工厂仓库这类工业建筑的默认生成参数", "topic": "建筑类型-工业"},
    {"id": "bt_agricultural", "query": "农业建筑 agricultural buildings 的语义入口", "topic": "建筑类型-农业"},
    # 构件组装
    {"id": "comp_window", "query": "默认窗的 geometry.components 参数有哪些", "topic": "构件-窗"},
    {"id": "comp_door", "query": "默认门的 leafMaterial 和 frameWidth 参数", "topic": "构件-门"},
    {"id": "comp_wall", "query": "墙体 wall 的 geometry.components 组装方式", "topic": "构件-墙"},
    {"id": "comp_railing", "query": "路径栏杆 postSpacing 与 railLevels 参数", "topic": "构件-栏杆"},
    {"id": "comp_roof", "query": "屋顶 span 和 depth 覆盖墙体的规则", "topic": "构件-屋顶"},
    {"id": "comp_curtain", "query": "玻璃幕墙怎么组装", "topic": "构件-幕墙"},
    {"id": "comp_opening", "query": "门窗洞口 opening 与 parentWall 的从属关系", "topic": "构件-洞口"},
    {"id": "comp_canopy", "query": "组合构件 canopy 雨棚怎么生成", "topic": "构件-雨棚"},
    {"id": "comp_bay_window", "query": "凸窗 bay_window 和飘窗怎么生成", "topic": "构件-凸窗"},
    {"id": "comp_structural", "query": "结构构件 structural components 有哪些", "topic": "构件-结构"},
    {"id": "boundary_engine", "query": "engine 当前不能写入 geometry.elements 的能力边界", "topic": "规格-能力边界"},
    # 材质
    {"id": "mat_residential", "query": "住宅默认材质配色 外墙涂料 屋顶瓦片", "topic": "材质-住宅"},
    {"id": "mat_public", "query": "公共建筑材质色板与玻璃幕墙配色", "topic": "材质-公共"},
    # 装配关系与模式
    {"id": "recipe_assembly", "query": "构件间允许的装配关系有哪些", "topic": "装配关系"},
    {"id": "recipe_template", "query": "组装模板 assembly templates 怎么用", "topic": "装配模板"},
    {"id": "recipe_style", "query": "门窗屋顶的风格参考", "topic": "风格参考"},
    {"id": "pattern_high_detail", "query": "高细节建筑生成模式", "topic": "生成模式"},
]


def load_questions(args_questions: str | None, limit: int | None) -> list[dict[str, Any]]:
    """加载评测问题。

    JSON 文件可以携带 ``expectedSources``，因此能计算真正的 Recall@K/MRR。
    纯文本文件只有问题，没有标准答案，只能用于人工查看召回结果。
    """
    path = Path(args_questions).resolve() if args_questions else DEFAULT_CASES_PATH
    if path:
        if not path.exists():
            if args_questions:
                raise SystemExit(f"错误: 问题文件不存在: {path}")
            questions = list(DEFAULT_QUESTIONS)
            print(f"警告: 默认 JSON 评测集不存在，改用 {len(questions)} 条无标准答案的后备问题。")
            return questions[:limit] if limit else questions

        if path.suffix.casefold() == ".json":
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise SystemExit(f"错误: 无法读取 JSON 评测集 {path}: {exc}") from exc
            questions = payload.get("cases") if isinstance(payload, dict) else None
            if not isinstance(questions, list) or not questions:
                raise SystemExit(f"错误: JSON 评测集必须包含非空 cases 数组: {path}")
            normalized: list[dict[str, Any]] = []
            for index, case in enumerate(questions, start=1):
                if not isinstance(case, dict) or not str(case.get("query") or "").strip():
                    raise SystemExit(f"错误: 第 {index} 条 case 缺少 query: {path}")
                expected_sources = case.get("expectedSources", [])
                if not isinstance(expected_sources, list):
                    raise SystemExit(f"错误: 第 {index} 条 expectedSources 必须是数组: {path}")
                normalized.append({
                    **case,
                    "id": str(case.get("id") or f"q{index}"),
                    "query": str(case["query"]).strip(),
                    "topic": str(case.get("topic") or "未分类"),
                    "expectedSources": [str(item) for item in expected_sources],
                    "requiredTerms": [str(item) for item in case.get("requiredTerms", [])],
                    "expectedAction": str(case.get("expectedAction") or "answer").lower(),
                })
            print(f"已加载带标准答案的 JSON 评测集: {len(normalized)} 条，来源 {path}")
            return normalized[:limit] if limit else normalized

        questions: list[dict[str, str]] = []
        for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "|" in line:
                qid, query = line.split("|", 1)
                questions.append({"id": qid.strip() or f"q{line_no}", "query": query.strip(), "topic": "外部问题"})
            else:
                questions.append({"id": f"q{line_no}", "query": line, "topic": "外部问题"})
        if not questions:
            raise SystemExit(f"错误: 问题文件为空: {path}")
        print(f"已从外部文件加载 {len(questions)} 条问题: {path}")
        return questions[:limit] if limit else questions


def build_loader(args: argparse.Namespace) -> tuple[RAGSpecLoader, Any | None]:
    """按真实链路装配 Loader，并把实验索引与正式 Chroma 隔离。"""
    try:
        from config import config
    except Exception as exc:
        raise SystemExit(
            f"错误: 无法加载 config（请在 wild-server 根目录运行并设置 PYTHONPATH=\".\"）: {exc}"
        )

    rag_spec_paths = get_rag_spec_paths()
    temp_handle: Any = None

    if args.embedding == "hash":
        # 离线降级：HashEmbeddingFunction 与线上 qwen embedding 向量空间不兼容，
        # 若直接打开线上集合会触发 index_signature 不匹配而重建索引（危险）。
        # 因此强制使用临时目录 + 独立集合，仅验证真实分片/检索链路，不读线上向量。
        temp_handle = TemporaryDirectory(ignore_cleanup_errors=True)
        embedding_function = create_embedding_function(
            api_key="",
            base_url="",
            model_name="",
            allow_hash_fallback=True,
        )
        print("警告: --embedding hash 只验证流程，不代表真实语义召回质量。")
    else:
        embedding_function = create_embedding_function(
            api_key=config.embedding.api_key,
            base_url=config.embedding.base_url,
            model_name=config.embedding.name,
            allow_hash_fallback=config.rag.allow_hash_fallback,
        )
        if type(embedding_function).__name__ == "HashEmbeddingFunction":
            print(
                "警告: auto 因配置缺少真实 embedding 凭据而降级为 HashEmbeddingFunction；"
                "本次结果不能作为语义召回质量结论。"
            )
    use_temporary_index = args.embedding == "hash" or args.temporary_index
    if use_temporary_index:
        if temp_handle is None:
            temp_handle = TemporaryDirectory(ignore_cleanup_errors=True)
        persist_dir = str(Path(temp_handle.name))
        collection_name = f"wild_eval_retrieval_{time.strftime('%Y%m%d_%H%M%S')}"
        print("索引模式: 临时重建；退出脚本后自动清理，不修改 storage/chroma。")
    else:
        persist_dir = str(
            Path(config.rag.persist_dir)
            if Path(config.rag.persist_dir).is_absolute()
            else SERVER_ROOT / config.rag.persist_dir
        )
        collection_name = config.rag.collection_name

    print(f"加载 RAG Loader: persist_dir={persist_dir}, collection={collection_name}, namespace={args.namespace}")
    print(f"embedding: {type(embedding_function).__name__}")

    args.effective_chunk_size = args.chunk_size or config.rag.chunk_size
    args.effective_chunk_overlap = (
        args.chunk_overlap
        if args.chunk_overlap is not None
        else config.rag.chunk_overlap
    )
    loader = RAGSpecLoader(
        base_paths=[str(p) for p in BASE_SPEC_PATHS],
        rag_paths=[str(p) for p in rag_spec_paths],
        persist_dir=persist_dir,
        collection_name=collection_name,
        embedding_function=embedding_function,
        top_k=args.top_k,
        chunk_size=args.effective_chunk_size,
        chunk_overlap=args.effective_chunk_overlap,
        max_context_chars=config.rag.max_context_chars,
        namespace=args.namespace,
        # 所有临时索引都必须在本次运行中构建；正式索引只在显式授权时同步。
        auto_sync=use_temporary_index or args.sync_index,
    )
    if not use_temporary_index and not args.sync_index:
        attach_existing_collection_read_only(loader)
    args.index_mode = (
        "临时重建"
        if use_temporary_index
        else "同步后评测"
        if args.sync_index
        else "只读已有索引"
    )
    return loader, temp_handle


def attach_existing_collection_read_only(loader: RAGSpecLoader) -> None:
    """只打开已有集合，并在签名不兼容时停止，而不是让 Loader 自动重建。

    生产 Loader 的 ``_get_collection()`` 会在 embedding 或分片签名变化时删除旧集合
    后重建，这是服务启动同步时的正确行为，却不适合默认评测。评测脚本因此先安全
    挂载已有集合；需要重建时必须显式选择临时索引或 ``--sync-index``。
    """
    try:
        import chromadb
    except ImportError as exc:
        raise SystemExit("错误: 缺少 chromadb 依赖，请先安装 wild-server 依赖") from exc

    if not loader._persist_dir.exists():
        raise SystemExit(
            f"错误: 正式索引目录不存在: {loader._persist_dir}。"
            "可使用 --temporary-index 安全构建实验索引。"
        )
    client = chromadb.PersistentClient(path=str(loader._persist_dir))
    try:
        collection = client.get_collection(
            name=loader._collection_name,
            embedding_function=loader._embedding_function,
        )
    except Exception as exc:
        raise SystemExit(
            f"错误: 无法只读打开已有集合 {loader._collection_name}: {exc}。"
            "可检查配置，或使用 --temporary-index。"
        ) from exc

    expected_signature = loader._index_signature()
    existing_signature = (collection.metadata or {}).get("index_signature")
    if existing_signature != expected_signature:
        raise SystemExit(
            "错误: 当前 embedding/分片配置与已有索引签名不一致。"
            "默认评测为保护正式索引不会自动重建；请使用 --temporary-index 做实验，"
            "或确认确需更新正式库后使用 --sync-index。"
        )
    loader._client = client
    loader._collection = collection


def indexed_chunk_count(loader: RAGSpecLoader) -> int:
    """统计当前 namespace 已存在的索引条数，不触发知识库同步。"""
    collection = loader._get_collection()
    result = collection.get(
        where={"namespace": loader._namespace},
        include=["metadatas"],
    )
    return len(result.get("ids") or [])


def summarize_document(document: str, max_chars: int = 120) -> str:
    """生成内容摘要：取正文前 max_chars 字符，压成单行。"""
    text = " ".join(document.split())
    if len(text) > max_chars:
        return text[: max_chars - 3] + "..."
    return text


def _matches_expected_source(hit: dict[str, Any], expected: str) -> bool:
    """用文件名或相对路径匹配标准答案，Windows/Linux 路径均可。"""
    expected_normalized = expected.replace("\\", "/").casefold()
    source = str(hit.get("source") or "").replace("\\", "/").casefold()
    source_path = str(hit.get("path") or "").replace("\\", "/").casefold()
    return source.endswith(expected_normalized) or source_path.endswith(expected_normalized)


def score_ranked_hits(
    hits: list[dict[str, Any]],
    expected_sources: list[str],
) -> dict[str, Any] | None:
    """计算单题的来源级检索指标；没有标准答案时返回 ``None``。

    - Hit@K：Top-K 至少命中一个标准来源。
    - Recall@K：标准来源中有多少比例出现在 Top-K。
    - Reciprocal rank：第一个正确来源排名的倒数，供最终计算 MRR。
    """
    expected = list(dict.fromkeys(item for item in expected_sources if item))
    if not expected:
        return None
    matched = {
        source
        for source in expected
        if any(_matches_expected_source(hit, source) for hit in hits)
    }
    first_rank = next(
        (
            rank
            for rank, hit in enumerate(hits, start=1)
            if any(_matches_expected_source(hit, source) for source in expected)
        ),
        None,
    )
    return {
        "hit": bool(matched),
        "recall": len(matched) / len(expected),
        "reciprocal_rank": 0.0 if first_rank is None else 1.0 / first_rank,
        "first_relevant_rank": first_rank,
        "matched_sources": sorted(matched),
        "missing_sources": [source for source in expected if source not in matched],
    }


def select_ranked_parent_groups(
    hits: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    """把相邻 part 折叠回父 section，避免邻片占掉 Top-K 名额。

    ``RAGSpecLoader`` 会在一个语义命中前后补相邻 part。它们属于同一次父块
    命中，不应该在 Recall@K 里被当成多个独立排名。
    """
    selected: list[dict[str, Any]] = []
    seen_groups: set[str] = set()
    for index, hit in enumerate(hits):
        group_id = str(hit.get("parent_chunk_id") or f"standalone:{index}")
        if group_id in seen_groups:
            continue
        seen_groups.add(group_id)
        selected.append(hit)
        if len(selected) >= top_k:
            break
    return selected


def run_eval(
    loader: RAGSpecLoader,
    questions: list[dict[str, Any]],
    top_k: int,
    *,
    use_case_filters: bool = True,
) -> dict[str, Any]:
    """逐条执行检索，返回命中明细与汇总统计。"""
    results: list[dict[str, Any]] = []
    empty_top1 = 0
    retrieval_errors = 0
    all_distances: list[float] = []
    top1_distances: list[float] = []
    entity_counter: Counter[str] = Counter()
    source_counter: Counter[str] = Counter()

    for q in questions:
        qid = q["id"]
        query = q["query"]
        try:
            metadata_filter = q.get("metadataFilter") if use_case_filters else None
            hits = loader.retrieve(query, metadata_filter=metadata_filter)
        except Exception as exc:
            retrieval_errors += 1
            results.append({**q, "error": f"{type(exc).__name__}: {exc}", "hits": []})
            print(f"[异常] {qid}: {query!r} -> {type(exc).__name__}: {exc}")
            continue

        entries = []
        if not hits:
            empty_top1 += 1
        else:
            if hits[0].distance is not None:
                top1_distances.append(hits[0].distance)
            for rank, hit in enumerate(hits, start=1):
                metadata = hit.metadata or {}
                distance = hit.distance
                if distance is not None:
                    all_distances.append(distance)
                source = str(metadata.get("source") or "-")
                entity = str(metadata.get("entity_name") or "(无)")
                entity_counter[entity] += 1
                source_counter[source] += 1
                entries.append(
                    {
                        "rank": rank,
                        "chunk_id": hit.id,
                        "distance": distance,
                        "source": source,
                        "path": str(metadata.get("path") or "-"),
                        "heading": str(metadata.get("heading") or "-"),
                        "heading_path": str(metadata.get("heading_path") or "-"),
                        "entity": entity,
                        "doc_type": str(metadata.get("doc_type") or "-"),
                        "status": str(metadata.get("status") or "-"),
                        "authority": str(metadata.get("authority") or "-"),
                        "parent_chunk_id": str(metadata.get("parent_chunk_id") or ""),
                        "summary": summarize_document(hit.document),
                    }
                )

        # Loader 会补相邻 part；先按 parent_chunk_id 折叠，再取前 K 个语义父块。
        ranked_entries = select_ranked_parent_groups(entries, top_k)
        score = score_ranked_hits(ranked_entries, q.get("expectedSources", []))
        required_terms = q.get("requiredTerms", [])
        # requiredTerms 检查实际注入上下文；相邻 part 也属于本次 Top-K 命中的补充内容。
        ranked_text = "\n".join(hit.document for hit in hits).casefold()
        missing_terms = [term for term in required_terms if term.casefold() not in ranked_text]
        results.append({
            **q,
            "error": None,
            "hits": entries,
            "score": score,
            "missing_terms": missing_terms,
        })
        if entries:
            top1 = entries[0]
            print(
                f"[OK] {qid}: {query!r} -> {len(entries)} hits, "
                f"top1={top1['source']} / {top1['heading'][:40]}, "
                f"dist={'-' if top1['distance'] is None else round(top1['distance'], 4)}"
            )
        else:
            print(f"[空] {qid}: {query!r} -> 0 hits")

    total = len(questions)
    avg_all = sum(all_distances) / len(all_distances) if all_distances else None
    avg_top1 = sum(top1_distances) / len(top1_distances) if top1_distances else None
    # 同源率：平均每个问题 Top-K 命中中来自同一文件的占比（高说明召回集中，可能漏召回）
    same_source_ratios = []
    for r in results:
        if len(r["hits"]) > 1:
            c = Counter(h["source"] for h in r["hits"])
            same_source_ratios.append(c.most_common(1)[0][1] / len(r["hits"]))

    graded_scores = [r["score"] for r in results if r.get("score") is not None]
    negative_results = [
        result for result in results if result.get("expectedAction") == "reject"
    ]
    negative_rejected = sum(1 for result in negative_results if not result.get("hits"))
    stats = {
        "total_questions": total,
        "empty_top1": empty_top1,
        "empty_top1_rate": empty_top1 / total if total else 0.0,
        "retrieval_errors": retrieval_errors,
        "avg_all_distance": avg_all,
        "avg_top1_distance": avg_top1,
        "avg_hits_per_question": sum(len(r["hits"]) for r in results) / total if total else 0.0,
        "avg_same_source_ratio": sum(same_source_ratios) / len(same_source_ratios) if same_source_ratios else None,
        "entity_distribution": entity_counter.most_common(15),
        "source_distribution": source_counter.most_common(15),
        "graded_questions": len(graded_scores),
        "hit_at_k": (
            sum(1 for score in graded_scores if score["hit"]) / len(graded_scores)
            if graded_scores else None
        ),
        "recall_at_k": (
            sum(score["recall"] for score in graded_scores) / len(graded_scores)
            if graded_scores else None
        ),
        "mrr": (
            sum(score["reciprocal_rank"] for score in graded_scores) / len(graded_scores)
            if graded_scores else None
        ),
        "term_complete_questions": sum(
            1
            for result in results
            if result.get("requiredTerms")
            and not result.get("error")
            and result.get("missing_terms") == []
        ),
        "term_graded_questions": sum(1 for result in results if result.get("requiredTerms")),
        "negative_questions": len(negative_results),
        # 没有阈值时这里只统计空召回；真正的 Gate 正确率由校准脚本按阈值计算。
        "negative_empty_reject_rate": (
            negative_rejected / len(negative_results) if negative_results else None
        ),
    }
    return {"results": results, "stats": stats}


def signals_markdown(stats: dict[str, Any]) -> list[str]:
    """基于统计自动生成观察信号，帮助阅读者快速定位检索问题。"""
    lines: list[str] = []
    if stats["empty_top1_rate"] >= 0.2:
        lines.append(
            f"- ⚠️ 空召回率 {stats['empty_top1_rate']:.0%}（{stats['empty_top1']}/{stats['total_questions']}）较高："
            "请检查问题用词是否偏离知识库关键词、embedding 质量，以及 namespace 是否匹配索引。"
        )
    elif stats["empty_top1"] > 0:
        lines.append(
            f"- 存在 {stats['empty_top1']} 条空召回问题，见逐题明细中标记为 [空] 的条目。"
        )
    if stats["retrieval_errors"]:
        lines.append(
            f"- 检索异常 {stats['retrieval_errors']} 条：多为 embedding 服务/网络问题，"
            "不影响其余问题的评测结论。"
        )
    if stats["avg_same_source_ratio"] is not None and stats["avg_same_source_ratio"] > 0.6:
        lines.append(
            f"- 平均同源率 {stats['avg_same_source_ratio']:.0%} 偏高：Top-K 大多来自同一文件，"
            "可能存在漏召回（相关内容分散在多个文件时未被召回）。"
        )
    if stats["avg_all_distance"] is not None and stats["avg_all_distance"] > 1.0:
        lines.append(
            f"- 平均命中距离 {stats['avg_all_distance']:.3f} 较大：命中分片与问题整体相关度偏低，"
            "可检查 embedding 配置或分片粒度。"
        )
    if stats["hit_at_k"] is not None and stats["hit_at_k"] < 0.8:
        lines.append(
            f"- Hit@K 为 {stats['hit_at_k']:.1%}，低于 80%：优先查看未命中的标准来源，"
            "再判断是知识缺失、分片语义过弱、过滤条件错误还是 embedding 排序问题。"
        )
    if not lines:
        lines.append("- 未触发明显异常信号，建议结合逐题明细人工复核命中质量。")
    return lines


def to_markdown(
    eval_data: dict[str, Any],
    args: argparse.Namespace,
    loader: RAGSpecLoader,
) -> str:
    stats = eval_data["stats"]
    results = eval_data["results"]
    sync = loader.last_sync_stats

    lines: list[str] = [
        "# RAG 检索评测报告",
        "",
        f"- 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 索引: `{args.namespace}` / collection=`{args.collection_name}`",
        f"- embedding: `{args.embedding_type}`",
        f"- Top-K: {args.top_k}",
        f"- 分片参数: chunk_size={args.effective_chunk_size}, chunk_overlap={args.effective_chunk_overlap}",
        f"- 问题数: {stats['total_questions']}",
        f"- 索引模式: `{args.index_mode}`",
        f"- 当前 namespace 分片数: {args.indexed_chunk_count}",
        f"- 本次同步: updated={sync.get('updated', 0)}, deleted={sync.get('deleted', 0)}",
        "",
    ]

    same_source_text = (
        "-"
        if stats["avg_same_source_ratio"] is None
        else f"{stats['avg_same_source_ratio']:.0%}"
    )
    hit_text = "-" if stats["hit_at_k"] is None else f"{stats['hit_at_k']:.1%}"
    recall_text = "-" if stats["recall_at_k"] is None else f"{stats['recall_at_k']:.1%}"
    mrr_text = "-" if stats["mrr"] is None else f"{stats['mrr']:.3f}"
    lines += [
        "## 汇总统计",
        "",
        "| 指标 | 值 | 说明 |",
        "| --- | --- | --- |",
        f"| 总问题数 | {stats['total_questions']} | 本次评测执行的查询数量 |",
        f"| 空召回数（Top-1 为空） | {stats['empty_top1']} | 完全未召回任何分片的问题数 |",
        f"| 空召回率 | {stats['empty_top1_rate']:.1%} | 越低越好；>20% 需重点排查 |",
        f"| 检索异常数 | {stats['retrieval_errors']} | embedding 服务/网络导致的查询失败 |",
        f"| 平均命中距离 | {stats['avg_all_distance'] if stats['avg_all_distance'] is not None else '-'} | 越小越相关（跨 embedding 不可直接比） |",
        f"| 平均 Top-1 距离 | {stats['avg_top1_distance'] if stats['avg_top1_distance'] is not None else '-'} | 首条命中与问题的相关度 |",
        f"| 每问平均命中数 | {stats['avg_hits_per_question']:.2f} | 反映 Top-K 被有效填充的程度 |",
        f"| 平均同源率 | {same_source_text} | 同文件命中占比；过高提示漏召回 |",
        f"| 已自动判分问题数 | {stats['graded_questions']} | 有 expectedSources 标准答案的问题数 |",
        f"| Hit@{args.top_k} | {hit_text} | 至少命中一个标准来源的问题比例 |",
        f"| Recall@{args.top_k} | {recall_text} | 每题标准来源召回比例的宏平均 |",
        f"| MRR@{args.top_k} | {mrr_text} | 第一条正确结果越靠前，值越接近 1 |",
        f"| 关键词完整问题 | {stats['term_complete_questions']}/{stats['term_graded_questions']} | requiredTerms 全部出现在 Top-K 的问题数 |",
        f"| 负样本数 | {stats['negative_questions']} | expectedAction=reject 的无关问题数 |",
        f"| 负样本空召回率 | {stats['negative_empty_reject_rate'] if stats['negative_empty_reject_rate'] is not None else '-'} | 未配置阈值前只表示完全空召回，不等于最终 Gate 正确率 |",
        "",
    ]

    lines += ["## 信号提示", ""]
    lines += signals_markdown(stats)
    lines += [""]

    lines += ["## 按实体分组的命中分布", ""]
    if stats["entity_distribution"]:
        lines += ["| 实体 | 命中次数 |", "| --- | --- |"]
        for entity, count in stats["entity_distribution"]:
            lines.append(f"| {entity} | {count} |")
    else:
        lines.append("无命中。")
    lines += [""]

    lines += ["## 按文件分组的命中分布", ""]
    if stats["source_distribution"]:
        lines += ["| 文件 | 命中次数 |", "| --- | --- |"]
        for source, count in stats["source_distribution"]:
            lines.append(f"| {source} | {count} |")
    else:
        lines.append("无命中。")
    lines += [""]

    lines += ["## 逐题明细", ""]
    for idx, r in enumerate(results, start=1):
        lines.append(f"### Q{idx}. {r['id']} — {r['query']}")
        lines.append("")
        lines.append(f"- 主题: {r['topic']}")
        if r.get("expectedSources"):
            lines.append(f"- 标准来源: `{', '.join(r['expectedSources'])}`")
        if r.get("metadataFilter") and not args.ignore_case_filters:
            lines.append(f"- 本题过滤条件: `{json.dumps(r['metadataFilter'], ensure_ascii=False)}`")
        if r["error"]:
            lines.append(f"- 检索异常: {r['error']}")
            lines.append("")
            continue
        if not r["hits"]:
            lines.append("- **空召回**：没有命中任何分片。")
            lines.append("")
            continue
        if r.get("score") is not None:
            score = r["score"]
            verdict = "✅ 命中" if score["hit"] else "❌ 未命中"
            rank_text = score["first_relevant_rank"] if score["first_relevant_rank"] is not None else "-"
            lines.append(
                f"- 自动判分: {verdict}；Recall@{args.top_k}={score['recall']:.1%}；"
                f"第一条正确结果排名={rank_text}"
            )
        if r.get("missing_terms"):
            lines.append(f"- Top-K 缺少要求关键词: `{', '.join(r['missing_terms'])}`")
        lines.append(
            "| 排名 | 距离 | 来源文件 | 标题路径 | 实体 | 内容摘要 |"
        )
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for hit in r["hits"]:
            dist = "-" if hit["distance"] is None else f"{hit['distance']:.4f}"
            heading = (hit["heading_path"] or hit["heading"]).replace("|", "\\|")[:60]
            lines.append(
                f"| {hit['rank']} | {dist} | {hit['source']} | {heading} | {hit['entity']} | {hit['summary'].replace('|', '\\|')[:80]} |"
            )
        lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="RAG 检索评测工具（真实检索链路）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例用法:

  # 使用内置问题集评测线上索引（默认 top_k=5）
  python scripts/rag/eval_retrieval.py

  # 只跑前 10 条问题
  python scripts/rag/eval_retrieval.py --limit 10

  # 自定义 Top-K
  python scripts/rag/eval_retrieval.py --top-k 8

  # 从外部文件加载问题（每行一条，支持 id|query 或纯 query）
  python scripts/rag/eval_retrieval.py --questions my_questions.txt

  # 指定逻辑命名空间（默认 wild_spec，与线上索引一致）
  python scripts/rag/eval_retrieval.py --namespace wild_spec

  # 离线 smoke：本地 hash embedding + 临时索引，不读线上向量
  python scripts/rag/eval_retrieval.py --embedding hash

  # 真实 embedding + 临时索引，可安全实验分片参数
  python scripts/rag/eval_retrieval.py --temporary-index --chunk-size 600 --chunk-overlap 100

  # 自定义报告与日志输出路径
  python scripts/rag/eval_retrieval.py --output reports/eval.md --log-output reports/eval.log

  # 关闭控制台日志保存
  python scripts/rag/eval_retrieval.py --no-log-output
""",
    )
    parser.add_argument(
        "--questions",
        type=str,
        help="评测集路径；JSON 可带标准答案，纯文本只做人工检查（默认 evals/rag_retrieval_cases.json）",
    )
    parser.add_argument("--limit", type=int, help="限制评测问题数（默认全部）")
    parser.add_argument("--top-k", type=int, default=5, help="每个问题保留的 Top-K 命中数（默认 5）")
    parser.add_argument("--namespace", type=str, default="wild_spec", help="逻辑命名空间（默认 wild_spec，必须与索引一致）")
    parser.add_argument("--embedding", choices=["auto", "hash"], default="auto", help="embedding 选择：auto 用 config 真实配置（默认）；hash 用本地 HashEmbeddingFunction + 临时索引")
    parser.add_argument(
        "--temporary-index",
        action="store_true",
        help="用当前知识库重建临时索引；auto 模式会调用真实 embedding，但不修改 storage/chroma",
    )
    parser.add_argument("--chunk-size", type=int, help="临时索引分片长度；默认使用 config.rag.chunk_size")
    parser.add_argument("--chunk-overlap", type=int, help="临时索引普通文本重叠长度；默认使用 config.rag.chunk_overlap")
    parser.add_argument(
        "--sync-index",
        action="store_true",
        help="评测前同步真实索引（默认只读已有线上索引；hash 临时索引不受此参数影响）",
    )
    parser.add_argument(
        "--ignore-case-filters",
        action="store_true",
        help="忽略 JSON case 的 metadataFilter，用于观察纯向量检索基线",
    )
    parser.add_argument("--output", type=Path, help="报告 Markdown 输出路径（默认 scripts/reports/eval_retrieval_<时间戳>.md）")
    parser.add_argument("--json-output", type=Path, help="同时输出机器可读 JSON，供阈值校准和 CI 门禁使用")
    parser.add_argument("--log-output", type=Path, help="控制台日志保存路径（默认 scripts/reports/eval_console_<时间戳>.txt）")
    parser.add_argument("--no-log-output", action="store_true", help="不保存控制台日志（默认会保存）")
    args = parser.parse_args()

    if args.top_k < 1:
        raise SystemExit("错误: --top-k 必须 >= 1")
    if args.limit is not None and args.limit < 1:
        raise SystemExit("错误: --limit 必须 >= 1")
    if args.chunk_size is not None and args.chunk_size < 200:
        raise SystemExit("错误: --chunk-size 必须 >= 200（与 MarkdownChunker 下限一致）")
    if args.chunk_overlap is not None and args.chunk_overlap < 0:
        raise SystemExit("错误: --chunk-overlap 必须 >= 0")
    if (args.chunk_size is not None or args.chunk_overlap is not None) and not (
        args.temporary_index or args.embedding == "hash"
    ):
        raise SystemExit(
            "错误: 分片参数只对新建索引生效。请加 --temporary-index，避免为实验改写正式索引。"
        )
    if args.embedding == "hash" and args.sync_index:
        print("提示: hash 模式始终只构建临时索引，--sync-index 不会修改线上索引。")

    # ── 控制台日志双写（Tee） ──
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = None
    if not args.no_log_output:
        if args.log_output:
            log_path = args.log_output.resolve()
        else:
            reports_dir = Path(__file__).resolve().parents[1] / "reports"
            log_path = reports_dir / f"eval_console_{timestamp}.txt"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_file = open(log_path, "w", encoding="utf-8")
        except OSError as exc:
            print(f"警告: 无法创建控制台日志文件 {log_path}: {exc}")
        else:
            sys.stdout = Tee(sys.stdout, log_file)
            print(f"控制台输出将同时保存到: {log_path}")

    questions = load_questions(args.questions, args.limit)
    loader, temp_handle = build_loader(args)
    args.collection_name = getattr(loader, "_collection_name", "?")
    args.embedding_type = type(loader._embedding_function).__name__ if hasattr(loader, "_embedding_function") else "?"

    # 只读模式下 last_sync_stats 仍为 0，因此直接统计当前 namespace 的已有记录。
    total_chunks = indexed_chunk_count(loader)
    args.indexed_chunk_count = total_chunks
    if total_chunks == 0:
        print(
            f"错误: namespace='{args.namespace}' 下没有分片（total=0）。"
            "请检查 --namespace 是否与索引一致；若知识库尚未建索引，可确认配置后显式使用 --sync-index。"
        )
        return 2

    print(f"索引就绪: 总分片 {total_chunks}，知识库来源文件 {len(get_rag_spec_paths())} 个")
    eval_data = run_eval(
        loader,
        questions,
        args.top_k,
        use_case_filters=not args.ignore_case_filters,
    )
    stats = eval_data["stats"]
    quality_summary = (
        "未提供标准答案"
        if stats["hit_at_k"] is None
        else f"Hit@{args.top_k}={stats['hit_at_k']:.1%}, "
             f"Recall@{args.top_k}={stats['recall_at_k']:.1%}, MRR={stats['mrr']:.3f}"
    )
    print(
        f"\n汇总: {quality_summary}; 空召回 {stats['empty_top1']}/{stats['total_questions']} "
        f"({stats['empty_top1_rate']:.1%}), 异常 {stats['retrieval_errors']}"
    )

    # ── 写入 Markdown 报告 ──
    if args.output:
        report_path = args.output.resolve()
    else:
        reports_dir = Path(__file__).resolve().parents[1] / "reports"
        report_path = reports_dir / f"eval_retrieval_{timestamp}.md"
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        md_content = to_markdown(eval_data, args, loader)
        report_path.write_text(md_content, encoding="utf-8")
        print(f"\n报告文件已生成: {report_path} ({len(md_content)} 字符)")
    except OSError as exc:
        print(f"警告: 无法写入报告文件 {report_path}: {exc}")

    if args.json_output:
        json_payload = {
            **eval_data,
            "run": {
                "embedding": args.embedding_type,
                "index_signature": loader._index_signature(),
                "top_k": args.top_k,
                "chunk_size": args.effective_chunk_size,
                "chunk_overlap": args.effective_chunk_overlap,
                "namespace": args.namespace,
            },
        }
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(json_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"机器可读评测结果已生成: {args.json_output.resolve()}")

    if log_path:
        print(f"控制台日志已保存: {log_path}")
    if stats["retrieval_errors"]:
        print(
            "错误: 本次评测存在检索异常，报告仅用于排错，不能作为召回率基线。"
        )
        return 3
    return 0


if __name__ == "__main__":
    exit(main())
