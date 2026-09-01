"""校准 Retrieval Gate 距离阈值。

两种用法：
1. 读 eval_retrieval.py 的 JSON 产物（推荐，直接复用真实评测结果）：
     python scripts/rag/eval_retrieval.py --json-output evals/retrieval_results.json
     python scripts/rag/calibrate_retrieval_gate.py evals/retrieval_results.json
2. 直接跑评测校准（内部复用 eval_retrieval 的 loader 装配与问题加载）：
     python scripts/rag/calibrate_retrieval_gate.py --eval --embedding hash
     python scripts/rag/calibrate_retrieval_gate.py --eval --questions my_cases.json --top-k 5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[2]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.agent.rag_calibration import calibrate_distance_threshold


def _samples_from_eval_results(results: list[dict]) -> list[dict[str, object]]:
    """从 eval 结果集抽取 (should_answer, top1 distance) 样本。"""
    samples: list[dict[str, object]] = []
    for result in results:
        if result.get("error"):
            # 检索异常意味着"无法通过任何有限距离阈值"，等价于空召回样本。
            samples.append({
                "id": result.get("id"),
                "should_answer": str(result.get("expectedAction") or "answer").lower() != "reject",
                "distance": None,
            })
            continue
        expected_action = str(result.get("expectedAction") or "answer").lower()
        hits = result.get("hits") or []
        top_distance = hits[0].get("distance") if hits else None
        samples.append({
            "id": result.get("id"),
            "should_answer": expected_action != "reject",
            "distance": top_distance,
        })
    return samples


def _run_eval_calibration(args: argparse.Namespace) -> tuple[dict, dict]:
    """复用 eval_retrieval 的装配跑一遍评测，再校准阈值。"""
    import scripts.rag.eval_retrieval as eval_mod

    loader, temp_handle = eval_mod.build_loader(args)
    questions = eval_mod.load_questions(args.questions, args.limit)
    total_chunks = eval_mod.indexed_chunk_count(loader)
    if total_chunks == 0:
        raise SystemExit(
            f"错误: namespace='{args.namespace}' 下没有分片（total=0）。"
            "请检查 --namespace；若知识库尚未建索引，可显式使用 --sync-index。"
        )
    eval_data = eval_mod.run_eval(
        loader,
        questions,
        args.top_k,
        use_case_filters=not args.ignore_case_filters,
    )
    stats = eval_data["stats"]
    samples = _samples_from_eval_results(eval_data["results"])
    calibration = calibrate_distance_threshold(samples)
    calibration["embedding"] = args.embedding_type
    calibration["index_signature"] = loader._index_signature()
    calibration["stats"] = {
        "total_questions": stats["total_questions"],
        "empty_top1": stats["empty_top1"],
        "retrieval_errors": stats["retrieval_errors"],
        "negative_questions": stats["negative_questions"],
    }
    return calibration, stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="校准 RAG Retrieval Gate 距离阈值",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例用法:

  # 方式一：从 eval_retrieval.py 的 JSON 产物校准
  python scripts/rag/eval_retrieval.py --json-output evals/retrieval_results.json
  python scripts/rag/calibrate_retrieval_gate.py evals/retrieval_results.json

  # 方式二：直接跑评测并校准（内部复用 eval_retrieval 装配）
  python scripts/rag/calibrate_retrieval_gate.py --eval --embedding hash
  python scripts/rag/calibrate_retrieval_gate.py --eval --questions my_cases.json --top-k 5
""",
    )
    parser.add_argument(
        "eval_json",
        nargs="?",
        type=Path,
        help="eval_retrieval.py --json-output 产物；与 --eval 二选一",
    )
    parser.add_argument("--eval", action="store_true", help="直接跑评测并校准（需给出问题集）")
    parser.add_argument("--output", type=Path, help="校准结果 JSON；默认打印到控制台")

    # 与 eval_retrieval.py 对齐的评测参数（仅 --eval 模式使用）。
    parser.add_argument("--questions", type=str, help="评测集路径；JSON 可带标准答案（默认 evals/rag_retrieval_cases.json）")
    parser.add_argument("--limit", type=int, help="限制评测问题数")
    parser.add_argument("--top-k", type=int, default=5, help="每个问题保留的 Top-K 命中数（默认 5）")
    parser.add_argument("--namespace", type=str, default="wild_spec", help="逻辑命名空间（默认 wild_spec）")
    parser.add_argument("--embedding", choices=["auto", "hash"], default="auto", help="auto 用真实配置；hash 用本地 HashEmbeddingFunction + 临时索引")
    parser.add_argument("--temporary-index", action="store_true", help="重建临时索引（不修改 storage/chroma）")
    parser.add_argument("--chunk-size", type=int, help="临时索引分片长度；默认 config.rag.chunk_size")
    parser.add_argument("--chunk-overlap", type=int, help="临时索引普通文本重叠长度；默认 config.rag.chunk_overlap")
    parser.add_argument("--sync-index", action="store_true", help="评测前同步真实索引")
    parser.add_argument("--ignore-case-filters", action="store_true", help="忽略 JSON case 的 metadataFilter")

    args = parser.parse_args()

    if args.eval:
        if args.eval_json:
            raise SystemExit("错误: --eval 模式不需要 eval_json 位置参数，二选一。")
        if args.top_k < 1:
            raise SystemExit("错误: --top-k 必须 >= 1")
        if args.chunk_size is not None and args.chunk_size < 200:
            raise SystemExit("错误: --chunk-size 必须 >= 200")
        if args.chunk_overlap is not None and args.chunk_overlap < 0:
            raise SystemExit("错误: --chunk-overlap 必须 >= 0")
        # 构造 eval_retrieval.build_loader 需要的附加属性。
        args.effective_chunk_size = None
        args.effective_chunk_overlap = None
        args.embedding_type = args.embedding
        calibration, stats = _run_eval_calibration(args)
        if stats["retrieval_errors"]:
            print("警告: 评测存在检索异常；校准样本含空召回，阈值偏保守。")
    elif args.eval_json:
        if not args.eval_json.exists():
            raise SystemExit(f"错误: 评测结果文件不存在: {args.eval_json}")
        payload = json.loads(args.eval_json.read_text(encoding="utf-8"))
        samples = _samples_from_eval_results(payload.get("results") or [])
        if not samples:
            raise SystemExit("错误: 评测结果中没有可用的样本。")
        calibration = calibrate_distance_threshold(samples)
        calibration["embedding"] = payload.get("run", {}).get("embedding")
        calibration["index_signature"] = payload.get("run", {}).get("index_signature")
    else:
        parser.print_help()
        return 2

    calibration["config_example"] = {
        "RAG__RETRIEVAL_GATE__MODE": "observe",
        "RAG__RETRIEVAL_GATE__MAX_DISTANCE": round(calibration["threshold"], 6),
    }
    text = json.dumps(calibration, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"阈值校准报告已生成: {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
