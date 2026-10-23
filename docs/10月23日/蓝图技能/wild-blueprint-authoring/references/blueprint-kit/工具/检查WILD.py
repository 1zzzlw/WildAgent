"""只读：原始 JSON Schema、引用及明确尺寸链检查；不代替 Core 或视觉验收。"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator

PACK = Path(__file__).resolve().parents[1]


def check(path):
    raw = path.read_bytes()
    report = dict(file=str(path), sha256=hashlib.sha256(raw).hexdigest(), errors=[], warnings=[])
    errors, warnings = report['errors'], report['warnings']
    try:
        bp = json.loads(raw.decode('utf-8-sig'),
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f'非 JSON 数字 {value}')))
    except (ValueError, UnicodeError) as exc:
        errors.append(str(exc))
        return report
    def finite(value):
        if isinstance(value, dict):
            return all(finite(v) for v in value.values())
        if isinstance(value, list):
            return all(finite(v) for v in value)
        return not isinstance(value, float) or math.isfinite(value)

    if not finite(bp):
        errors.append('包含超出有限范围的数值')
        return report
    schema = json.loads((PACK / '核心资料/wild-core/schema.json').read_text(encoding='utf-8'))
    for error in sorted(Draft202012Validator(schema).iter_errors(bp), key=lambda e: str(e.path)):
        errors.append(f'Schema {list(error.path)}: {error.message}')
    if errors:
        return report
    geometry = bp['geometry']
    if any(geometry.get(name) for name in ('templates', 'instances', 'placements')):
        warnings.append('存在模板/批量放置；本工具未展开它们，请运行 Core')
    rows = geometry.get('elements', []) + geometry.get('components', [])
    if not rows and not geometry.get('instances'):
        errors.append('没有可生成几何的元素或组件')
    by_id = {}
    materials = bp.get('materials', {})
    for row in rows:
        identifier = row['id']
        if identifier in by_id:
            errors.append(f'重复 ID: {identifier}')
        by_id[identifier] = row
        for key, value in row.items():
            if (key == 'material' or key.endswith('Material')) and isinstance(value, str) and value not in materials:
                errors.append(f'{identifier}.{key}: 材质 {value} 未定义（自足输出要求）')
    for row in rows:
        identifier = row['id']
        if 'parentWall' in row:
            wall = by_id.get(row['parentWall'])
            if not wall or wall['type'] != 'wall':
                errors.append(f'{identifier}: parentWall 不是存在的 wall')
            elif not wall.get('curve'):
                length = math.hypot(wall['to'][0]-wall['from'][0], wall['to'][2]-wall['from'][2])
                along, bottom, _ = row['from']
                if along < 0 or along + row['width'] > length + 1e-6:
                    errors.append(f'{identifier}: 超出宿主墙长')
                if 'height' in row and (bottom < wall['from'][1]-1e-6 or bottom + row['height'] > wall['to'][1]+1e-6):
                    errors.append(f'{identifier}: 超出宿主墙高')
        for key, expected in (('parentFloor', 'floor'), ('parentRoof', 'roof')):
            if key in row and by_id.get(row[key], {}).get('type') != expected:
                errors.append(f'{identifier}: {key} 不是存在的 {expected}')
        if row['type'] == 'wall':
            if row['to'][1] <= row['from'][1] or math.hypot(row['to'][0]-row['from'][0], row['to'][2]-row['from'][2]) <= 0:
                errors.append(f'{identifier}: 墙高或水平长度非正')
        if row['type'] == 'stair':
            n, h, d = (row.get(k) for k in ('stepCount', 'stepHeight', 'stepDepth'))
            if any(value is None for value in (n, h, d)):
                warnings.append(f'{identifier}: 缺少显式踏步参数，需要 Core 推导')
            else:
                rise = row['to'][1]-row['from'][1]
                run = math.hypot(row['to'][0]-row['from'][0], row['to'][2]-row['from'][2])
                if n <= 0 or h <= 0 or d <= 0 or abs(n*h-rise) > 1e-5 or abs(n*d-run) > 1e-5:
                    errors.append(f'{identifier}: 楼梯端点与 N×步高/步深不一致')
        if row['type'] == 'primitive' and row.get('label') and row['shape'] != 'box':
            errors.append(f'{identifier}: label 仅支持 box')
    report['scope'] = '原始Schema、ID/材质/宿主引用、直墙开口界限、显式楼梯尺寸链；未证明空间可用或画面质量'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    reports = [check(path) for path in args.files]
    result = dict(ok=not any(row['errors'] for row in reports), reports=reports)
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding='utf-8')
    print(text, end='')
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
