"""复用项目检索与评分函数，在 LangSmith 上运行来源级检索评测。"""
import argparse
import os


def make_target(loader, top_k):
    # 原评测脚本已有父分片合并逻辑，保持两种报告的评分口径一致。
    from scripts.rag.eval_retrieval import select_ranked_parent_groups

    def rag_target(inputs: dict) -> dict:
        hits = loader.retrieve(
            inputs["query"], metadata_filter=inputs.get("metadataFilter")
        )
        entries = [
            {
                "chunk_id": hit.id,
                "source": hit.metadata.get("source", ""),
                "path": hit.metadata.get("path", ""),
                "parent_chunk_id": hit.metadata.get("parent_chunk_id", ""),
                "distance": hit.distance,
                "document": hit.document,
            }
            for hit in hits
        ]
        return {"hits": select_ranked_parent_groups(entries, top_k)}

    return rag_target


def retrieval_scores(outputs: dict, reference_outputs: dict) -> dict:
    expected = (reference_outputs or {}).get("expectedSources")
    if not isinstance(expected, list) or not expected or not all(
        isinstance(source, str) and source.strip() for source in expected
    ):
        raise ValueError("参考输出必须包含非空字符串数组 expectedSources")
    from scripts.rag.eval_retrieval import score_ranked_hits

    scores = score_ranked_hits(outputs["hits"], expected)
    return {"results": [
        {"key": "hit_at_k", "score": int(scores["hit"])},
        {"key": "recall_at_k", "score": scores["recall"]},
        {"key": "reciprocal_rank", "score": scores["reciprocal_rank"]},
    ]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, help="已有的 LangSmith 数据集名称")
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--experiment-prefix", default="wildagent-rag-baseline")
    args = parser.parse_args()
    if args.top_k is not None and args.top_k < 1:
        parser.error("--top-k 必须大于 0")

    from dotenv import load_dotenv
    from app.utils.runtime_env import runtime_env_path

    load_dotenv(runtime_env_path(), override=False)
    if not os.environ.get("LANGSMITH_API_KEY"):
        parser.error("请在 wild-server/.env 或进程环境中设置 LANGSMITH_API_KEY")

    from langsmith import evaluate, traceable
    from config import config
    from scripts.rag.eval_retrieval import build_loader, indexed_chunk_count

    if not config.rag.enabled or not config.embedding.api_key or not config.embedding.name:
        parser.error("请启用 RAG 并配置 EMBEDDING__API_KEY 和 EMBEDDING__NAME；本入口不使用 hash 评测")

    top_k = args.top_k or config.rag.top_k
    loader, _ = build_loader(argparse.Namespace(
        embedding="auto", temporary_index=False, sync_index=False,
        namespace="wild_spec", top_k=top_k, chunk_size=None, chunk_overlap=None,
    ))
    if indexed_chunk_count(loader) == 0:
        parser.error("现有知识索引为空，请先通过项目原有入库流程构建索引")

    # closure 只追踪输入与命中结果，不把 Loader 实例或配置密钥作为追踪参数。
    rag_target = traceable(name="wildagent_retrieval", run_type="retriever")(
        make_target(loader, top_k)
    )
    experiment_results = evaluate(
        rag_target,
        data=args.dataset,
        evaluators=[retrieval_scores],
        experiment_prefix=args.experiment_prefix,
        max_concurrency=1,
        metadata={
            "top_k": top_k,
            "embedding_model": config.embedding.name,
            "collection": config.rag.collection_name,
            "chunk_size": config.rag.chunk_size,
            "chunk_overlap": config.rag.chunk_overlap,
            "index_mode": "existing_no_sync",
        },
    )
    print(f"实验已结束：{experiment_results.experiment_name}；请检查样例和 evaluator 错误后解读得分")


if __name__ == "__main__":
    main()
