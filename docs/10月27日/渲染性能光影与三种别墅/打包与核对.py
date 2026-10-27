"""核对指定两套资料的链接、来源、镜像与压缩包；不改业务代码。"""
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PACK = ROOT / 'docs/蓝图文档'
SKILL = ROOT / 'docs/蓝图技能/wild-blueprint-authoring'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files(directory):
    return sorted(p for p in directory.rglob('*') if p.is_file()
                  and not {'node_modules', '__pycache__', '.git'}.intersection(p.parts)
                  and not p.name.endswith(('.zip', '.zip.sha256', '.pyc')))


def main():
    errors, links, mirrored = [], 0, 0
    for directory in [PACK, SKILL]:
        for path in files(directory):
            if path.suffix == '.md':
                text = path.read_text(encoding='utf-8-sig')
                for target in re.findall(r'\]\(([^\n]+?)\)', text):
                    target = unquote(target.strip('<>').split('#', 1)[0])
                    if not target or re.match(r'[a-zA-Z]+:', target):
                        continue
                    links += 1
                    if not (path.parent / target).exists():
                        errors.append(f'链接不存在: {path.relative_to(ROOT)} -> {target}')
            if path.suffix in ['.json', '.wild']:
                try:
                    json.loads(path.read_text(encoding='utf-8-sig'))
                except ValueError as exc:
                    errors.append(f'非法JSON: {path}: {exc}')
    sources = json.loads((PACK / '验证与来源/核心源码来源.json').read_text(encoding='utf-8'))
    for row in sources['files']:
        if sha(ROOT / row['source']) != row['sha256'] or sha(PACK / row['packed']) != row['sha256']:
            errors.append('快照不匹配: ' + row['source'])
    for p in files(PACK):
        target = SKILL / 'references/blueprint-kit' / p.relative_to(PACK)
        if not target.is_file() or sha(target) != sha(p):
            errors.append('文档/技能镜像不匹配: ' + p.relative_to(PACK).as_posix())
        mirrored += 1
    file_list = json.loads((PACK / '验证与来源/文件清单.json').read_text(encoding='utf-8'))
    for row in file_list['files']:
        if row['path'] == '验证与来源/文件清单.json' or sha(PACK / row['path']) != row['sha256']:
            errors.append('文件清单不匹配: ' + row['path'])
    if errors:
        (HERE / '验证/资料包最终核对.json').write_text(json.dumps(dict(status='FAIL', errors=errors), ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(dict(status='FAIL', errors=errors), ensure_ascii=False))
        return 1
    archives = []
    for directory, name in [(PACK, PACK / '蓝图创作包-v3.0.zip'), (SKILL, SKILL.parent / 'wild-blueprint-authoring.zip')]:
        entries = files(directory)
        with zipfile.ZipFile(name, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in entries:
                info = zipfile.ZipInfo(directory.name + '/' + path.relative_to(directory).as_posix(), date_time=(2026, 10, 27, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, path.read_bytes())
        with zipfile.ZipFile(name) as archive:
            if archive.testzip() is not None:
                raise ValueError('ZIP CRC失败: ' + str(name))
            for path in entries:
                member = directory.name + '/' + path.relative_to(directory).as_posix()
                if hashlib.sha256(archive.read(member)).hexdigest() != sha(path):
                    raise ValueError('ZIP条目不匹配: ' + member)
        fingerprint = sha(name)
        Path(str(name) + '.sha256').write_text(fingerprint + '  ' + name.name + '\n', encoding='utf-8')
        archives.append(dict(file=name.relative_to(ROOT).as_posix(), files=len(entries), bytes=name.stat().st_size, sha256=fingerprint, crc='PASS', contentHashes='PASS'))
    shutil.copyfile(PACK / '蓝图创作包-v3.0.zip.sha256', SKILL / 'references/blueprint-kit/蓝图创作包-v3.0.zip.sha256')
    result = dict(status='PASS', links=links, sourceSnapshots=len(sources['files']), mirroredFiles=mirrored, fileListEntries=len(file_list['files']), archives=archives, errors=[],
                  scope='指定文档/项目技能和分发包；全局已安装技能副本不在本次更新范围')
    for name in [HERE / '验证/资料包最终核对.json', SKILL.parent / '2026-10-27更新核对.json']:
        name.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
