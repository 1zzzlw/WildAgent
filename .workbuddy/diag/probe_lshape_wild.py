"""体检一份 .wild 蓝图：屋顶覆盖是否与体量数匹配。

用于判定"缺屋顶"到底是生成侧（蓝图里就没有 roof）还是渲染侧（有 roof 没画出来）。
"""
import json
import sys
from collections import Counter, defaultdict

PATH = sys.argv[1] if len(sys.argv) > 1 else \
    r"D:\Backup\Downloads\AI 生成 - L形双翼别墅，主翼面南展开12米，副翼从东北角向北延伸形成半围合庭院，双坡屋顶覆盖各翼，立面通过门位偏置与开窗对位建立主次关系.wild"

with open(PATH, encoding='utf-8') as fh:
    bp = json.load(fh)

print('=' * 74)
print('顶层字段:', list(bp.keys()))
meta = bp.get('meta', {})
print('meta:', json.dumps(meta, ensure_ascii=False)[:300])

geo = bp.get('geometry', {})
print('geometry 字段:', list(geo.keys()))

elements = geo.get('elements', [])
components = geo.get('components', [])
print(f'元素总数: {len(elements)}   组合构件数: {len(components)}')

print()
print('--- 按 type 计数 ---')
for t, n in Counter(e.get('type') for e in elements).most_common():
    print(f'  {t:14s} {n}')

print()
print('--- 组合构件 ---')
for c in components:
    print(f"  {c.get('type'):12s} id={c.get('id')} 键={[k for k in c if k not in ('type','id')]}")

print()
print('=' * 74)
print('屋顶元素详情')
print('=' * 74)
roofs = [e for e in elements if e.get('type') == 'roof']
if not roofs:
    print('  ❌ 蓝图里没有任何 roof 元素')
for r in roofs:
    print(json.dumps(r, ensure_ascii=False, indent=2))
    print('-' * 40)

print()
print('=' * 74)
print('体量分析：把墙按水平位置聚类')
print('=' * 74)
walls = [e for e in elements if e.get('type') == 'wall']


def seg_bounds(w):
    """返回墙的水平线段包围盒 (minx,maxx,minz,maxz) 与其竖向范围"""
    pts = []
    for key in ('from', 'to'):
        v = w.get(key)
        if isinstance(v, list) and len(v) >= 3:
            pts.append((v[0], v[2]))
    if not pts:
        return None
    xs = [p[0] for p in pts]
    zs = [p[1] for p in pts]
    ys = []
    for key in ('from', 'to'):
        v = w.get(key)
        if isinstance(v, list) and len(v) >= 3:
            ys.append(v[1])
    h = w.get('height')
    if h is not None:
        ys = [min(ys), min(ys) + h]
    return (min(xs), max(xs), min(zs), max(zs), min(ys), max(ys), w.get('id'))


info = [seg_bounds(w) for w in walls]
info = [i for i in info if i]
if info:
    gx0 = min(i[0] for i in info); gx1 = max(i[1] for i in info)
    gz0 = min(i[2] for i in info); gz1 = max(i[3] for i in info)
    print(f'全部墙的水平总范围: X[{gx0:.2f}, {gx1:.2f}]  Z[{gz0:.2f}, {gz1:.2f}]')
    print(f'全场最高墙顶 Y = {max(i[5] for i in info):.2f}')

    # 简单网格聚类：按 X/Z 中位数把墙分到不同象限
    print()
    print('--- 每面墙（水平包围盒 + 墙顶）---')
    for i in sorted(info, key=lambda x: (x[2], x[0])):
        print(f'  {i[6]:32s} X[{i[0]:7.2f},{i[1]:7.2f}] Z[{i[2]:7.2f},{i[3]:7.2f}] 顶Y={i[5]:6.2f}')

# ── 屋顶覆盖检查：每个 roof 的水平范围 vs 墙的范围 ──
print()
print('=' * 74)
print('屋顶覆盖 vs 建筑水平范围')
print('=' * 74)
if info:
    for r in roofs:
        pos = r.get('position')
        span = r.get('span'); depth = r.get('depth')
        if not pos:
            print(f"  {r.get('id')}: 无 position（需由引擎按承托墙反推）")
            continue
        cx, cy, cz = pos[0], pos[1], pos[2]
        if span and depth:
            rx0, rx1 = cx - span / 2, cx + span / 2
            rz0, rz1 = cz - depth / 2, cz + depth / 2
            cov_x = (min(rx1, gx1) - max(rx0, gx0)) / (gx1 - gx0) * 100
            cov_z = (min(rz1, gz1) - max(rz0, gz0)) / (gz1 - gz0) * 100
            print(f"  {r.get('id'):20s} type={r.get('roofType')} position Y={cy:.2f} "
                  f"X[{rx0:.2f},{rx1:.2f}] Z[{rz0:.2f},{rz1:.2f}]")
            print(f"      覆盖建筑总水平范围: X {cov_x:.0f}%   Z {cov_z:.0f}%")
