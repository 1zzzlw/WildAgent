"""校验 knowledge_base 知识库的结构与检索契约。

用真实的 MarkdownChunker 解析路径级 metadata 与 frontmatter（不是自写 YAML 解析），
再拿代码里那 5 组硬编码过滤对去比对，证明目录重组没有把检索入口打断。
退出码即结果：0 = 全绿。
"""

from __future__ import annotations

import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2] / "wild-server"
sys.path.insert(0, str(WS))

import yaml  # noqa: E402
from app.spec.loader import MarkdownChunker  # noqa: E402

KB = WS / "storage" / "knowledge_base"
CFG = KB / "config.yaml"

FILTERS: list[tuple[str, dict[str, str]]] = [
    ("knowledge/protocol 协议", {"doc_type": "blueprint_spec", "knowledge_role": "protocol"}),
    ("knowledge/components 能力", {"doc_type": "component", "knowledge_role": "capability"}),
    ("rules 关系", {"doc_type": "recipe", "knowledge_role": "relation"}),
    ("点名校验 组装关系", {"doc_type": "recipe", "entity_name": "supported_assembly_relations"}),
    ("点名校验 构件参数", {"doc_type": "component", "topic": "parameters"}),
]

GENERATION_ROLES = ("protocol", "capability", "relation")
NAV_MARKERS = ("参见", "详见", "见第")
FORBIDDEN_FM_KEYS = ("source",)

problems: list[str] = []
counts = {name: 0 for name, _ in FILTERS}
gen_docs = 0
nav_docs = 0
rows: list[tuple[str, str, str, str, str]] = []

chunker = MarkdownChunker(metadata_config_path=CFG)

for path in sorted(KB.rglob("*.md")):
    rel = path.relative_to(KB).as_posix()
    text = path.read_text(encoding="utf-8")

    # ① frontmatter 必须是合法 YAML，且真实解析器读出的值要一致
    baked: dict = {}
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) < 3:
            problems.append(f"{rel}: frontmatter 未闭合")
            continue
        try:
            baked = yaml.safe_load(parts[1]) or {}
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{rel}: frontmatter YAML 解析失败 {exc}")
            continue
        for key in FORBIDDEN_FM_KEYS:
            if key in baked:
                problems.append(f"{rel}: frontmatter 不应包含 {key}")
        real_fm, _ = chunker._extract_frontmatter(text)
        for key, want in baked.items():
            got = real_fm.get(key, "<缺失>")
            if isinstance(want, list):
                if list(got) != list(want):
                    problems.append(f"{rel}: 真实解析器 {key} 不一致 {got!r} != {want!r}")
            elif str(got) != str(want):
                problems.append(f"{rel}: 真实解析器 {key} 不一致 {got!r} != {want!r}")
    elif rel != "README.md":
        problems.append(f"{rel}: 缺少 frontmatter")

    # ② 路径规则 + frontmatter（后者覆盖），复刻 loader 的合并顺序
    real_fm, body = chunker._extract_frontmatter(text)
    meta = chunker._path_rule_metadata(path)
    meta.update(real_fm)

    # ③ 硬编码过滤对必须能命中
    for name, cond in FILTERS:
        if all(str(meta.get(k)) == v for k, v in cond.items()):
            counts[name] += 1

    role = str(meta.get("knowledge_role") or "")
    if role in GENERATION_ROLES:
        gen_docs += 1
    else:
        nav_docs += 1

    # ④ 必须有 H1，否则分片的"知识路径"会退化成文件名
    if not any(line.startswith("# ") for line in body.splitlines()):
        problems.append(f"{rel}: 缺少 H1 标题")

    # ⑤ 代码围栏必须配对
    fences = sum(1 for line in body.splitlines() if line.startswith("```"))
    if fences % 2:
        problems.append(f"{rel}: 代码围栏未闭合（{fences} 个）")

    # ⑥ 正文不应出现指向其他文件的导航句（README 自身在讲这条规则，跳过）
    if rel != "README.md":
        for marker in NAV_MARKERS:
            for i, line in enumerate(body.splitlines(), 1):
                if marker in line and ".md" in line:
                    problems.append(f"{rel}:{i}: 残留导航句 -> {line.strip()[:60]}")

    rows.append(
        (rel, str(meta.get("doc_type", "")), role, str(meta.get("entity_name", "")), str(meta.get("topic", "")))
    )

print(f"{'路径':<48} {'doc_type':<15} {'role':<11} {'entity_name':<32} topic")
print("-" * 132)
for rel, dt, role, en, tp in rows:
    print(f"{rel:<48} {dt:<15} {role:<11} {en:<32} {tp}")

print()
print("过滤对命中数：")
for name, cond in FILTERS:
    n = counts[name]
    print(f"  {'OK ' if n else '!! '}{name:<24} {n} 个文件  {cond}")
    if n == 0:
        problems.append(f"过滤对 {name} 命中 0 个文件")

print()
print(f"参与生成检索的文档：{gen_docs}    仅导航：{nav_docs}")

cfg = yaml.safe_load(CFG.read_text(encoding="utf-8")) or {}
declared = cfg.get("required_documents", [])
missing = [p for p in declared if not (KB / p).exists()]
if missing:
    problems.append(f"required_documents 缺失：{missing}")
undeclared = sorted(
    {p.relative_to(KB).as_posix() for p in KB.rglob("*.md")} - set(declared)
)
if undeclared:
    problems.append(f"未登记进 required_documents：{undeclared}")
print(f"required_documents：{len(declared)} 条，缺失 {len(missing)}，未登记 {len(undeclared)}")

print()
if problems:
    print(f"FAIL —— {len(problems)} 个问题")
    for item in problems:
        print(f"  - {item}")
    sys.exit(1)
print("PASS —— 结构、metadata、过滤对、H1、围栏、导航句全部通过")
