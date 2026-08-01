from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


REQUIRED_METADATA = (
    "doc_type",
    "doc_scope",
    "knowledge_layer",
    "entity_type",
    "entity_name",
    "topic",
    "wild_version",
    "status",
    "authority",
    "source",
    "keywords",
)

ALLOWED_VALUES = {
    "doc_type": {
        "component", "building_type", "recipe", "blueprint_spec", "pattern", "index",
    },
    "doc_scope": {"generation", "index", "system"},
    "knowledge_layer": {
        "architecture", "constraint", "wild_schema", "project_pattern", "navigation",
    },
    "status": {"supported", "experimental", "proposed", "deprecated"},
    "authority": {
        "engine", "schema", "verified_example", "maintainer", "domain_reference", "inferred",
    },
}

PSEUDO_HEADING_RE = re.compile(
    r"^\s*\*\*(?:[A-ZＡ-Ｚ]|\d+|[一二三四五六七八九十]+)[.、．:：]\s*.+?\*\*.*$"
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
FENCE_RE = re.compile(r"^\s*(```+|~~~+)\s*([A-Za-z0-9_-]*)")
RAG_META_START_RE = re.compile(r"^\s*<!--\s*rag-meta\s*$")


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    path: str
    line: int
    message: str


@dataclass(frozen=True)
class Heading:
    level: int
    title: str
    line: int
    end_line: int
    chars: int


def _scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_simple_yaml(lines: list[str]) -> dict[str, object]:
    """Parse the flat scalar/list subset used by WildAgent metadata."""
    result: dict[str, object] = {}
    active_list: str | None = None
    for raw in lines:
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        list_match = re.match(r"^\s*-\s+(.+?)\s*$", line)
        if list_match and active_list:
            values = result.setdefault(active_list, [])
            if isinstance(values, list):
                values.append(_scalar(list_match.group(1)))
            continue
        pair = re.match(r"^([a-zA-Z_][a-zA-Z0-9_-]*):\s*(.*?)\s*$", line)
        if not pair:
            continue
        key, value = pair.groups()
        if value:
            if key == "keywords" and "," in value:
                result[key] = [_scalar(item) for item in value.split(",") if item.strip()]
            else:
                result[key] = _scalar(value)
            active_list = None
        else:
            result[key] = []
            active_list = key
    return result


def split_frontmatter(lines: list[str]) -> tuple[dict[str, object], int]:
    if not lines or lines[0].strip() != "---":
        return {}, 0
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return parse_simple_yaml(lines[1:index]), index + 1
    return {}, 0


def iter_markdown_files(inputs: Iterable[Path]) -> list[Path]:
    files: set[Path] = set()
    for input_path in inputs:
        path = input_path.resolve()
        if path.is_dir():
            files.update(item for item in path.rglob("*.md") if item.is_file())
        elif path.is_file() and path.suffix.casefold() == ".md":
            files.add(path)
    return sorted(files, key=lambda item: str(item).casefold())


def scan_structure(lines: list[str]) -> tuple[list[Heading], list[tuple[int, str, str]], list[int]]:
    raw_headings: list[tuple[int, int, str]] = []
    code_blocks: list[tuple[int, str, str]] = []
    pseudo_lines: list[int] = []
    fence_token: str | None = None
    fence_lang = ""
    fence_start = 0
    fence_content: list[str] = []

    for line_number, line in enumerate(lines, start=1):
        fence_match = FENCE_RE.match(line)
        if fence_match:
            token, language = fence_match.groups()
            if fence_token is None:
                fence_token = token
                fence_lang = language.casefold()
                fence_start = line_number
                fence_content = []
            elif token.startswith(fence_token[0]):
                code_blocks.append((fence_start, fence_lang, "\n".join(fence_content)))
                fence_token = None
                fence_lang = ""
                fence_content = []
            continue

        if fence_token is not None:
            fence_content.append(line)
            continue

        heading_match = HEADING_RE.match(line)
        if heading_match:
            raw_headings.append((line_number, len(heading_match.group(1)), heading_match.group(2)))
        elif PSEUDO_HEADING_RE.match(line):
            pseudo_lines.append(line_number)

    if fence_token is not None:
        code_blocks.append((fence_start, f"unclosed:{fence_lang}", "\n".join(fence_content)))

    headings: list[Heading] = []
    for index, (line_number, level, title) in enumerate(raw_headings):
        end_line = raw_headings[index + 1][0] - 1 if index + 1 < len(raw_headings) else len(lines)
        chars = len("\n".join(lines[line_number - 1:end_line]))
        headings.append(Heading(level, title, line_number, end_line, chars))
    return headings, code_blocks, pseudo_lines


def metadata_issues(path: Path, lines: list[str]) -> list[Issue]:
    metadata, _ = split_frontmatter(lines)
    issues: list[Issue] = []
    if not metadata:
        return [Issue("error", "missing_frontmatter", str(path), 1, "缺少文档级 YAML frontmatter")]

    for key in REQUIRED_METADATA:
        value = metadata.get(key)
        if value in (None, "", []):
            issues.append(Issue("error", "missing_metadata", str(path), 1, f"metadata 缺少 {key}"))

    for key, allowed in ALLOWED_VALUES.items():
        value = metadata.get(key)
        if value not in (None, "") and value not in allowed:
            issues.append(
                Issue("error", "invalid_metadata_value", str(path), 1, f"{key}={value!r} 不在允许值中")
            )

    keywords = metadata.get("keywords")
    if keywords not in (None, "") and not isinstance(keywords, list):
        issues.append(Issue("error", "invalid_keywords", str(path), 1, "keywords 必须是 YAML 列表"))

    if metadata.get("doc_type") == "index" and metadata.get("doc_scope") != "index":
        issues.append(Issue("error", "index_scope", str(path), 1, "index 文档必须使用 doc_scope: index"))
    if path.name.casefold() == "readme.md" and metadata.get("doc_scope") != "index":
        issues.append(Issue("warning", "readme_scope", str(path), 1, "README 建议使用 doc_scope: index"))
    return issues


def structure_issues(
    path: Path,
    lines: list[str],
    min_section_chars: int,
    max_section_chars: int,
) -> list[Issue]:
    headings, code_blocks, pseudo_lines = scan_structure(lines)
    issues: list[Issue] = []

    if not headings:
        issues.append(Issue("error", "no_headings", str(path), 1, "文档没有 Markdown 标题"))
        return issues

    h1 = [heading for heading in headings if heading.level == 1]
    if len(h1) != 1:
        issues.append(
            Issue("error", "h1_count", str(path), 1, f"文档应有且仅有一个 H1，当前为 {len(h1)}")
        )

    previous_level = headings[0].level
    seen_paths: set[tuple[str, ...]] = set()
    stack: list[str] = []
    for heading in headings:
        if heading.level > previous_level + 1:
            issues.append(
                Issue(
                    "warning",
                    "heading_jump",
                    str(path),
                    heading.line,
                    f"标题层级从 H{previous_level} 跳到 H{heading.level}",
                )
            )
        previous_level = heading.level

        stack = stack[: heading.level - 1]
        stack.append(heading.title.casefold().strip())
        heading_path = tuple(stack)
        if heading_path in seen_paths:
            issues.append(
                Issue("warning", "duplicate_heading_path", str(path), heading.line, "完整标题路径重复")
            )
        seen_paths.add(heading_path)

        section_lines = lines[heading.line:heading.end_line]
        semantic_lines: list[str] = []
        inside_rag_meta = False
        for line in section_lines:
            stripped = line.strip()
            if stripped.startswith("<!-- rag-meta"):
                inside_rag_meta = "-->" not in stripped
                continue
            if inside_rag_meta:
                if "-->" in stripped:
                    inside_rag_meta = False
                continue
            if not stripped or re.fullmatch(r"(?:-{3,}|\*{3,}|_{3,})", stripped):
                continue
            semantic_lines.append(stripped)
        semantic_chars = len("\n".join(semantic_lines))

        if heading.level >= 2 and semantic_chars == 0:
            issues.append(
                Issue(
                    "warning",
                    "empty_container_heading",
                    str(path),
                    heading.line,
                    "标题本身没有正文；Loader 会跳过该壳块，确认它仍有必要保留为父级路径",
                )
            )
        if heading.level >= 2 and semantic_chars > max_section_chars:
            issues.append(
                Issue(
                    "warning",
                    "long_section",
                    str(path),
                    heading.line,
                    f"标题块有效正文 {semantic_chars} 字符，建议增加业务子标题",
                )
            )
        if heading.level >= 2 and 0 < semantic_chars < min_section_chars:
            issues.append(
                Issue(
                    "warning",
                    "short_section",
                    str(path),
                    heading.line,
                    f"标题块有效正文仅 {semantic_chars} 字符，确认其能独立回答问题",
                )
            )

    for line_number in pseudo_lines:
        issues.append(
            Issue(
                "warning",
                "pseudo_heading",
                str(path),
                line_number,
                "疑似使用粗体编号代替实体标题",
            )
        )

    for line_number, language, content in code_blocks:
        if language.startswith("unclosed:"):
            issues.append(Issue("error", "unclosed_fence", str(path), line_number, "代码围栏未闭合"))
            continue
        if language == "json":
            if re.search(r"(^|[^:])//|/\*|\*/", content):
                issues.append(
                    Issue("error", "json_comment", str(path), line_number, "JSON 代码块包含注释")
                )
            try:
                json.loads(content)
            except json.JSONDecodeError as exc:
                issues.append(
                    Issue(
                        "error",
                        "invalid_json",
                        str(path),
                        line_number,
                        f"JSON 无法严格解析：{exc.msg}",
                    )
                )
        if len(content) > max_section_chars:
            issues.append(
                Issue(
                    "warning",
                    "long_code_block",
                    str(path),
                    line_number,
                    f"代码块 {len(content)} 字符；长度兜底必须保持其原子性",
                )
            )

    text = "\n".join(lines)
    for match in RAG_META_START_RE.finditer(text):
        start = text[: match.start()].count("\n") + 1
        end = text.find("-->", match.end())
        if end < 0:
            issues.append(Issue("error", "unclosed_rag_meta", str(path), start, "rag-meta 注释未闭合"))

    return issues


def proposed_claim_issues(path: Path, lines: list[str]) -> list[Issue]:
    metadata, _ = split_frontmatter(lines)
    if metadata.get("status") != "proposed":
        return []
    text = "\n".join(lines)
    if re.search(r"当前(?:已经)?支持|可直接(?:生成|使用|表达)|正式支持", text):
        return [
            Issue(
                "warning",
                "proposed_as_supported",
                str(path),
                1,
                "status=proposed 的文档含有疑似“当前已支持”表述，请人工核对",
            )
        ]
    return []


def lint_file(path: Path, min_section_chars: int, max_section_chars: int) -> list[Issue]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return [
        *metadata_issues(path, lines),
        *structure_issues(path, lines, min_section_chars, max_section_chars),
        *proposed_claim_issues(path, lines),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint WildAgent RAG Markdown documents.")
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--min-section-chars", type=int, default=120)
    parser.add_argument("--max-section-chars", type=int, default=1600)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    args = parser.parse_args()

    files = iter_markdown_files(args.paths)
    if not files:
        print("没有找到 Markdown 文件", file=sys.stderr)
        return 2

    issues = [
        issue
        for path in files
        for issue in lint_file(path, args.min_section_chars, args.max_section_chars)
    ]

    if args.as_json:
        print(json.dumps([asdict(issue) for issue in issues], ensure_ascii=False, indent=2))
    else:
        for issue in issues:
            print(
                f"{issue.severity.upper():7} {issue.code:26} "
                f"{issue.path}:{issue.line} {issue.message}"
            )
        errors = sum(issue.severity == "error" for issue in issues)
        warnings = sum(issue.severity == "warning" for issue in issues)
        print(f"检查 {len(files)} 个文件：{errors} errors, {warnings} warnings")

    has_errors = any(issue.severity == "error" for issue in issues)
    has_warnings = any(issue.severity == "warning" for issue in issues)
    return 1 if has_errors or (args.strict and has_warnings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
