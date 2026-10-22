"""维护时在原项目内执行；复制核心源码并生成可核查的来源清单。"""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

PACK = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, required=True)
    args = parser.parse_args()
    root = args.project_root.resolve()
    if not (root / 'wild-core/src/index.ts').is_file():
        parser.error('project-root 不是 WildAgent 项目根目录')
    entries = []

    def copy(source):
        relative = source.relative_to(root)
        target = PACK / '核心资料' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        entries.append(dict(source=relative.as_posix(), packed=target.relative_to(PACK).as_posix(),
                            bytes=source.stat().st_size, sha256=sha(source)))

    for source in sorted((root / 'wild-core/src').rglob('*.ts')):
        copy(source)
    for name in ('types.ts', 'schema.json', 'package.json', 'tsconfig.json'):
        copy(root / 'wild-core' / name)
    # 保留相对导入的完整闭包；包含类型依赖，不复制整个前端应用。
    pending = [root / 'wild-web/src/renderer/renderEntity.ts',
               root / 'wild-web/src/renderer/materialAdapter.ts']
    seen = set()
    while pending:
        source = pending.pop().resolve()
        if source in seen:
            continue
        seen.add(source)
        copy(source)
        imports = re.findall(r'(?:from\s*|import\s*)[\'\"](\.[^\'\"]+)[\'\"]',
                             source.read_text(encoding='utf-8'))
        for name in imports:
            base = source.parent / name
            candidates = [base, Path(str(base) + '.ts'), base / 'index.ts']
            target = next((p for p in candidates if p.is_file()), None)
            if target is None:
                raise RuntimeError(f'未解析的相对导入: {source}: {name}')
            pending.append(target)
    for name in ('validate-generated.mjs', 'render-baseline.mjs'):
        copy(root / 'wild-web/scripts' / name)
    for name in ('contracts.py', 'compilation.py'):
        copy(root / 'wild-server/app/design' / name)

    samples = []
    day = root / 'docs/10月22日'
    paths = [root / 'docs/10月20日优化/汀院别墅-Codex.wild']
    for directory in sorted(day.iterdir()):
        if directory.is_dir() and re.match(r'\d\d-', directory.name):
            paths.extend(sorted(directory.glob('*.wild')))
    for path in paths:
        bp = json.loads(path.read_text(encoding='utf-8-sig'))
        directory = path.parent
        related = [directory / 'README.md']
        for part in ('01-需求与设计', '03-过程记录'):
            related.extend(sorted((directory / part).glob('*.md')))
        related.extend(sorted((directory / '01-需求与设计').glob('DesignDocument.json')))
        related.extend(sorted((directory / '04-校验').glob('*.json')))
        related.extend(sorted((directory / '05-效果图').rglob('*manifest*.json')))
        number = '00-汀院质量参考' if directory != day and path == paths[0] else directory.name
        case_dir = PACK / '案例' / number
        case_dir.mkdir(parents=True, exist_ok=True)
        packed_wild = case_dir / path.name
        shutil.copyfile(path, packed_wild)
        preview_candidates = [directory / '05-效果图/参考视角/reference-day.png',
                              directory / '05-效果图/世界环境/day.png',
                              directory / '05-效果图/perspective.png']
        if path == paths[0]:
            preview_candidates.insert(0, day / '00-质量参考/本次命名建筑对照/汀院/perspective.png')
        preview = next((p for p in preview_candidates if p.is_file()), None)
        preview_info = None
        if preview:
            target = case_dir / '已有实图.png'
            shutil.copyfile(preview, target)
            manifest = next(iter(sorted(preview.parent.glob('*manifest*.json'))), None)
            if manifest:
                shutil.copyfile(manifest, case_dir / '已有渲染清单.json')
                related.append(manifest)
            preview_info = dict(source=preview.relative_to(root).as_posix(),
                                packed=target.relative_to(PACK).as_posix(), sha256=sha(preview))
        evidence = []
        for source in sorted(set(related)):
            if not source.is_file():
                continue
            local = source.relative_to(directory) if source.is_relative_to(directory) else Path('质量参照清单') / source.name
            target = case_dir / '原始记录' / local
            if target.suffix == '.md':
                target = target.with_suffix('.md.txt')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            evidence.append(dict(source=source.relative_to(root).as_posix(),
                                 packed=target.relative_to(PACK).as_posix(), sha256=sha(source)))
        samples.append(dict(name=bp['meta']['name'], source=path.relative_to(root).as_posix(),
                            packed=packed_wild.relative_to(PACK).as_posix(), preview=preview_info,
                            sha256=sha(path), bytes=path.stat().st_size,
                            elements=len(bp['geometry'].get('elements', [])),
                            components=len(bp['geometry'].get('components', [])),
                            materials=len(bp.get('materials', {})),
                            evidence=evidence))
    out = PACK / '验证与来源'
    out.mkdir(exist_ok=True)
    (out / '核心源码来源.json').write_text(json.dumps(dict(
        snapshot_date='2026-10-22', policy='只读原样快照；不包含依赖缓存、密钥或完整后端',
        files=sorted(entries, key=lambda row: row['source'])), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (out / '十二例来源索引.json').write_text(json.dumps(dict(
        scope='11栋当日作品与1栋质量参照；不含剖切副本与前端优化目录',
        count=len(samples), samples=samples), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(snapshot_files=len(entries), samples=len(samples)), ensure_ascii=False))


if __name__ == '__main__':
    main()
