"""核对资料包自身的链接、JSON、来源指纹及检查工具的有限反例。"""
import argparse
import copy
import hashlib
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

from 检查WILD import check

PACK = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=PACK / '验证与来源/资料包自检.json')
    args = parser.parse_args()
    errors = []
    counts = dict(markdown_files=0, json_blocks=0, local_links=0, source_snapshots=0, cases=0)
    full_example = json.loads((PACK / '示例/听风茶室.wild').read_text(encoding='utf-8'))
    for path in sorted(PACK.rglob('*.md')):
        if 'node_modules' in path.parts:
            continue
        counts['markdown_files'] += 1
        text = path.read_text(encoding='utf-8')
        for block in re.findall(r'```json\s*\n(.*?)\n```', text, re.S):
            counts['json_blocks'] += 1
            try:
                value = json.loads(block)
                if isinstance(value, dict) and value.get('meta') and value != full_example:
                    errors.append(f'{path.name}: 完整例子与独立WILD不一致')
            except ValueError as exc:
                errors.append(f'{path.name}: 非法JSON代码块 {exc}')
        for target in re.findall(r'\]\(([^\n]+?)\)', text):
            target = unquote(target.strip('<>').split('#', 1)[0])
            if not target or re.match(r'[a-zA-Z]+:', target):
                continue
            counts['local_links'] += 1
            if not (path.parent / target).exists():
                errors.append(f'{path.relative_to(PACK)}: 链接不存在 {target}')
    sources = json.loads((PACK / '验证与来源/核心源码来源.json').read_text(encoding='utf-8'))
    for row in sources['files']:
        path = PACK / row['packed']
        counts['source_snapshots'] += 1
        if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            errors.append(f'源码快照hash不一致: {row["packed"]}')
    cases = json.loads((PACK / '验证与来源/十二例来源索引.json').read_text(encoding='utf-8'))
    case_checks = []
    for row in cases['samples']:
        path = PACK / row['packed']
        counts['cases'] += 1
        if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            errors.append(f'案例WILD不一致: {row["name"]}')
        preview = row['preview']
        if not preview or hashlib.sha256((PACK / preview['packed']).read_bytes()).hexdigest() != preview['sha256']:
            errors.append(f'案例实图不一致: {row["name"]}')
        manifest = json.loads((path.parent / '已有渲染清单.json').read_text(encoding='utf-8'))
        if manifest.get('inputSha256') != row['sha256']:
            errors.append(f'已有实图输入绑定不一致: {row["name"]}')
        for evidence in row['evidence']:
            if hashlib.sha256((PACK / evidence['packed']).read_bytes()).hexdigest() != evidence['sha256']:
                errors.append(f'原始记录不一致: {evidence["packed"]}')
        result = check(path)
        case_checks.append(dict(name=row['name'], sha256=row['sha256'], errors=result['errors'], warnings=result['warnings']))
        errors.extend(f'{row["name"]}: {item}' for item in result['errors'])
    example_result = check(PACK / '示例/听风茶室.wild')
    errors.extend(example_result['errors'])

    # 只测试工具明确声称可以检查的关系，避免用测试结果推断所有空间正确。
    mutations = {}
    bad = copy.deepcopy(full_example)
    bad['geometry']['elements'][1]['id'] = bad['geometry']['elements'][0]['id']
    mutations['duplicate_id'] = bad
    bad = copy.deepcopy(full_example)
    bad['geometry']['components'][0]['parentWall'] = 'missing_wall'
    mutations['missing_host'] = bad
    bad = copy.deepcopy(full_example)
    bad['geometry']['elements'][1]['material'] = 'missing_material'
    mutations['missing_material'] = bad
    bad = copy.deepcopy(full_example)
    next(row for row in bad['geometry']['elements'] if row['type'] == 'stair')['stepHeight'] = .3
    mutations['stair_chain'] = bad
    bad = copy.deepcopy(full_example)
    bad['geometry']['components'][0]['from'][0] = 100
    mutations['opening_outside_host'] = bad
    mutations['invalid_schema'] = dict(meta=full_example['meta'], geometry=dict(elements=[dict(type='magic_mesh', id='x')]))
    regressions = []
    with tempfile.TemporaryDirectory(prefix='wild-docs-check-') as temporary:
        for name, bp in mutations.items():
            path = Path(temporary) / (name + '.wild')
            path.write_text(json.dumps(bp), encoding='utf-8')
            result = check(path)
            regressions.append(dict(case=name, rejected=bool(result['errors']), errors=result['errors']))
            if not result['errors']:
                errors.append(f'反例未拒绝: {name}')
        for name, text in (('invalid_json', '{'), ('non_finite_number', '{"x":1e999}')):
            path = Path(temporary) / (name + '.wild')
            path.write_text(text, encoding='utf-8')
            result = check(path)
            regressions.append(dict(case=name, rejected=bool(result['errors']), errors=result['errors']))
            if not result['errors']:
                errors.append(f'反例未拒绝: {name}')
    result = dict(ok=not errors, checked_at=datetime.now(timezone.utc).isoformat(),
                  counts=counts, errors=errors, teaching_example=example_result,
                  case_static_checks=case_checks, checker_regressions=regressions,
                  boundary='案例为已有图/hash核对，未重新执行十二例后端/渲染；新教学例Core与真渲染另有独立运行记录')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(ok=result['ok'], counts=counts, errors=errors, report=str(args.report)), ensure_ascii=False))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
