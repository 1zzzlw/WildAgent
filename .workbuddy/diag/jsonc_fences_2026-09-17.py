"""把知识库里"带注释/省略号的教学示意"代码块从 ```json 改成 ```jsonc。

背景：scripts/rag/lint_wild_rag_docs.py:499 只对 ```json 围栏做严格 JSON 解析 +
注释检查（json_comment / invalid_json），而 tests/rag/test_knowledge_rules_v3.py
把这些 error 当门禁。这些块本来就不是合法 JSON（含 // ❌ 注释或 ... 省略号），
但注释承担教学语义，删掉会丢信息。

约定（本脚本落地的那条）：
  ```json   ← 可被代码解析 / 模型能直接照抄的最小示例，必须严格合法
  ```jsonc  ← 带注释或省略号的教学示意，不参与严格校验

直接用 Edit 改 10 处容易错行，因此按"围栏起始行号"精确替换。
用法：
    cd wild-server
    ./.venv/Scripts/python.exe ../.workbuddy/diag/jsonc_fences_2026-09-17.py
"""
from __future__ import annotations

import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[2] / "wild-server"
KB = SERVER_ROOT / "storage" / "knowledge_base"

# 文件 → 需要改成 jsonc 的 ```json 围栏起始行号（1-based）
TARGETS: dict[str, list[int]] = {
    "knowledge/components/capability-boundaries.md": [450],
    "knowledge/protocol/blueprint-skeleton.md": [33],
    "knowledge/protocol/scene-patch-protocol.md": [256, 289, 311, 365, 394, 412, 454],
    "rules/implementation/assembly-relations.md": [45],
}


def main() -> int:
    changed = 0
    for rel, line_numbers in TARGETS.items():
        path = KB / rel
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        for number in line_numbers:
            index = number - 1
            stripped = lines[index].strip()
            if stripped != "```json":
                print(f"[SKIP] {rel}:{number} 实际是 {stripped!r}，未按预期落在围栏上")
                continue
            # 保留原缩进与换行符，只替换语言标记。
            indent = lines[index][: len(lines[index]) - len(lines[index].lstrip())]
            newline = "\n" if lines[index].endswith("\n") else ""
            lines[index] = f"{indent}```jsonc{newline}"
            changed += 1
            print(f"[OK]   {rel}:{number} json -> jsonc")
        path.write_text("".join(lines), encoding="utf-8")
    print(f"\n共改动 {changed} 处围栏")
    return 0


if __name__ == "__main__":
    sys.exit(main())
