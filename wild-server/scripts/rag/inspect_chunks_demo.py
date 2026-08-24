"""
RAG 分片检查与展示脚本

功能：
1. 使用 MarkdownChunker 对知识库文件进行分片
2. 控制台打印每个分片的详细信息（来源、字符数、内容摘要、合法性检查）
3. 将分片展示信息写入 Markdown 文件，用于直观展示分片效果

运行方式（在 wild-server 目录下）：
    .\\.venv\\Scripts\\activate
    $env:PYTHONPATH="."
    python scripts/rag/inspect_chunks_demo.py [文件或目录路径]

示例：
    python scripts/rag/inspect_chunks_demo.py storage/knowledge_base/building_types/residential/villas.md
    python scripts/rag/inspect_chunks_demo.py storage/knowledge_base
"""

import argparse
import hashlib
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

# 设置 stdout 为 UTF-8（解决 Windows 控制台中文乱码）
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from app.spec.loader import MarkdownChunker, collect_markdown_paths


# ── 合法性检查 ──────────────────────────────────────────────────────


def check_chunk_legality(document: str, metadata: dict) -> list[str]:
    """检查单个分片的合法性，返回问题列表（空列表表示合法）。"""
    issues = []
    if not document or not document.strip():
        issues.append("分片内容为空")
    if "rag-meta" in document and "<!--" not in document:
        # rag-meta 注释未被移除（原始注释应被 loader 剥离）
        issues.append("包含未处理的 rag-meta 标记")
    if metadata.get("content_hash") and len(document) > 0:
        actual_hash = hashlib.sha256(document.encode("utf-8")).hexdigest()[:16]
        if actual_hash != metadata.get("content_hash"):
            issues.append("content_hash 与实际内容不匹配")
    # 检查标题路径是否为空
    if not metadata.get("heading"):
        issues.append("缺少 heading 元数据")
    return issues


# ── 元数据字段展示（MarkdownChunker 全部 metadata 字段，按分组） ────


METADATA_FIELD_GROUPS = [
    ("定位/溯源", ["path", "_source", "source_file", "_extension", "_file_name", "declared_source"]),
    ("分片结构", ["namespace", "heading_path", "parent_chunk_id", "part_index", "chunk_index"]),
    ("内容校验", ["body_hash", "content_hash"]),
    ("时间", ["mtime"]),
    ("文档分类", ["doc_scope", "knowledge_layer", "entity_type", "topic", "wild_version",
                  "primary_terms", "synonyms", "building_category", "entity_aliases",
                  "constraint_tags", "role_tags", "keywords"]),
]


def format_metadata_value(value):
    """将 metadata 值格式化为可展示文本：缺失/空显示 '-'，list 用 '; ' 连接，时间戳转为可读时间。"""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)) and value > 1e9:
        # 大于 1e9 的数值视为 Unix 时间戳（秒），转为可读时间
        try:
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(value))
        except (OSError, ValueError, OverflowError):
            return str(value)
    if isinstance(value, (list, tuple, set)):
        items = [str(v) for v in value if v not in (None, "")]
        return "; ".join(items) if items else "-"
    s = str(value).strip()
    return s if s else "-"


def render_metadata_groups(metadata: dict, show_missing: bool = False) -> list[tuple[str, str]]:
    """按分组渲染补充元数据字段，返回 [(分组名, 字段=值 拼接串), ...]。

    - show_missing=False: 仅渲染分组内实际存在的字段（控制台用）
    - show_missing=True:  分组内所有字段均渲染，缺失显示 '-'（Markdown 报告用）
    """
    rendered = []
    for group_name, fields in METADATA_FIELD_GROUPS:
        pairs = []
        for f in fields:
            if f not in metadata or metadata.get(f) in (None, ""):
                if show_missing:
                    pairs.append(f"{f}=-")
                continue
            pairs.append(f"{f}={format_metadata_value(metadata.get(f))}")
        if pairs:
            rendered.append((group_name, "  |  ".join(pairs)))
    return rendered


# ── 控制台输出双写（Tee） ───────────────────────────────────────────


class Tee:
    """将写入内容同时分发到多个流（控制台 + 日志文件），每次写入后 flush 保证双端一致。"""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            s.write(data)
            s.flush()

    def flush(self):
        for s in self.streams:
            s.flush()

    def isatty(self):
        return self.streams[0].isatty()

    def fileno(self):
        return self.streams[0].fileno()

    def __getattr__(self, name):
        return getattr(self.streams[0], name)


# ── 控制台输出 ──────────────────────────────────────────────────────


def print_chunk_detail(chunk, index: int, show_full: bool = False):
    """打印单个分片的详细信息到控制台。"""
    m = chunk.metadata
    print(f"\n{'─' * 78}")
    print(f"  ▸ 分片 #{index + 1}")
    print(f"    ID: {chunk.id}")
    print(f"    来源: {m.get('source', '-')}")
    print(f"    标题路径: {m.get('heading', '-')}")
    print(f"    实体: {m.get('entity_name', '-')}  |  类型: {m.get('doc_type', '-')}")
    print(f"    长度: {len(chunk.document)} 字符")
    print(f"    状态: {m.get('status', '-')}  |  权威性: {m.get('authority', '-')}")

    # 补充元数据字段（按分组，仅显示实际存在的字段）
    for group_name, text in render_metadata_groups(m, show_missing=False):
        print(f"    {group_name}: {text}")

    # 合法性检查
    issues = check_chunk_legality(chunk.document, m)
    if issues:
        print(f"    合法性: ❌ {'; '.join(issues)}")
    else:
        print(f"    合法性: ✅ 通过")

    # 内容摘要
    if show_full:
        lines = chunk.document.splitlines()
        print(f"    完整内容 ({len(lines)} 行):")
        for line in lines[:20]:
            print(f"      {line}")
        if len(lines) > 20:
            print(f"      ... (共 {len(lines)} 行，仅显示前 20 行)")
    else:
        text = chunk.document[:200].replace("\n", "\\n")
        if len(chunk.document) > 200:
            text += "..."
        # 从 '知识路径：' 后截取更简洁的摘要
        if "知识路径：" in chunk.document:
            after_path = chunk.document.split("知识路径：", 1)[1]
            summary = after_path.split("\n", 1)[1].strip() if "\n" in after_path else after_path
            summary = summary[:200]
            if len(summary) > 200:
                summary += "..."
            print(f"    内容摘要: {summary}")
        else:
            print(f"    内容摘要: {text}")


def print_statistics(chunks, elapsed: float):
    """打印统计信息到控制台。"""
    print(f"\n{'=' * 78}")
    print(f"  📊 统计汇总")
    print(f"{'=' * 78}")
    print(f"  总分片数: {len(chunks)}")
    print(f"  处理耗时: {elapsed:.3f} 秒")

    if not chunks:
        return

    lengths = [len(c.document) for c in chunks]
    print(f"\n  长度分布:")
    print(f"    最小: {min(lengths)} 字符")
    print(f"    最大: {max(lengths)} 字符")
    print(f"    平均: {sum(lengths) // len(lengths)} 字符")
    print(f"    中位数: {sorted(lengths)[len(lengths) // 2]} 字符")

    # 按文件分组
    by_source = Counter(c.metadata.get("source", "unknown") for c in chunks)
    if len(by_source) > 1:
        print(f"\n  按文件分组:")
        for source, count in sorted(by_source.items()):
            print(f"    {source}: {count} 个分片")

    # 按实体
    by_entity = Counter(c.metadata.get("entity_name", "(无)") for c in chunks)
    print(f"\n  按实体名称:")
    for entity, count in sorted(by_entity.items(), key=lambda x: -x[1])[:10]:
        print(f"    {entity}: {count} 个分片")

    # 按 doc_type
    by_type = Counter(c.metadata.get("doc_type", "(无)") for c in chunks)
    print(f"\n  按文档类型:")
    for t, count in sorted(by_type.items()):
        print(f"    {t}: {count} 个分片")

    # 合法性统计
    all_issues = {}
    for i, c in enumerate(chunks):
        issues = check_chunk_legality(c.document, c.metadata)
        if issues:
            all_issues[i + 1] = issues
    if all_issues:
        print(f"\n  合法性检查:")
        print(f"    ❌ {len(all_issues)}/{len(chunks)} 个分片存在问题")
        for idx, issues in all_issues.items():
            print(f"      分片 #{idx}: {'; '.join(issues)}")
    else:
        print(f"\n  合法性检查: ✅ 全部 {len(chunks)} 个分片通过")


# ── Markdown 输出 ───────────────────────────────────────────────────


def chunks_to_markdown(chunks, source_label: str, elapsed: float) -> str:
    """将分片信息格式化为 Markdown 展示文件。"""
    lines = []
    lines.append(f"# RAG 分片检查报告")
    lines.append(f"")
    lines.append(f"- **生成时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- **数据来源**: {source_label}")
    lines.append(f"- **处理耗时**: {elapsed:.3f} 秒")
    lines.append(f"- **总分片数**: {len(chunks)}")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    if not chunks:
        lines.append("> 未生成任何分片，请检查输入路径。")
        return "\n".join(lines)

    # ── 统计概览 ──
    lengths = [len(c.document) for c in chunks]
    lines.append(f"## 统计概览")
    lines.append(f"")
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|---|---|")
    lines.append(f"| 总分片数 | {len(chunks)} |")
    lines.append(f"| 最小长度 | {min(lengths)} 字符 |")
    lines.append(f"| 最大长度 | {max(lengths)} 字符 |")
    lines.append(f"| 平均长度 | {sum(lengths) // len(lengths)} 字符 |")
    lines.append(f"| 中位长度 | {sorted(lengths)[len(lengths) // 2]} 字符 |")
    lines.append(f"| 处理耗时 | {elapsed:.3f} 秒 |")
    lines.append(f"")

    # 按文件分组
    by_source = Counter(c.metadata.get("source", "unknown") for c in chunks)
    if len(by_source) > 1:
        lines.append(f"### 按文件分布")
        lines.append(f"")
        lines.append(f"| 文件 | 分片数 |")
        lines.append(f"|---|---|")
        for source, count in sorted(by_source.items()):
            lines.append(f"| {source} | {count} |")
        lines.append(f"")

    # 按实体分组
    by_entity = Counter(c.metadata.get("entity_name", "(无)") for c in chunks)
    lines.append(f"### 按实体分布")
    lines.append(f"")
    lines.append(f"| 实体名称 | 分片数 |")
    lines.append(f"|---|---|")
    for entity, count in sorted(by_entity.items(), key=lambda x: -x[1])[:10]:
        lines.append(f"| {entity} | {count} |")
    lines.append(f"")

    # ── 合法性检查 ──
    lines.append(f"## 合法性检查")
    lines.append(f"")
    illegal_count = 0
    for i, c in enumerate(chunks):
        issues = check_chunk_legality(c.document, c.metadata)
        if issues:
            illegal_count += 1
    if illegal_count == 0:
        lines.append(f"✅ **全部 {len(chunks)} 个分片通过合法性检查**")
    else:
        lines.append(f"❌ **{illegal_count}/{len(chunks)} 个分片存在以下问题**")
        lines.append(f"")
        for i, c in enumerate(chunks):
            issues = check_chunk_legality(c.document, c.metadata)
            if issues:
                lines.append(f"- 分片 #{i + 1}: {'; '.join(issues)}")
    lines.append(f"")

    # ── 分片明细 ──
    lines.append(f"## 分片明细")
    lines.append(f"")
    lines.append(f"| # | 来源 | 标题路径 | 实体 | 类型 | 长度 | 状态 | 合法性 |")
    lines.append(f"|---|------|----------|------|------|------|------|--------|")
    for i, c in enumerate(chunks):
        m = c.metadata
        issues = check_chunk_legality(c.document, m)
        legal = "✅" if not issues else "❌"
        heading = m.get("heading", "-") or "-"
        if len(heading) > 50:
            heading = heading[:47] + "..."
        lines.append(
            f"| {i + 1} | {m.get('source', '-')} | {heading} "
            f"| {m.get('entity_name', '-')} | {m.get('doc_type', '-')} "
            f"| {len(c.document)} | {m.get('status', '-')} | {legal} |"
        )
    lines.append(f"")

    # ── 每个分片的详细内容 ──
    lines.append(f"## 分片详细内容")
    lines.append(f"")
    for i, c in enumerate(chunks):
        m = c.metadata
        lines.append(f"### 分片 #{i + 1}: {m.get('heading', '-')}")
        lines.append(f"")
        lines.append(f"- **ID**: `{c.id}`")
        lines.append(f"- **来源**: {m.get('source', '-')}")
        lines.append(f"- **实体**: {m.get('entity_name', '-')}  |  **类型**: {m.get('doc_type', '-')}")
        lines.append(f"- **长度**: {len(c.document)} 字符")
        lines.append(f"- **状态**: {m.get('status', '-')}  |  **权威性**: {m.get('authority', '-')}")
        # 补充元数据字段（按分组完整列出，缺失显示 '-'）
        for group_name, text in render_metadata_groups(m, show_missing=True):
            lines.append(f"- **{group_name}**: {text}")
        issues = check_chunk_legality(c.document, m)
        lines.append(f"- **合法性**: {'✅ 通过' if not issues else '❌ ' + '; '.join(issues)}")
        lines.append(f"")
        lines.append(f"```text")
        # 内容限制显示，避免文件过大
        doc_lines = c.document.splitlines()
        for dl in doc_lines[:50]:
            lines.append(dl)
        if len(doc_lines) > 50:
            lines.append(f"... (共 {len(doc_lines)} 行，仅显示前 50 行)")
        lines.append(f"```")
        lines.append(f"")

    lines.append(f"---")
    lines.append(f"*报告由 `inspect_chunks_demo.py` 于 {time.strftime('%Y-%m-%d %H:%M:%S')} 自动生成*")
    return "\n".join(lines)


# ── 主逻辑 ──────────────────────────────────────────────────────────


def inspect_file(file_path: Path, chunk_size: int, chunk_overlap: int, show_full: bool):
    """检查单个文件的分片。"""
    label = str(file_path)
    print(f"\n{'=' * 78}")
    print(f"  处理文件: {label}")
    print(f"  配置: chunk_size={chunk_size}, chunk_overlap={chunk_overlap}")
    print(f"{'=' * 78}")

    chunker = MarkdownChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    t0 = time.time()
    chunks = chunker.split_file(file_path, namespace="test")
    elapsed = time.time() - t0

    print(f"\n  生成 {len(chunks)} 个分片")
    for i, c in enumerate(chunks):
        print_chunk_detail(c, i, show_full=show_full)

    print_statistics(chunks, elapsed)
    return chunks, label, elapsed


def inspect_directory(dir_path: Path, chunk_size: int, chunk_overlap: int, show_full: bool, file_limit: int | None):
    """检查目录下所有 Markdown 文件的分片。"""
    label = str(dir_path)
    print(f"\n{'=' * 78}")
    print(f"  扫描目录: {label}")
    print(f"  配置: chunk_size={chunk_size}, chunk_overlap={chunk_overlap}")
    print(f"{'=' * 78}")

    paths = collect_markdown_paths(dir_path)
    if not paths:
        print("\n  未找到 Markdown 文件")
        return [], label, 0

    print(f"\n  找到 {len(paths)} 个 Markdown 文件")
    if file_limit:
        paths = paths[:file_limit]
        print(f"  限制处理前 {file_limit} 个文件")

    chunker = MarkdownChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    all_chunks = []
    t0 = time.time()
    for p in paths:
        rel = p.relative_to(dir_path)
        print(f"\n  ── 处理: {rel}")
        chunks = chunker.split_file(p, namespace="test")
        print(f"     生成 {len(chunks)} 个分片")
        for i, c in enumerate(chunks):
            print_chunk_detail(c, i + len(all_chunks), show_full=show_full)
        all_chunks.extend(chunks)
    elapsed = time.time() - t0

    print(f"\n{'=' * 78}")
    print(f"  目录扫描完成，共 {len(all_chunks)} 个分片")
    print_statistics(all_chunks, elapsed)
    return all_chunks, label, elapsed


def main():
    parser = argparse.ArgumentParser(
        description="RAG 分片检查与展示脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n\n"
            "  # 检查单个文件\n"
            "  python scripts/rag/inspect_chunks_demo.py storage/knowledge_base/.../villas.md\n\n"
            "  # 检查整个知识库\n"
            "  python scripts/rag/inspect_chunks_demo.py storage/knowledge_base\n\n"
            "  # 自定义分片参数\n"
            "  python scripts/rag/inspect_chunks_demo.py storage/knowledge_base --chunk-size 600 --chunk-overlap 100\n\n"
            "  # 显示完整内容\n"
            "  python scripts/rag/inspect_chunks_demo.py storage/knowledge_base --show-full\n\n"
            "  # 限制文件数\n"
            "  python scripts/rag/inspect_chunks_demo.py storage/knowledge_base --limit 3\n\n"
            "  # 自定义控制台日志路径\n"
            "  python scripts/rag/inspect_chunks_demo.py storage/knowledge_base --log-output logs/console.txt\n\n"
            "  # 关闭控制台日志保存\n"
            "  python scripts/rag/inspect_chunks_demo.py storage/knowledge_base --no-log-output\n"
        ),
    )
    parser.add_argument("path", type=Path, help="Markdown 文件或目录路径")
    parser.add_argument("--chunk-size", type=int, default=900, help="分片大小（默认: 900）")
    parser.add_argument("--chunk-overlap", type=int, default=150, help="分片重叠（默认: 150）")
    parser.add_argument("--show-full", action="store_true", help="显示每个分片的完整内容")
    parser.add_argument("--limit", type=int, help="限制处理的文件数量（仅目录模式）")
    parser.add_argument("--output", type=Path, help="输出 Markdown 文件路径（默认自动生成到 scripts/ 目录）")
    parser.add_argument("--log-output", type=Path, help="控制台日志保存路径（默认自动生成到 scripts/ 目录，命名 chunks_console_<时间戳>.txt）")
    parser.add_argument("--no-log-output", action="store_true", help="不保存控制台日志（默认会保存）")

    args = parser.parse_args()

    # ── 控制台日志双写（Tee）：默认启用，--no-log-output 关闭，--log-output 自定义路径 ──
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = None
    if not args.no_log_output:
        if args.log_output:
            log_path = args.log_output.resolve()
        else:
            reports_dir = Path(__file__).resolve().parents[1] / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            log_path = reports_dir / f"chunks_console_{timestamp}.txt"
        try:
            log_file = open(log_path, "w", encoding="utf-8")
        except OSError as e:
            print(f"警告: 无法创建控制台日志文件 {log_path}: {e}")
        else:
            sys.stdout = Tee(sys.stdout, log_file)
            print(f"控制台输出将同时保存到: {log_path}")

    path = args.path.resolve()

    if not path.exists():
        print(f"错误: 路径不存在: {path}")
        return 1

    if path.is_file():
        chunks, label, elapsed = inspect_file(
            path, args.chunk_size, args.chunk_overlap, args.show_full
        )
    elif path.is_dir():
        chunks, label, elapsed = inspect_directory(
            path, args.chunk_size, args.chunk_overlap, args.show_full, args.limit
        )
    else:
        print(f"错误: 不支持的路径类型: {path}")
        return 1

    # ── 写入 Markdown 展示文件 ──
    if args.output:
        md_path = args.output.resolve()
    else:
        reports_dir = Path(__file__).resolve().parents[1] / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        md_path = reports_dir / f"chunks_report_{timestamp}.md"

    md_content = chunks_to_markdown(chunks, label, elapsed)
    md_path.write_text(md_content, encoding="utf-8")
    print(f"\n{'=' * 78}")
    print(f"  ✅ 展示文件已生成: {md_path}")
    print(f"  文件大小: {len(md_content)} 字符, {md_path.stat().st_size} 字节")
    print(f"{'=' * 78}\n")

    return 0


if __name__ == "__main__":
    exit(main())
