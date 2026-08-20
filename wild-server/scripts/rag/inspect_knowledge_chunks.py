"""
知识库分片检查工具

功能：
1. 对指定 Markdown 文件或整个知识库目录进行分片
2. 打印每个分片的详细信息（metadata、内容摘要）
3. 统计分片数量、大小分布等
4. 可用于验证知识库配置和分片策略
"""
import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

# 设置输出编码为 UTF-8（解决 Windows PowerShell 中文乱码）
import io
import codecs
if sys.platform == 'win32':
    # 强制使用 UTF-8 编码输出
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    # 设置默认编码
    if hasattr(sys, '_base_executable'):  # Python 3.3+
        import locale
        locale.setlocale(locale.LC_ALL, '')

from app.spec.loader import MarkdownChunker, collect_markdown_paths


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


def format_metadata(metadata: dict, indent: str = "  ") -> str:
    """格式化 metadata 为易读的多行字符串"""
    lines = []
    for key, value in sorted(metadata.items()):
        if key.startswith("_"):
            continue  # 跳过内部字段
        if isinstance(value, (int, float)):
            lines.append(f"{indent}{key}: {value}")
        else:
            lines.append(f"{indent}{key}: {value!r}")
    return "\n".join(lines)


def print_chunk_summary(chunk, index: int, show_content: bool = False):
    """打印单个分片的摘要信息"""
    print(f"\n{'='*80}")
    print(f"分片 #{index + 1}")
    print(f"{'='*80}")
    
    # 基本信息
    print(f"ID: {chunk.id}")
    print(f"文档长度: {len(chunk.document)} 字符")
    
    # Metadata
    print("\nMetadata:")
    print(format_metadata(chunk.metadata))
    
    # 内容预览
    if show_content:
        print("\n完整内容:")
        print("-" * 80)
        print(chunk.document)
        print("-" * 80)
    else:
        # 只显示前 200 字符
        preview = chunk.document[:200]
        if len(chunk.document) > 200:
            preview += "..."
        print("\n内容预览:")
        print("-" * 80)
        print(preview)
        print("-" * 80)


def print_chunks_table(chunks):
    """以表格形式打印分片信息"""
    if not chunks:
        print("没有生成任何分片")
        return
    
    # 使用更紧凑的表格格式
    print(f"\n{'='*100}")
    print("分片信息表")
    print(f"{'='*100}")
    
    # 表头（缩短列宽）
    print(f"{'No':<4} {'文件':<15} {'实体':<18} {'类型':<8} {'长度':<6} {'分类':<8}")
    print(f"{'-'*4} {'-'*15} {'-'*18} {'-'*8} {'-'*6} {'-'*8}")
    
    # 打印每一行
    for i, chunk in enumerate(chunks):
        m = chunk.metadata
        
        # 提取字段，处理缺失值和长度
        row = {
            "no": str(i + 1),
            "file": (m.get("source", "-") or "-")[:15],
            "entity": (m.get("entity_name", "-") or "-")[:18],
            "type": (m.get("doc_type", "-") or "-")[:8],
            "length": str(len(chunk.document)),
            "category": (m.get("building_category", "-") or "-")[:8],
        }
        
        print(f"{row['no']:<4} {row['file']:<15} {row['entity']:<18} {row['type']:<8} {row['length']:<6} {row['category']:<8}")
    
    print(f"{'-'*100}")
    print(f"总计: {len(chunks)} 个分片")
    
    # 打印简化的标题路径列表
    print(f"\n{'='*100}")
    print("标题路径列表")
    print(f"{'='*100}")
    for i, chunk in enumerate(chunks):
        heading = chunk.metadata.get("heading", "-")
        # 截断过长的标题
        if len(heading) > 80:
            heading = heading[:77] + "..."
        print(f"{i+1:3}. {heading}")
    print(f"{'='*100}\n")


def analyze_chunks(chunks):
    """分析分片统计信息"""
    if not chunks:
        print("没有生成任何分片")
        return
    
    print(f"\n{'='*80}")
    print("统计分析")
    print(f"{'='*80}")
    
    # 基本统计
    total = len(chunks)
    print(f"\n总分片数: {total}")
    
    # 长度分布
    lengths = [len(chunk.document) for chunk in chunks]
    print(f"\n长度统计:")
    print(f"  最小: {min(lengths)} 字符")
    print(f"  最大: {max(lengths)} 字符")
    print(f"  平均: {sum(lengths) // total} 字符")
    print(f"  中位数: {sorted(lengths)[total // 2]} 字符")
    
    # 按文件分组
    by_source = defaultdict(int)
    for chunk in chunks:
        source = chunk.metadata.get("source", "unknown")
        by_source[source] += 1
    
    print(f"\n按文件分组:")
    for source, count in sorted(by_source.items()):
        print(f"  {source}: {count} 个分片")
    
    # 按 entity_name 分组
    by_entity = defaultdict(int)
    for chunk in chunks:
        entity = chunk.metadata.get("entity_name", "(无)")
        by_entity[entity] += 1
    
    if len(by_entity) > 1 or "(无)" not in by_entity:
        print(f"\n按实体名称分组:")
        for entity, count in sorted(by_entity.items(), key=lambda x: -x[1])[:10]:
            print(f"  {entity}: {count} 个分片")
    
    # 按 doc_type 分组
    by_doc_type = defaultdict(int)
    for chunk in chunks:
        doc_type = chunk.metadata.get("doc_type", "(无)")
        by_doc_type[doc_type] += 1
    
    print(f"\n按文档类型分组:")
    for doc_type, count in sorted(by_doc_type.items()):
        print(f"  {doc_type}: {count} 个分片")
    
    # 按 building_category 分组（如果有）
    by_category = defaultdict(int)
    for chunk in chunks:
        category = chunk.metadata.get("building_category")
        if category:
            by_category[category] += 1
    
    if by_category:
        print(f"\n按建筑类型分组:")
        for category, count in sorted(by_category.items()):
            print(f"  {category}: {count} 个分片")


def chunks_to_markdown(chunks, label: str) -> str:
    """将分片检查结果生成为 Markdown 报告文本（用于 --output 报告文件）"""
    lines = [
        "# 知识库分片检查报告",
        "",
        f"- 检查对象: `{label}`",
        f"- 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 总分片数: {len(chunks)}",
        "",
    ]

    if not chunks:
        lines.append("没有生成任何分片。")
        return "\n".join(lines) + "\n"

    # 分片信息表
    lines.append("## 分片信息表")
    lines.append("")
    lines.append("| No | 文件 | 实体 | 类型 | 长度 | 分类 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for i, chunk in enumerate(chunks):
        m = chunk.metadata
        file_ = (m.get("source", "-") or "-").replace("|", "\\|")[:30]
        entity = (m.get("entity_name", "-") or "-").replace("|", "\\|")[:30]
        doc_type = (m.get("doc_type", "-") or "-").replace("|", "\\|")[:20]
        category = (m.get("building_category", "-") or "-").replace("|", "\\|")[:20]
        lines.append(
            f"| {i + 1} | {file_} | {entity} | {doc_type} | {len(chunk.document)} | {category} |"
        )
    lines.append("")

    # 标题路径列表
    lines.append("## 标题路径列表")
    lines.append("")
    for i, chunk in enumerate(chunks):
        lines.append(f"{i + 1}. {chunk.metadata.get('heading', '-')}")
    lines.append("")

    # 统计分析
    lines.append("## 统计分析")
    lines.append("")
    total = len(chunks)
    lengths = [len(chunk.document) for chunk in chunks]
    lines.append(f"- 总分片数: {total}")
    lines.append(
        f"- 长度统计: 最小 {min(lengths)} / 最大 {max(lengths)} / "
        f"平均 {sum(lengths) // total} / 中位数 {sorted(lengths)[total // 2]} 字符"
    )
    lines.append("")

    by_source = defaultdict(int)
    for chunk in chunks:
        by_source[chunk.metadata.get("source", "unknown")] += 1
    lines.append("### 按文件分组")
    lines.append("")
    for source, count in sorted(by_source.items()):
        lines.append(f"- {source}: {count} 个分片")
    lines.append("")

    return "\n".join(lines) + "\n"


def inspect_file(
    file_path: Path,
    namespace: str = "test",
    chunk_size: int = 900,
    chunk_overlap: int = 150,
    show_content: bool = False,
    show_summary: bool = True,
    table_mode: bool = False,
):
    """检查单个文件的分片"""
    print(f"\n处理文件: {file_path}")
    print(f"配置: chunk_size={chunk_size}, chunk_overlap={chunk_overlap}\n")
    
    chunker = MarkdownChunker(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    
    chunks = chunker.split_file(file_path, namespace=namespace)
    
    # 表格模式
    if table_mode:
        print_chunks_table(chunks)
    else:
        # 打印每个分片
        for i, chunk in enumerate(chunks):
            print_chunk_summary(chunk, i, show_content=show_content)
    
    # 统计分析
    if show_summary:
        analyze_chunks(chunks)

    return chunks


def inspect_directory(
    dir_path: Path,
    namespace: str = "test",
    chunk_size: int = 900,
    chunk_overlap: int = 150,
    show_content: bool = False,
    show_summary: bool = True,
    file_limit: int | None = None,
    table_mode: bool = False,
):
    """检查目录下所有 Markdown 文件的分片"""
    print(f"\n扫描目录: {dir_path}")
    print(f"配置: chunk_size={chunk_size}, chunk_overlap={chunk_overlap}\n")
    
    paths = collect_markdown_paths(dir_path)
    
    if not paths:
        print("未找到 Markdown 文件")
        return
    
    print(f"找到 {len(paths)} 个 Markdown 文件")
    
    if file_limit:
        paths = paths[:file_limit]
        print(f"限制处理前 {file_limit} 个文件")
    
    chunker = MarkdownChunker(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    
    all_chunks = []
    for path in paths:
        print(f"\n处理: {path.relative_to(dir_path)}")
        chunks = chunker.split_file(path, namespace=namespace)
        print(f"  生成 {len(chunks)} 个分片")
        all_chunks.extend(chunks)
    
    # 表格模式
    if table_mode:
        print_chunks_table(all_chunks)
    elif show_content:
        # 详细模式：打印每个分片
        for i, chunk in enumerate(all_chunks):
            print_chunk_summary(chunk, i, show_content=True)
    
    # 统计分析
    if show_summary:
        analyze_chunks(all_chunks)

    return all_chunks


def main():
    parser = argparse.ArgumentParser(
        description="知识库分片检查工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:

  # 检查单个文件
  python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base/building_types/residential/residential-building-types.md

  # 检查整个知识库目录
  python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base

  # 显示完整内容
  python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base/components/windows.md --show-content

  # 只处理前 5 个文件
  python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --limit 5

  # 自定义分片大小
  python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --chunk-size 600 --chunk-overlap 100

  # 自定义控制台日志路径（默认 scripts/reports/chunks_console_<时间戳>.txt）
  python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --log-output logs/console.txt

  # 关闭控制台日志保存
  python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --no-log-output

  # 自定义报告输出路径（默认 scripts/reports/inspect_chunks_<时间戳>.md）
  python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --output reports/inspect.md
""",
    )
    
    parser.add_argument(
        "path",
        type=Path,
        help="Markdown 文件或目录路径",
    )
    
    parser.add_argument(
        "--namespace",
        type=str,
        default="test",
        help="命名空间（默认: test）",
    )
    
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=900,
        help="分片大小（默认: 900）",
    )
    
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=150,
        help="分片重叠（默认: 150）",
    )
    
    parser.add_argument(
        "--show-content",
        action="store_true",
        help="显示每个分片的完整内容",
    )
    
    parser.add_argument(
        "--table",
        action="store_true",
        help="以表格形式显示分片信息（简洁模式）",
    )
    
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="不显示统计摘要",
    )
    
    parser.add_argument(
        "--limit",
        type=int,
        help="限制处理的文件数量（仅用于目录）",
    )
    
    parser.add_argument(
        "--output",
        type=Path,
        help="报告 Markdown 输出路径（默认自动生成到 scripts/reports/ 目录，命名 inspect_chunks_<时间戳>.md）",
    )
    
    parser.add_argument(
        "--log-output",
        type=Path,
        help="控制台日志保存路径（默认自动生成到 scripts/reports/ 目录，命名 chunks_console_<时间戳>.txt）",
    )
    
    parser.add_argument(
        "--no-log-output",
        action="store_true",
        help="不保存控制台日志（默认会保存）",
    )
    
    args = parser.parse_args()
    
    # ── 控制台日志双写（Tee）：默认启用，--no-log-output 关闭，--log-output 自定义路径 ──
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = None
    if not args.no_log_output:
        if args.log_output:
            log_path = args.log_output.resolve()
        else:
            reports_dir = Path(__file__).resolve().parents[1] / "reports"
            log_path = reports_dir / f"chunks_console_{timestamp}.txt"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
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
        chunks = inspect_file(
            path,
            namespace=args.namespace,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
            show_content=args.show_content,
            show_summary=not args.no_summary,
            table_mode=args.table,
        )
    elif path.is_dir():
        chunks = inspect_directory(
            path,
            namespace=args.namespace,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
            show_content=args.show_content,
            show_summary=not args.no_summary,
            file_limit=args.limit,
            table_mode=args.table,
        )
    else:
        print(f"错误: 不支持的路径类型: {path}")
        return 1
    
    # ── 写入 Markdown 报告文件（--output 自定义路径，默认 scripts/reports/inspect_chunks_<时间戳>.md） ──
    if args.output:
        report_path = args.output.resolve()
    else:
        reports_dir = Path(__file__).resolve().parents[1] / "reports"
        report_path = reports_dir / f"inspect_chunks_{timestamp}.md"
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        md_content = chunks_to_markdown(chunks, str(path))
        report_path.write_text(md_content, encoding="utf-8")
        print(f"\n报告文件已生成: {report_path} ({len(md_content)} 字符)")
    except OSError as e:
        print(f"警告: 无法写入报告文件 {report_path}: {e}")
    
    return 0


if __name__ == "__main__":
    exit(main())
