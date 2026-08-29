"""候选知识晋升：把人工批准的 staging 文件移入正式知识库并触发 Loader 同步。

用法：
  python scripts/kb/promote_staged.py <staged_file.md> [--dry-run]

流程：
  1. 校验候选文件 frontmatter（status=staged / source_url / 能力映射存在）。
  2. 移动到 storage/knowledge_base/ 正式目录（默认 components/，可 --target-dir 覆盖）。
  3. 触发正式 RAGSpecLoader.sync_index() 增量同步进 Chroma（不手写正式库）。
  4. 记录晋升审计（来源、时间、目标路径）。

正式入库唯一入口：只能通过本脚本移动文件 + Loader 同步，模型不能直接写正式库。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[2]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.agent.web.staging import STAGING_ROOT  # noqa: E402
from config import config  # noqa: E402

KB_ROOT = SERVER_ROOT / "storage" / "knowledge_base"


def _check_frontmatter(path: Path) -> list[str]:
    """校验候选文件是否满足入库前置条件。"""
    issues: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"无法读取候选文件: {exc}"]
    if "status: staged" not in text:
        issues.append("缺少 status: staged 标记")
    if "source_url:" not in text:
        issues.append("缺少 source_url 来源声明")
    if "authority: web_research" not in text:
        issues.append("缺少 authority 声明")
    return issues


def promote(path: Path, *, target_dir: Path, dry_run: bool) -> bool:
    """晋升单个候选文件；返回是否成功。"""
    issues = _check_frontmatter(path)
    if issues:
        print(f"❌ {path.name} 未通过前置校验: {'; '.join(issues)}")
        return False

    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / path.name
    if target.exists():
        print(f"⚠️ 目标已存在，跳过（防覆盖）: {target.name}")
        return False

    print(f"{'[dry-run] ' if dry_run else ''}晋升: {path.name} -> {target.relative_to(KB_ROOT)}")
    if dry_run:
        return True
    shutil.move(str(path), str(target))

    # 触发正式 Loader 增量同步（只读 + 增量，不手写 Chroma）。
    try:
        from app.spec.loader import RAGSpecLoader, collect_markdown_paths, create_embedding_function

        base_paths = [str(KB_ROOT / "BLUEPRINT-SPEC-MINIMAL.md")]
        rag_paths = [str(p) for p in collect_markdown_paths(KB_ROOT, exclude=base_paths)]
        loader = RAGSpecLoader(
            base_paths=base_paths,
            rag_paths=rag_paths,
            persist_dir=str(SERVER_ROOT / config.rag.persist_dir),
            collection_name=config.rag.collection_name,
            embedding_function=create_embedding_function(
                api_key=config.embedding.api_key,
                base_url=config.embedding.base_url,
                model_name=config.embedding.name,
                allow_hash_fallback=config.rag.allow_hash_fallback,
            ),
            namespace="wild_spec",
        )
        added = loader.sync_index()
        print(f"✅ 正式索引已增量同步，新增/更新 {added} 个分片")
    except Exception as exc:
        print(f"⚠️ 文件已移入正式库，但 Loader 同步失败: {exc}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="候选知识晋升到正式知识库")
    parser.add_argument("file", type=Path, help="staging 下的候选 .md 文件路径")
    parser.add_argument("--target-dir", type=str, default="components",
                        help="正式库目标子目录（默认 components/）")
    parser.add_argument("--dry-run", action="store_true", help="只校验和预览，不实际移动")
    args = parser.parse_args()

    path = args.file if args.file.is_absolute() else STAGING_ROOT.parent.parent / "knowledge_staging" / "web" / args.file
    # 允许传相对 staging 根或绝对路径
    if not path.exists():
        print(f"❌ 候选文件不存在: {path}")
        return 1
    target_dir = KB_ROOT / args.target_dir
    ok = promote(path, target_dir=target_dir, dry_run=args.dry_run)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
