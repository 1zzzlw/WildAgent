"""
RAG 检索评测工具

功能：
1. 使用项目真实检索链路（app.spec.loader.RAGSpecLoader + config 中的
   embedding 配置）对内置或外部问题集逐条执行检索
2. 输出每条问题的 Top-K 命中分片：距离/分数、来源文件、标题路径、实体、内容摘要
3. 汇总评测统计：总分片数、平均命中距离、Top-1 空召回率、按实体/文件分组命中分布
4. 生成 Markdown 评测报告到 scripts/reports/（eval_retrieval_<时间戳>.md），
   控制台输出通过 Tee 双写保存日志（eval_console_<时间戳>.txt）

运行方式（需在 wild-server 根目录）：

    $env:PYTHONPATH="."
    .\\.venv\\Scripts\\python.exe scripts\\rag\\eval_retrieval.py
    $env:PYTHONPATH="."; uv run --no-project python scripts/rag/eval_retrieval.py

说明：
- 默认读取线上持久化索引 storage/chroma（集合 wild_knowledge_base），并使用
  config.embedding 配置的真实语义 embedding；若 EMBEDDING__API_KEY 缺失或
  embedding 服务不可达，脚本会给出清晰报错与降级方案。
- --embedding hash 会改用本地 HashEmbeddingFunction + 临时目录重建一个临时
  索引（不读线上向量，不污染 storage/chroma），仅用于离线 smoke 场景。
"""
from __future__ import annotations

import argparse
import io
import sys
import time
from collections import Counter, defaultdict
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


# ── 内置问题集（覆盖建筑类型 / 构件组装 / 材质 / 装配关系 / 规格边界等主题） ──────
# topic 仅为人工标注的主题域，用于报告分组与阅读提示，不参与自动判分。
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


def load_questions(args_questions: str | None, limit: int | None) -> list[dict[str, str]]:
    """加载问题集：--questions 指定外部文件（每行一条，支持 id|query 或纯 query），否则用内置集。"""
    if args_questions:
        path = Path(args_questions).resolve()
        if not path.exists():
            raise SystemExit(f"错误: 问题文件不存在: {path}")
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

    questions = list(DEFAULT_QUESTIONS)
    if limit:
        questions = questions[:limit]
    print(f"使用内置问题集: {len(questions)} 条（可用 --questions 加载自定义问题）")
    return questions


def build_loader(args: argparse.Namespace) -> tuple[RAGSpecLoader, Path | None]:
    """按真实链路装配 RAGSpecLoader；--embedding hash 时使用临时索引（离线 smoke）。"""
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
        persist_dir = str(Path(temp_handle.name))
        collection_name = f"wild_eval_retrieval_{time.strftime('%Y%m%d_%H%M%S')}"
        print("警告: --embedding hash 使用临时索引（本地 HashEmbeddingFunction），不读取线上向量。")
    else:
        embedding_function = create_embedding_function(
            api_key=config.embedding.api_key,
            base_url=config.embedding.base_url,
            model_name=config.embedding.name,
            allow_hash_fallback=config.rag.allow_hash_fallback,
        )
        persist_dir = str(
            Path(config.rag.persist_dir)
            if Path(config.rag.persist_dir).is_absolute()
            else SERVER_ROOT / config.rag.persist_dir
        )
        collection_name = config.rag.collection_name

    print(f"加载 RAG Loader: persist_dir={persist_dir}, collection={collection_name}, namespace={args.namespace}")
    print(f"embedding: {type(embedding_function).__name__}")

    loader = RAGSpecLoader(
        base_paths=[str(p) for p in BASE_SPEC_PATHS],
        rag_paths=[str(p) for p in rag_spec_paths],
        persist_dir=persist_dir,
        collection_name=collection_name,
        embedding_function=embedding_function,
        top_k=args.top_k,
        chunk_size=config.rag.chunk_size,
        chunk_overlap=config.rag.chunk_overlap,
        max_context_chars=config.rag.max_context_chars,
        namespace=args.namespace,
    )
    return loader, temp_handle


def summarize_document(document: str, max_chars: int = 120) -> str:
    """生成内容摘要：取正文前 max_chars 字符，压成单行。"""
    text = " ".join(document.split())
    if len(text) > max_chars:
        return text[: max_chars - 3] + "..."
    return text


def run_eval(loader: RAGSpecLoader, questions: list[dict[str, str]], top_k: int) -> dict[str, Any]:
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
            hits = loader.retrieve(query, metadata_filter=None)
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
                        "distance": distance,
                        "source": source,
                        "heading": str(metadata.get("heading") or "-"),
                        "heading_path": str(metadata.get("heading_path") or "-"),
                        "entity": entity,
                        "doc_type": str(metadata.get("doc_type") or "-"),
                        "status": str(metadata.get("status") or "-"),
                        "authority": str(metadata.get("authority") or "-"),
                        "summary": summarize_document(hit.document),
                    }
                )

        results.append({**q, "error": None, "hits": entries})
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
        f"- 问题数: {stats['total_questions']}",
        f"- 总分片数: {sync.get('total', '-')}（本次同步 updated={sync.get('updated', 0)}, deleted={sync.get('deleted', 0)}）",
        "",
    ]

    same_source_text = (
        "-"
        if stats["avg_same_source_ratio"] is None
        else f"{stats['avg_same_source_ratio']:.0%}"
    )
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
        if r["error"]:
            lines.append(f"- 检索异常: {r['error']}")
            lines.append("")
            continue
        if not r["hits"]:
            lines.append("- **空召回**：没有命中任何分片。")
            lines.append("")
            continue
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

  # 自定义报告与日志输出路径
  python scripts/rag/eval_retrieval.py --output reports/eval.md --log-output reports/eval.log

  # 关闭控制台日志保存
  python scripts/rag/eval_retrieval.py --no-log-output
""",
    )
    parser.add_argument("--questions", type=str, help="外部问题文件路径（每行一条，可选 id|query）")
    parser.add_argument("--limit", type=int, help="限制评测问题数（默认全部）")
    parser.add_argument("--top-k", type=int, default=5, help="每个问题保留的 Top-K 命中数（默认 5）")
    parser.add_argument("--namespace", type=str, default="wild_spec", help="逻辑命名空间（默认 wild_spec，必须与索引一致）")
    parser.add_argument("--embedding", choices=["auto", "hash"], default="auto", help="embedding 选择：auto 用 config 真实配置（默认）；hash 用本地 HashEmbeddingFunction + 临时索引")
    parser.add_argument("--output", type=Path, help="报告 Markdown 输出路径（默认 scripts/reports/eval_retrieval_<时间戳>.md）")
    parser.add_argument("--log-output", type=Path, help="控制台日志保存路径（默认 scripts/reports/eval_console_<时间戳>.txt）")
    parser.add_argument("--no-log-output", action="store_true", help="不保存控制台日志（默认会保存）")
    args = parser.parse_args()

    if args.top_k < 1:
        raise SystemExit("错误: --top-k 必须 >= 1")

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

    # 校验 namespace 下确有分片，避免误用空索引得出无意义结论
    total_chunks = loader.last_sync_stats.get("total", 0)
    if total_chunks == 0:
        print(
            f"错误: namespace='{args.namespace}' 下没有分片（total=0）。"
            "请检查 --namespace 是否与索引一致（线上默认 wild_spec），或索引是否已构建。"
        )
        return 2

    print(f"索引就绪: 总分片 {total_chunks}，知识库来源文件 {len(get_rag_spec_paths())} 个")
    eval_data = run_eval(loader, questions, args.top_k)
    stats = eval_data["stats"]
    print(f"\n汇总: 空召回 {stats['empty_top1']}/{stats['total_questions']} "
          f"({stats['empty_top1_rate']:.1%}), 异常 {stats['retrieval_errors']}, "
          f"平均距离 {stats['avg_all_distance'] if stats['avg_all_distance'] is not None else '-'}")

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

    if log_path:
        print(f"控制台日志已保存: {log_path}")
    return 0


if __name__ == "__main__":
    exit(main())
