from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


REQUIRED_METADATA = {
    "doc_type",
    "doc_scope",
    "knowledge_layer",
    "entity_type",
    "entity_name",
    "topic",
    "wild_version",
    "status",
    "authority",
    "keywords",
    "heading_path",
    "parent_chunk_id",
    "part_index",
}
HEADING_RE = re.compile(r"^#{1,5}\s+")
SEPARATOR_RE = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})$")
DETACHED_LABEL_RE = re.compile(r"(?:JSON|代码|示例|配置|如下)[：:]?\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class PreviewIssue:
    severity: str
    code: str
    source: str
    heading: str
    part_index: int
    message: str


def find_project_root(script_path: Path) -> Path:
    for candidate in script_path.resolve().parents:
        if (candidate / "wild-server" / "app" / "spec" / "loader.py").is_file():
            return candidate
    raise RuntimeError("无法定位 WildAgent 项目根目录")


def iter_markdown_files(inputs: Iterable[Path]) -> list[Path]:
    files: set[Path] = set()
    for input_path in inputs:
        path = input_path.resolve()
        if path.is_dir():
            files.update(item for item in path.rglob("*.md") if item.is_file())
        elif path.is_file() and path.suffix.casefold() == ".md":
            files.add(path)
    return sorted(files, key=lambda item: str(item).casefold())


def payload_lines(document: str) -> list[str]:
    lines: list[str] = []
    for line in document.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("> 知识路径："):
            continue
        if HEADING_RE.match(stripped) or SEPARATOR_RE.fullmatch(stripped):
            continue
        lines.append(stripped)
    return lines


def audit_chunks(
    chunks: list[object],
    chunk_size: int,
    min_payload_chars: int,
    max_parts_per_parent: int,
) -> list[PreviewIssue]:
    issues: list[PreviewIssue] = []
    chunks_by_parent: dict[str, list[object]] = defaultdict(list)

    for chunk in chunks:
        metadata = chunk.metadata
        source = str(metadata.get("source_file") or metadata.get("source") or "unknown")
        heading = str(metadata.get("heading") or "")
        part_index = int(metadata.get("part_index") or 0)
        chunks_by_parent[str(metadata.get("parent_chunk_id") or chunk.id)].append(chunk)

        missing = sorted(REQUIRED_METADATA - metadata.keys())
        if missing:
            issues.append(PreviewIssue(
                "error", "missing_chunk_metadata", source, heading, part_index,
                f"chunk 缺少 metadata：{', '.join(missing)}",
            ))
        if "rag-meta" in chunk.document:
            issues.append(PreviewIssue(
                "error", "rag_meta_leaked", source, heading, part_index,
                "rag-meta 注释泄漏到向量正文",
            ))
        if not chunk.document.startswith("> 知识路径："):
            issues.append(PreviewIssue(
                "error", "missing_knowledge_path", source, heading, part_index,
                "chunk 正文没有知识路径",
            ))

        payload = "\n".join(payload_lines(chunk.document))
        if not payload:
            issues.append(PreviewIssue(
                "error", "empty_payload", source, heading, part_index,
                "去除标题和分隔线后没有有效正文",
            ))
        elif len(payload) < min_payload_chars:
            issues.append(PreviewIssue(
                "warning", "thin_payload", source, heading, part_index,
                f"有效正文仅 {len(payload)} 字符，确认它能独立回答问题",
            ))
        if len(chunk.document) > chunk_size:
            issues.append(PreviewIssue(
                "warning", "oversized_atomic_chunk", source, heading, part_index,
                f"原子 chunk 为 {len(chunk.document)} 字符，超过配置 {chunk_size}",
            ))

    for siblings in chunks_by_parent.values():
        siblings.sort(key=lambda chunk: int(chunk.metadata.get("part_index") or 0))
        first = siblings[0]
        source = str(first.metadata.get("source_file") or first.metadata.get("source") or "unknown")
        heading = str(first.metadata.get("heading") or "")
        if len(siblings) > max_parts_per_parent:
            issues.append(PreviewIssue(
                "warning", "too_many_parts", source, heading, 0,
                f"同一业务标题产生 {len(siblings)} 个 part，优先增加真实子标题",
            ))
        for previous, current in zip(siblings, siblings[1:]):
            previous_payload = payload_lines(previous.document)
            current_payload = payload_lines(current.document)
            if not previous_payload or not current_payload:
                continue
            current_first = current_payload[0]
            starts_atomic = (
                current_first.startswith("```")
                or current_first.startswith("~~~")
                or current_first.startswith("|")
            )
            if starts_atomic and DETACHED_LABEL_RE.search(previous_payload[-1]):
                issues.append(PreviewIssue(
                    "error", "detached_atomic_block", source, heading,
                    int(current.metadata.get("part_index") or 0),
                    "说明标签留在前一 part，代码块或表格落入后一 part",
                ))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview Markdown through WildAgent's real RAG chunker.",
    )
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--chunk-size", type=int, default=900)
    parser.add_argument("--chunk-overlap", type=int, default=150)
    parser.add_argument("--min-payload-chars", type=int, default=20)
    parser.add_argument("--max-parts-per-parent", type=int, default=4)
    parser.add_argument("--show-chunks", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    files = iter_markdown_files(args.paths)
    if not files:
        print("没有找到 Markdown 文件", file=sys.stderr)
        return 2

    project_root = find_project_root(Path(__file__))
    server_root = project_root / "wild-server"
    sys.path.insert(0, str(server_root))
    from app.spec.loader import MarkdownChunker

    chunker = MarkdownChunker(args.chunk_size, args.chunk_overlap)
    chunks = [
        chunk
        for path in files
        for chunk in chunker.split_file(path, namespace="skill_preview")
    ]
    issues = audit_chunks(
        chunks,
        chunker.chunk_size,
        args.min_payload_chars,
        args.max_parts_per_parent,
    )

    if args.as_json:
        print(json.dumps({
            "files": [str(path) for path in files],
            "chunk_count": len(chunks),
            "chunks": [
                {
                    "id": chunk.id,
                    "source": chunk.metadata.get("source_file"),
                    "heading": chunk.metadata.get("heading"),
                    "entity_name": chunk.metadata.get("entity_name"),
                    "topic": chunk.metadata.get("topic"),
                    "part_index": chunk.metadata.get("part_index"),
                    "chars": len(chunk.document),
                }
                for chunk in chunks
            ] if args.show_chunks else [],
            "issues": [asdict(issue) for issue in issues],
        }, ensure_ascii=False, indent=2))
    else:
        if args.show_chunks:
            for chunk in chunks:
                print(
                    f"CHUNK {chunk.metadata.get('source_file')} | "
                    f"{chunk.metadata.get('heading')} | "
                    f"part={chunk.metadata.get('part_index')} | "
                    f"chars={len(chunk.document)} | "
                    f"entity={chunk.metadata.get('entity_name')}"
                )
        for issue in issues:
            print(
                f"{issue.severity.upper():7} {issue.code:24} "
                f"{issue.source} / {issue.heading} / part={issue.part_index}: "
                f"{issue.message}"
            )
        errors = sum(issue.severity == "error" for issue in issues)
        warnings = sum(issue.severity == "warning" for issue in issues)
        print(f"预览 {len(files)} 个文件、{len(chunks)} 个 chunks：{errors} errors, {warnings} warnings")

    has_errors = any(issue.severity == "error" for issue in issues)
    has_warnings = any(issue.severity == "warning" for issue in issues)
    return 1 if has_errors or (args.strict and has_warnings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
