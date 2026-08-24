#!/usr/bin/env python3
"""删除已由知识库 config.yaml 提供的重复 frontmatter 字段。

只有路径配置值与文件头显式值完全相同时才删除。脚本会在写入前重新解析文件，
并确认清理前后的最终合并 metadata 完全一致。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lint_wild_rag_docs import _path_metadata, split_frontmatter  # noqa: E402


TOP_LEVEL_KEY_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_-]*):")


@dataclass(frozen=True)
class CompactResult:
    text: str
    removed_fields: tuple[str, ...]


def compact_text(path: Path, text: str) -> CompactResult:
    newline = "\r\n" if "\r\n" in text else "\n"
    had_final_newline = text.endswith(("\n", "\r"))
    lines = text.splitlines()
    declared_before, body_start = split_frontmatter(lines)
    if not declared_before or body_start == 0:
        return CompactResult(text, ())

    mapped = _path_metadata(path)
    redundant = tuple(
        key for key, value in declared_before.items()
        if key in mapped and mapped[key] == value
    )
    if not redundant:
        return CompactResult(text, ())

    redundant_set = set(redundant)
    output = [lines[0]]
    index = 1
    frontmatter_end = body_start - 1
    while index < frontmatter_end:
        key_match = TOP_LEVEL_KEY_RE.match(lines[index])
        if not key_match or key_match.group(1) not in redundant_set:
            output.append(lines[index])
            index += 1
            continue

        # 删除当前顶层字段；若它是列表，同时删除所属的缩进列表项。
        index += 1
        while index < frontmatter_end:
            if TOP_LEVEL_KEY_RE.match(lines[index]):
                break
            if lines[index].strip() == "" or lines[index].startswith((" ", "\t")):
                index += 1
                continue
            break

    output.extend(lines[frontmatter_end:])
    compacted = newline.join(output)
    if had_final_newline:
        compacted += newline

    declared_after, _ = split_frontmatter(compacted.splitlines())
    effective_before = {**mapped, **declared_before}
    effective_after = {**mapped, **declared_after}
    if effective_before != effective_after:
        raise ValueError(f"{path}: 清理前后最终 metadata 不一致，已拒绝写入")
    return CompactResult(compacted, redundant)


def iter_markdown_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.md") if path.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description="清理由 config.yaml 重复提供的文件头字段")
    parser.add_argument("root", type=Path, help="知识库根目录")
    parser.add_argument("--write", action="store_true", help="实际写回；默认只输出审计结果")
    args = parser.parse_args()

    changed: list[tuple[Path, CompactResult]] = []
    counts: dict[str, int] = {}
    for path in iter_markdown_files(args.root):
        result = compact_text(path, path.read_text(encoding="utf-8"))
        if not result.removed_fields:
            continue
        changed.append((path, result))
        for field in result.removed_fields:
            counts[field] = counts.get(field, 0) + 1

    if args.write:
        for path, result in changed:
            path.write_text(result.text, encoding="utf-8", newline="")

    action = "已清理" if args.write else "可清理"
    print(
        f"{action}: files={len(changed)}, fields={sum(counts.values())}, "
        f"by_field={dict(sorted(counts.items()))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
