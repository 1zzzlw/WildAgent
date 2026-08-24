from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Iterable

import yaml


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
)
TERM_FIELDS = {"primary_terms", "synonyms", "keywords"}

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
RAG_META_BLOCK_RE = re.compile(r"<!--\s*rag-meta\s*\n(.*?)-->", re.DOTALL)
COMPOSITION_HEADING_RE = re.compile(r"(?:默认完整构成|完整构成合同|构件构成|组件构成)")
FALLBACK_HEADING_RE = re.compile(r"(?:最少可行回退|最小可行回退|失败回退)")
COMPOSITION_FIELDS = {
    "识别特征": re.compile(r"(?:识别特征|身份特征|关键视觉)"),
    "空间与体量": re.compile(r"(?:空间与体量|空间组织|核心空间|体量)"),
    "主体骨架": re.compile(r"(?:主体骨架|结构骨架|骨架系统)"),
    "外围护": re.compile(r"(?:外围护|围护系统|外立面)"),
    "开口组件": re.compile(r"(?:开口组件|门窗组件|门窗系统)"),
    "交通组件": re.compile(r"(?:交通组件|交通系统|垂直交通)"),
    "附属组件": re.compile(r"(?:附属组件|辅助构件|附加构件)"),
    "重复与模数": re.compile(r"(?:重复与模数|标准层|模数|阵列|复用)"),
    "组装与依附": re.compile(r"(?:组装与依附|组装顺序|依附关系|搭接关系)"),
    "降级映射": re.compile(r"(?:降级映射|适配备注|不支持.*(?:近似|映射|降级))"),
    "构件优先级": re.compile(r"(?:required|characteristic|conditional|optional)"),
}
# 匹配 "X 类/种/个/款" 计数声明（如 "支持 9 类组件"、"11 种构件"）
COUNT_CLAIM_RE = re.compile(
    r"(?:支持\s*)?(\d+|[一二三四五六七八九十]+)\s*(?:类|种|个|款)\s*(?:组件|构件|类型|事物|能力)"
)
CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
TABLE_ROW_RE = re.compile(r"^\s*\|[^|]+\|.*\|\s*$")


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
            if value == "[]":
                result[key] = []
            elif key in TERM_FIELDS and value.startswith("[") and value.endswith("]"):
                result[key] = [
                    _scalar(item) for item in value[1:-1].split(",") if item.strip()
                ]
            elif key in TERM_FIELDS and "," in value:
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


@lru_cache(maxsize=8)
def _read_metadata_config(config_path: str) -> dict[str, object]:
    loaded = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    return loaded if isinstance(loaded, dict) else {}


def _path_metadata(path: Path) -> dict[str, object]:
    """读取最近的 config.yaml，并按 defaults → mapping_rules 解析路径默认值。"""
    config_path = next(
        (parent / "config.yaml" for parent in path.resolve().parents if (parent / "config.yaml").is_file()),
        None,
    )
    if config_path is None:
        return {}
    config = _read_metadata_config(str(config_path))
    defaults = config.get("defaults", {})
    resolved = dict(defaults) if isinstance(defaults, dict) else {}
    relative_path = path.resolve().relative_to(config_path.parent.resolve()).as_posix()
    rules = config.get("mapping_rules", [])
    if not isinstance(rules, list):
        return resolved
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        pattern = str(rule.get("path_pattern") or "").strip()
        rule_metadata = rule.get("metadata", {})
        if pattern and isinstance(rule_metadata, dict) and PurePosixPath(relative_path).match(pattern):
            resolved.update(rule_metadata)
    return resolved


def _resolved_frontmatter(path: Path, lines: list[str]) -> dict[str, object]:
    declared, _ = split_frontmatter(lines)
    return {**_path_metadata(path), **declared}


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
    declared, body_start = split_frontmatter(lines)
    issues: list[Issue] = []
    if not declared:
        return [Issue("error", "missing_frontmatter", str(path), 1, "缺少文档级 YAML frontmatter")]
    path_metadata = _path_metadata(path)
    metadata = {**path_metadata, **declared}

    redundant_fields = sorted(
        key for key, value in declared.items()
        if key in path_metadata and path_metadata[key] == value
    )
    if redundant_fields:
        issues.append(Issue(
            "warning", "redundant_path_metadata", str(path), 1,
            f"以下字段已由 config.yaml 提供，可从文件头删除：{', '.join(redundant_fields)}",
        ))

    for key in REQUIRED_METADATA:
        value = metadata.get(key)
        if key not in metadata or value in (None, "", []):
            issues.append(Issue("error", "missing_metadata", str(path), 1, f"metadata 缺少 {key}"))

    for key, allowed in ALLOWED_VALUES.items():
        value = metadata.get(key)
        if value not in (None, "") and value not in allowed:
            issues.append(
                Issue("error", "invalid_metadata_value", str(path), 1, f"{key}={value!r} 不在允许值中")
            )

    if "keywords" in declared:
        issues.append(Issue(
            "error", "legacy_keywords", str(path), 1,
            "keywords 已停用，请拆成 primary_terms 和 synonyms",
        ))
    issues.extend(_term_field_issues(path, metadata, line=1, require_both=True))
    issues.extend(_term_yaml_syntax_issues(path, lines[1:body_start - 1], line_offset=1))

    text = "\n".join(lines)
    for match in RAG_META_BLOCK_RE.finditer(text):
        rag_metadata = parse_simple_yaml(match.group(1).splitlines())
        line = text[:match.start()].count("\n") + 1
        if "keywords" in rag_metadata:
            issues.append(Issue(
                "error", "legacy_keywords", str(path), line,
                "rag-meta 中的 keywords 已停用，请拆成 primary_terms 和 synonyms",
            ))
        if TERM_FIELDS.intersection(rag_metadata):
            issues.extend(_term_field_issues(path, rag_metadata, line=line, require_both=True))
            issues.extend(_term_yaml_syntax_issues(
                path,
                match.group(1).splitlines(),
                line_offset=line + 1,
            ))

    if metadata.get("doc_type") == "index" and metadata.get("doc_scope") != "index":
        issues.append(Issue("error", "index_scope", str(path), 1, "index 文档必须使用 doc_scope: index"))
    if path.name.casefold() == "readme.md" and metadata.get("doc_scope") != "index":
        issues.append(Issue("warning", "readme_scope", str(path), 1, "README 建议使用 doc_scope: index"))
    return issues


def _term_yaml_syntax_issues(
    path: Path,
    lines: list[str],
    *,
    line_offset: int,
) -> list[Issue]:
    """正式知识库必须使用 YAML 数组，而不是逗号分隔的普通字符串。"""
    issues: list[Issue] = []
    for index, raw_line in enumerate(lines):
        match = re.match(r"^\s*(primary_terms|synonyms):\s*(.*?)\s*$", raw_line)
        if not match:
            continue
        value = match.group(2)
        if value and not (value.startswith("[") and value.endswith("]")):
            issues.append(Issue(
                "error", "term_field_not_yaml_array", str(path), line_offset + index,
                f"{match.group(1)} 必须使用 YAML 数组；推荐换行后逐项写 '- 术语'",
            ))
    return issues


def _term_field_issues(
    path: Path,
    metadata: dict[str, object],
    *,
    line: int,
    require_both: bool,
) -> list[Issue]:
    issues: list[Issue] = []
    primary = metadata.get("primary_terms")
    synonyms = metadata.get("synonyms")
    if require_both and "primary_terms" not in metadata:
        issues.append(Issue("error", "missing_primary_terms", str(path), line, "缺少 primary_terms"))
    if require_both and "synonyms" not in metadata:
        issues.append(Issue("error", "missing_synonyms", str(path), line, "缺少 synonyms"))
    if primary is not None and (not isinstance(primary, list) or not primary):
        issues.append(Issue(
            "error", "invalid_primary_terms", str(path), line,
            "primary_terms 必须是至少包含一个词的 YAML 数组",
        ))
    if synonyms is not None and not isinstance(synonyms, list):
        issues.append(Issue(
            "error", "invalid_synonyms", str(path), line,
            "synonyms 必须是 YAML 数组；没有同义词时写 []",
        ))
    if isinstance(primary, list) and isinstance(synonyms, list):
        overlap = sorted(
            {str(item).casefold() for item in primary}
            & {str(item).casefold() for item in synonyms}
        )
        if overlap:
            issues.append(Issue(
                "error", "overlapping_terms", str(path), line,
                f"主术语与同义词重复：{', '.join(overlap)}",
            ))
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
    metadata = _resolved_frontmatter(path, lines)
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


def _heading_subtree(
    lines: list[str],
    headings: list[Heading],
    index: int,
) -> tuple[int, list[str]]:
    heading = headings[index]
    end_line = len(lines)
    for candidate in headings[index + 1:]:
        if candidate.level <= heading.level:
            end_line = candidate.line - 1
            break
    return end_line, lines[heading.line:end_line]


def _rag_meta_in_intro(lines: list[str], heading: Heading) -> list[dict[str, object]]:
    intro = "\n".join(lines[heading.line:heading.end_line])
    return [
        parse_simple_yaml(match.group(1).splitlines())
        for match in RAG_META_BLOCK_RE.finditer(intro)
    ]


def building_composition_issues(path: Path, lines: list[str]) -> list[Issue]:
    """Warn when a detailed building entity was reduced to a minimal prose summary."""
    metadata = _resolved_frontmatter(path, lines)
    if metadata.get("doc_type") != "building_type" or "catalog" in {
        part.casefold() for part in path.parts
    }:
        return []

    headings, _, _ = scan_structure(lines)
    entity_indices = [
        index
        for index, heading in enumerate(headings)
        if heading.level == 2
        and any(meta.get("entity_type") == "building" for meta in _rag_meta_in_intro(lines, heading))
    ]

    # A single-entity building document can rely on document-level metadata.
    if not entity_indices and metadata.get("entity_type") == "building":
        document_text = "\n".join(lines)
        return _composition_contract_issues(
            path,
            int(next((heading.line for heading in headings if heading.level == 1), 1)),
            str(metadata.get("entity_name") or path.stem),
            document_text,
        )

    issues: list[Issue] = []
    for index in entity_indices:
        heading = headings[index]
        _, subtree_lines = _heading_subtree(lines, headings, index)
        issues.extend(_composition_contract_issues(
            path,
            heading.line,
            heading.title,
            "\n".join(subtree_lines),
        ))
    return issues


def _composition_contract_issues(
    path: Path,
    line: int,
    entity: str,
    text: str,
) -> list[Issue]:
    issues: list[Issue] = []
    if not COMPOSITION_HEADING_RE.search(text):
        issues.append(Issue(
            "error",
            "missing_composition_contract",
            str(path),
            line,
            f"建筑实体 {entity!r} 缺少默认完整构成合同；最小表达或单段摘要不能替代",
        ))
        return issues

    missing_fields = [
        name for name, pattern in COMPOSITION_FIELDS.items() if not pattern.search(text)
    ]
    if missing_fields:
        issues.append(Issue(
            "error",
            "incomplete_composition_contract",
            str(path),
            line,
            f"建筑实体 {entity!r} 的构成合同缺少：{', '.join(missing_fields)}",
        ))
    if not FALLBACK_HEADING_RE.search(text):
        issues.append(Issue(
            "warning",
            "missing_fallback_contract",
            str(path),
            line,
            f"建筑实体 {entity!r} 缺少独立的最少可行回退，容易让最小集合覆盖默认构成",
        ))
    return issues


def lint_file(path: Path, min_section_chars: int, max_section_chars: int) -> list[Issue]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return [
        *metadata_issues(path, lines),
        *structure_issues(path, lines, min_section_chars, max_section_chars),
        *proposed_claim_issues(path, lines),
        *building_composition_issues(path, lines),
    ]


def cross_check_issues(path: Path) -> list[Issue]:
    """检查文档中声称的数字是否与紧随的表格/列表实际行数一致。"""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    issues: list[Issue] = []

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        match = COUNT_CLAIM_RE.search(line)
        if not match:
            continue
        claimed_str = match.group(1)
        claimed = CN_NUM.get(claimed_str, None)
        if claimed is None:
            try:
                claimed = int(claimed_str)
            except ValueError:
                continue

        # 在后续 10 行内找最近的表格
        actual = 0
        found_table = False
        table_start = 0
        for offset in range(1, min(11, len(lines) - line_number)):
            next_line = lines[line_number - 1 + offset].strip()
            # 表格分隔行（|---|---|）标志着一个表的存在
            if re.match(r"^\s*\|(?:\s*:?-{3,}:?\s*\|)+\s*$", next_line):
                found_table = True
                table_start = line_number + offset
                # 统计表头行之前的行是否也算是表行？回溯找表头
                if offset >= 1:
                    prev_line = lines[line_number - 1 + offset - 1].strip()
                    if TABLE_ROW_RE.match(prev_line):
                        actual = 1  # 表头
                # 从分隔行之后统计数据行
                for data_offset in range(1, min(51, len(lines) - table_start)):
                    data_line = lines[table_start + data_offset].strip()
                    if TABLE_ROW_RE.match(data_line):
                        actual += 1
                    elif not data_line or data_line.startswith("#") or data_line.startswith(">"):
                        break
                    else:
                        if not data_line.startswith("|"):
                            break
                break
            # 如果 3 行内找不到表格，跳过此计数声明
            if offset >= 3:
                break

        if found_table and actual != claimed:
            issues.append(Issue(
                "error",
                "count_mismatch",
                str(path),
                line_number,
                f"声称 {claimed} 类/种/个，但紧随的表格实际有 {actual} 行数据",
            ))

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint WildAgent RAG Markdown documents.")
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--min-section-chars", type=int, default=120)
    parser.add_argument("--max-section-chars", type=int, default=1600)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    parser.add_argument("--cross-check", action="store_true", help="Check claimed counts against actual table rows.")
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
    if args.cross_check:
        issues.extend([
            issue
            for path in files
            for issue in cross_check_issues(path)
        ])

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
