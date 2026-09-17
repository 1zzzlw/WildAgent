"""给 v2 知识库补分片级 rag-meta（entity_type），恢复 v1 的构件级检索粒度。

背景：v1 靠「文件名猜 entity_type」+「每节 rag-meta」让 _build_rag_queries 的构件查询命中；
v2 合并成 component-parameters.md / capability-boundaries.md 两个通用名文件后，
`entity_type: wall|window|door|roof|structural_component` 的查询全部命中 0。

本脚本在每个「以单一构件为主题」的标题后插入 rag-meta 块，只覆盖 entity_type。
不覆盖 topic / doc_type，因此 {doc_type: component, topic: parameters} 这类点名过滤不受影响。
幂等：已有 rag-meta 的位置跳过。
"""
from __future__ import annotations

import sys
from pathlib import Path

KB = Path(__file__).resolve().parents[2] / "wild-server" / "storage" / "knowledge_base_v2"

TARGETS: dict[str, list[tuple[str, str]]] = {
    "knowledge/protocol/component-parameters.md": [
        ("## 一、wall — 垂直墙体", "wall"),
        ("## 二、floor — 水平地板", "structural_component"),
        ("## 三、column — 柱式", "structural_component"),
        ("## 四、beam — 横梁", "structural_component"),
        ("## 五、roof — 屋顶", "roof"),
        ("## 六、opening — 门窗洞口", "opening"),
        ("## 十一、primitive — 通用程序化形体（v1.1）", "structural_component"),
    ],
    "knowledge/components/capability-boundaries.md": [
        ("### 3.1 柱 (column)", "structural_component"),
        ("### 3.2 梁 (beam)", "structural_component"),
        ("### 3.3 门 (door)", "door"),
        ("### 3.4 窗 (window)", "window"),
        ("### 3.5 屋顶 (roof)", "roof"),
    ],
}


def main() -> int:
    problems: list[str] = []
    for rel, mapping in TARGETS.items():
        path = KB / rel
        if not path.is_file():
            problems.append(f"文件不存在: {rel}")
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        out: list[str] = []
        inserted = 0
        for index, line in enumerate(lines):
            out.append(line)
            target = next((t for t in mapping if line.strip() == t[0]), None)
            if target is None:
                continue
            nxt = lines[index + 1] if index + 1 < len(lines) else ""
            if "rag-meta" in nxt:
                continue  # 幂等：已插入
            out.append("")
            out.append("<!-- rag-meta")
            out.append(f"entity_type: {target[1]}")
            out.append("-->")
            inserted += 1
        # 校验：每个目标标题都应被处理过一次
        for heading, _ in mapping:
            if not any(line.strip() == heading for line in lines):
                problems.append(f"未找到标题: {rel} :: {heading}")
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
        print(f"{rel}: 插入 {inserted} 处")

    if problems:
        print("\n问题：")
        for item in problems:
            print(f"  - {item}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
