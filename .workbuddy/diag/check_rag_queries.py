"""分片级校验：证明 app/services/agent_service.py 的生成期查询能命中。

用真实 MarkdownChunker 对知识库切分，然后拿 `_build_rag_queries` 生成建筑时实际用的
7 组过滤对去逐片比对，统计每组命中的**分片数**。

doc 级命中 != 分片级命中：loader 会按标题派生每片的 metadata（含分片 rag-meta 覆盖），
检索只看分片。退出码即结果：0 = 7 组全部非 0。
"""

from __future__ import annotations

import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2] / "wild-server"
sys.path.insert(0, str(WS))

from app.spec.loader import MarkdownChunker  # noqa: E402

KB = WS / "storage" / "knowledge_base"
CFG = KB / "config.yaml"

# 与 agent_service._build_rag_queries 的"生成建筑"分支一一对应
QUERIES: list[tuple[str, dict[str, str]]] = [
    ("已选构件的条件关系", {"doc_type": "recipe", "entity_name": "component_selection_conditions"}),
    ("结构构件能力", {"doc_type": "component", "entity_type": "structural_component"}),
    ("墙体构件能力", {"doc_type": "component", "entity_type": "wall"}),
    ("窗构件能力", {"doc_type": "component", "entity_type": "window"}),
    ("门构件能力", {"doc_type": "component", "entity_type": "door"}),
    ("栏杆构件能力", {"doc_type": "component", "entity_type": "railing"}),
    ("屋顶构件能力", {"doc_type": "component", "entity_type": "roof"}),
]

# 另外两组：非建筑生成路径（ScenePatch 修改）与基础点名校验
EXTRA: list[tuple[str, dict[str, str]]] = [
    ("ScenePatch 协议", {"doc_type": "blueprint_spec", "knowledge_role": "protocol"}),
    ("ScenePatch 能力", {"doc_type": "component", "knowledge_role": "capability"}),
    ("ScenePatch 关系", {"doc_type": "recipe", "knowledge_role": "relation"}),
    ("点名 组装关系", {"doc_type": "recipe", "entity_name": "supported_assembly_relations"}),
    ("点名 构件参数", {"doc_type": "component", "topic": "parameters"}),
]

GENERATION_ROLES = {"protocol", "capability", "relation"}


def main() -> int:
    chunker = MarkdownChunker(metadata_config_path=CFG)
    chunks = []
    for path in sorted(KB.rglob("*.md")):
        chunks.extend(chunker.split_file(path, namespace="probe", doc_scope="generation"))

    generation_chunks = [c for c in chunks if str(c.metadata.get("knowledge_role")) in GENERATION_ROLES]
    print(f"总分片 {len(chunks)}，其中参与生成检索 {len(generation_chunks)}")

    problems: list[str] = []
    for title, cond in QUERIES + EXTRA:
        hits = [
            c
            for c in generation_chunks
            if all(str(c.metadata.get(k)) == v for k, v in cond.items())
        ]
        sources = sorted({str(c.metadata.get("source_file") or "?") for c in hits})
        mark = "OK " if hits else "!! "
        print(f"  {mark}{title:<20} {len(hits):>3} 片  {cond}  {sources if sources else ''}")
        if not hits:
            problems.append(f"{title} {cond} 命中 0 片")

    print()
    if problems:
        print(f"FAIL —— {len(problems)} 组查询命中 0 片：")
        for item in problems:
            print(f"  - {item}")
        return 1
    print("PASS —— 所有查询在分片级都有命中")
    return 0


if __name__ == "__main__":
    sys.exit(main())
