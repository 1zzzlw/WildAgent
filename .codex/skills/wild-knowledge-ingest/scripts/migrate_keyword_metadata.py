#!/usr/bin/env python3
"""把 WildAgent 知识库 metadata 中的 legacy ``keywords`` 拆成两个字段。

迁移范围：
- 文档开头的 YAML frontmatter；
- ``<!-- rag-meta ... -->`` 实体级元数据块。

拆分原则刻意保持保守：中文术语、WILD 类型/字段和受控技术词进入
``primary_terms``；英文自然语言名称进入 ``synonyms``。脚本不会删除、改写
或重复任何旧词，并在写入前检查词项守恒。
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


KEY_RE = re.compile(r"^(?P<indent>[ \t]*)keywords:\s*(?P<value>.*?)\s*$")
LIST_ITEM_RE = re.compile(r"^(?P<indent>[ \t]*)-\s+(?P<value>.*?)\s*$")
CJK_RE = re.compile(r"[\u3400-\u9fff]")
CAMEL_CASE_RE = re.compile(r"[a-z][A-Z]")

# 这些不是自然语言别名，而是 WILD 结构、类型、字段、枚举或稳定技术概念。
PRIMARY_ASCII_TERMS = {
    "albedo", "assembly", "assembly relation", "assembly template", "balcony",
    "basecolor", "bay_window", "beam", "blueprint", "building type", "canopy",
    "chimney", "collision", "column", "column beam", "component", "cornice",
    "component compiler", "components", "composite component", "composition",
    "concrete", "csg", "curtain wall assembly", "curtain wall grid", "door",
    "door component matrix", "door opening", "door style", "engine capability",
    "facade extent", "facade grid", "fallback", "floor", "floor level", "geometry",
    "dome", "fink", "flat", "gable", "glass", "grid first", "grid mullion",
    "height", "hip", "howe", "instances", "interaction",
    "ior", "light", "material", "material reference", "materialclass glass",
    "materialdef", "materials", "metal", "metallic", "mullion", "mullion gap",
    "opening", "opening fit", "opacity", "pane module", "path", "patterns", "placements",
    "primitive", "primitive box", "primitive mullion", "primitive rotation",
    "pratt", "project pattern", "proposed component", "proposed type", "radial mullion",
    "railing", "ramp", "recipes", "reference order", "resolver", "reveal", "roof", "roof opening",
    "roof penetration", "roof style", "rotation", "roughness", "schema", "sill",
    "spandrel", "stair", "steel", "supported type", "taxonomy constraints", "templates",
    "templates instances", "terrain", "thickness", "transmission", "truss",
    "vertical mullion", "wall", "wall joint", "wall opening", "wall window",
    "wild", "wild type", "wild v1.1", "window", "window component",
    "window component matrix", "window grid", "window mullions", "window opening",
    "warren", "window style", "xz", "z fighting",
}


@dataclass(frozen=True)
class MigrationStats:
    files: int = 0
    declarations: int = 0
    terms: int = 0
    primary_terms: int = 0
    synonyms: int = 0

    def plus(self, *, files: int = 0, declarations: int = 0, terms: int = 0,
             primary_terms: int = 0, synonyms: int = 0) -> "MigrationStats":
        return MigrationStats(
            self.files + files,
            self.declarations + declarations,
            self.terms + terms,
            self.primary_terms + primary_terms,
            self.synonyms + synonyms,
        )


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _is_primary_term(term: str, index: int, previous_term: str | None) -> bool:
    """判断旧关键词是否为主术语；紧随中文名称的自然英文通常视为翻译。"""
    if index == 0 or CJK_RE.search(term):
        return True
    normalized = term.strip().casefold()
    if normalized in PRIMARY_ASCII_TERMS:
        return True
    if any(marker in term for marker in (".", "_")) or CAMEL_CASE_RE.search(term):
        return True
    # 常见旧列表按“中文正式名, 英文译名, 相关技术词……”书写。只有紧随
    # 中文术语的自然英文默认作为 synonym，后续相关技术词仍归 primary_terms。
    return not (previous_term and CJK_RE.search(previous_term))


def _split_terms(terms: list[str]) -> tuple[list[str], list[str]]:
    primary: list[str] = []
    synonyms: list[str] = []
    seen: set[str] = set()
    previous_term: str | None = None
    for index, raw_term in enumerate(terms):
        term = _strip_quotes(raw_term)
        if not term or term.casefold() in seen:
            continue
        seen.add(term.casefold())
        (primary if _is_primary_term(term, index, previous_term) else synonyms).append(term)
        previous_term = term
    if not primary and synonyms:
        primary.append(synonyms.pop(0))
    return primary, synonyms


def _metadata_contexts(lines: list[str]) -> list[bool]:
    """标记每一行是否位于 frontmatter 或 rag-meta 内。"""
    contexts = [False] * len(lines)
    in_frontmatter = bool(lines and lines[0].strip() == "---")
    in_rag_meta = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if index == 0 and in_frontmatter:
            contexts[index] = True
            continue
        if in_frontmatter:
            contexts[index] = True
            if stripped == "---":
                in_frontmatter = False
            continue
        if stripped.startswith("<!-- rag-meta"):
            in_rag_meta = True
        if in_rag_meta:
            contexts[index] = True
            if "-->" in line:
                in_rag_meta = False
    return contexts


def _render_array(indent: str, key: str, values: list[str]) -> list[str]:
    rendered = [f"{indent}{key}:"]
    if values:
        rendered.extend(f"{indent}  - {value}" for value in values)
    else:
        rendered[0] += " []"
    return rendered


def migrate_text(text: str) -> tuple[str, MigrationStats]:
    newline = "\r\n" if "\r\n" in text else "\n"
    had_final_newline = text.endswith(("\n", "\r"))
    lines = text.splitlines()
    contexts = _metadata_contexts(lines)
    output: list[str] = []
    stats = MigrationStats()
    index = 0

    while index < len(lines):
        line = lines[index]
        match = KEY_RE.match(line) if contexts[index] else None
        if not match:
            output.append(line)
            index += 1
            continue

        indent = match.group("indent")
        inline_value = match.group("value").strip()
        if inline_value:
            terms = [item.strip() for item in inline_value.strip("[]").split(",") if item.strip()]
            next_index = index + 1
        else:
            terms = []
            next_index = index + 1
            while next_index < len(lines) and contexts[next_index]:
                item_match = LIST_ITEM_RE.match(lines[next_index])
                if not item_match or len(item_match.group("indent")) <= len(indent):
                    break
                terms.append(item_match.group("value"))
                next_index += 1

        primary, synonyms = _split_terms(terms)
        if not primary:
            raise ValueError(f"第 {index + 1} 行的 keywords 没有有效词项")
        old_normalized = [item.casefold() for item in map(_strip_quotes, terms) if item.strip()]
        new_normalized = [item.casefold() for item in [*primary, *synonyms]]
        if set(old_normalized) != set(new_normalized) or len(set(old_normalized)) != len(new_normalized):
            raise ValueError(f"第 {index + 1} 行迁移前后词项不守恒")

        output.extend(_render_array(indent, "primary_terms", primary))
        output.extend(_render_array(indent, "synonyms", synonyms))
        stats = stats.plus(
            declarations=1,
            terms=len(primary) + len(synonyms),
            primary_terms=len(primary),
            synonyms=len(synonyms),
        )
        index = next_index

    migrated = newline.join(output)
    if had_final_newline:
        migrated += newline
    return migrated, stats


def iter_markdown_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.md") if path.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description="迁移 WildAgent 知识库 keywords metadata")
    parser.add_argument("root", type=Path, help="知识库根目录")
    parser.add_argument("--write", action="store_true", help="实际写回；默认只预览统计")
    args = parser.parse_args()

    total = MigrationStats()
    changed: list[tuple[Path, str]] = []
    for path in iter_markdown_files(args.root):
        original = path.read_text(encoding="utf-8")
        try:
            migrated, stats = migrate_text(original)
        except ValueError as exc:
            raise ValueError(f"{path}: {exc}") from exc
        if migrated != original:
            changed.append((path, migrated))
            total = total.plus(
                files=1,
                declarations=stats.declarations,
                terms=stats.terms,
                primary_terms=stats.primary_terms,
                synonyms=stats.synonyms,
            )

    if args.write:
        for path, migrated in changed:
            path.write_text(migrated, encoding="utf-8", newline="")

    action = "已写入" if args.write else "待迁移"
    print(
        f"{action}: files={total.files}, declarations={total.declarations}, "
        f"terms={total.terms}, primary_terms={total.primary_terms}, synonyms={total.synonyms}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
