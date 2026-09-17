"""Chroma RAG 检索的独立冒烟测试。

它不读取线上持久化索引，也不调用远程 embedding；测试结束后临时索引会被删除。
在 ``wild-server`` 目录运行：

    ./.venv/Scripts/python.exe scripts/rag/smoke_test.py

它属于运维/排查脚本，因此放在 scripts/ 而不是应用包内：app/ 只保留服务运行时
代码，避免业务包被测试脚手架污染。
"""
from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

# 脚本在 scripts/rag/ 下，导入 app.* 前必须把仓库根（wild-server）放进 sys.path。
SERVER_ROOT = Path(__file__).resolve().parents[2]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.spec.loader import HashEmbeddingFunction, RAGSpecLoader, collect_markdown_paths  # noqa: E402


# 所有路径从当前文件反推，避免运行命令所在目录改变知识库位置。
KB = SERVER_ROOT / "storage" / "knowledge_base"
KB = SERVER_ROOT / "storage" / "knowledge_base"
# 基础规范在真实服务中直接注入 Prompt，因此不应重复进入 RAG 候选。
BASE_SPEC_PATHS = [
    KB / "knowledge" / "protocol" / "blueprint-skeleton.md",
    KB / "knowledge" / "protocol" / "generation-redlines.md",
]
RAG_SPEC_PATHS = collect_markdown_paths(KB, exclude=BASE_SPEC_PATHS)


def main() -> None:
    """构建一次临时索引，并验证几类代表性查询能够召回预期关键词。"""
    # TemporaryDirectory 保证 smoke test 不污染 storage/chroma 中的真实索引。
    with TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        loader = RAGSpecLoader(
            base_paths=[str(path) for path in BASE_SPEC_PATHS],
            rag_paths=[str(path) for path in RAG_SPEC_PATHS],
            persist_dir=tmp_dir,
            collection_name="wild_rag_smoke",
            # 本地 hash embedding 让测试无需 API key，验证重点是完整检索链路。
            embedding_function=HashEmbeddingFunction(),
            top_k=4,
            chunk_size=900,
            chunk_overlap=150,
        )

        # 每项只要求命中任意一个关键词，避免分片或排序微调造成脆弱测试。
        # 关键词必须取自"当前知识库里真实存在的正文"（知识库已按 knowledge/ + rules/
        # 重组，历史文档名与建筑类型词条可能已不存在）；改动知识库后若这里开始失败，
        # 先确认是召回退化还是关键词过期，再决定改脚本还是改知识库。
        checks = [
            # 门窗：宿主引用与沿墙定位
            ("窗户 opening 引用宿主墙 parentWall", ["parentWall", "opening"]),
            # 材质：构件级材质字段与物理玻璃属性
            ("外墙材质 baseColor 玻璃 transmission", ["baseColor", "transmission"]),
            # 屋顶：按体量轮廓取尺寸
            ("屋顶 roofType 跨度 span 深度 depth", ["roofType", "span"]),
            # 复杂构件：幕墙确定性参数（问法要贴近该文档自身的标题用词，
            # 本地 HashEmbedding 本质是词面匹配，跨语言/近义改写召不回）
            ("玻璃幕墙确定性生成参数 分格", ["pane_module", "幕墙", "分格"]),
            # 场景补丁：增量修改协议（同上门槛：问法要与文档标题词面接近）
            ("ScenePatch 增量修改 操作类型 组件操作", ["update_component", "操作类型"]),
        ]

        for query, expected_terms in checks:
            # load() 同时触发检索和上下文拼接，last_results 暴露本次原始命中。
            context = loader.load(query)
            hits = loader.last_results
            if not hits:
                raise AssertionError(f"RAG query 没有召回结果: {query}")

            matched = [
                term for term in expected_terms
                if term.lower() in context.lower()
            ]
            if not matched:
                # 失败时输出来源与标题，方便判断是扫描、分片还是召回问题。
                sources = [
                    f"{hit.metadata.get('source')} / {hit.metadata.get('heading')}"
                    for hit in hits
                ]
                raise AssertionError(
                    f"RAG query 未命中预期关键词: {query}, hits={sources}"
                )

            print(f"[OK] {query} -> {len(hits)} hits, matched={matched}")


if __name__ == "__main__":
    # 仅直接执行模块时运行；被测试框架导入不会自动构建索引。
    main()
