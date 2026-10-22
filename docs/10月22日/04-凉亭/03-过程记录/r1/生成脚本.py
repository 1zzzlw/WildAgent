"""按本次设计展开自足 WILD；原语作者工具只提供写 JSON 的函数。"""
import hashlib
import importlib.util
import json
import math
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DAY = BASE.parent
spec = importlib.util.spec_from_file_location('author', DAY/'00-公共脚本/构件作者工具.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
rev = sys.argv[1] if len(sys.argv) > 1 else 'r1'
for folder in ['03-过程记录', '04-校验', '05-效果图', '06-剖切查看']:
    (BASE/folder).mkdir(parents=True, exist_ok=True)

for name, color, rough in [
    ('stone', [.49, .52, .49], .9), ('stone_light', [.68, .69, .62], .87),
    ('stone_dark', [.27, .31, .30], .9), ('paving', [.57, .57, .50], .94),
    ('wood', [.24, .10, .043], .68), ('wood_edge', [.36, .17, .064], .65),
    ('dark_wood', [.14, .066, .035], .72), ('tile', [.16, .20, .21], .83),
    ('tile_alt', [.20, .25, .25], .83), ('tile_joint', [.095, .12, .13], .92),
    ('tile_ridge', [.24, .28, .27], .8), ('bronze', [.38, .25, .085], .55),
    ('linen', [.72, .63, .42], .9), ('earth', [.25, .29, .20], .97),
    ('leaf', [.16, .27, .105], .96), ('leaf_light', [.28, .36, .13], .93),
    ('bamboo', [.26, .32, .09], .85), ('gravel', [.65, .64, .55], .95)]:
    a.material(name, color, rough)
a.material('water', [.16, .31, .29], .12, materialClass='glass', transmission=.84,
           opacity=1, ior=1.333, thickness=.16)
a.material('warm_glow', [1, .76, .36], .75, emissive=[1, .46, .12], emissiveIntensity=.6)

def beam(i, p, q, w=.15, h=.18, mat='wood', layer='timber'):
    return a.add(dict(id=i, type='beam', **{'from': p}, to=q,
                      crossSection='rect', width=w, height=h, material=mat), layer)

def cylinder(i, x, y, z, r, h, mat, layer='detail', rt=None):
    return a.add(dict(id=i, type='primitive', shape='cylinder', position=[x, y, z],
                      radiusBottom=r, radiusTop=r if rt is None else rt,
                      height=h, radialSegments=20, material=mat), layer)

def fret(i, p, q):
    # 几何回纹背靠，在两根立柱之间留出实际坐凳。
    dx, dz = q[0]-p[0], q[2]-p[2]
    length = math.hypot(dx, dz)
    n = math.ceil(length/.85)
    ux, uz = dx/length, dz/length
    for name, y in [('lower', 1.04), ('upper', 1.59)]:
        beam(i+'_'+name, [p[0], y, p[2]], [q[0], y, q[2]], .055, .065, 'wood_edge', 'seating')
    for k in range(n):
        t = (k+.5)/n
        x, z = p[0]+dx*t, p[2]+dz*t
        s = min(.25, length/n*.35)
        pts = [[x-ux*s, 1.06, z-uz*s], [x-ux*s, 1.39, z-uz*s],
               [x+ux*s, 1.39, z+uz*s], [x+ux*s, 1.57, z+uz*s]]
        for j in range(3):
            beam(f'{i}_fret_{k}_{j}', pts[j], pts[j+1], .035, .035, 'wood_edge', 'seating')

# 场地与石台，地板顶部统一为 +0.65。
a.slab('site', -7.5, -6.7, 7.5, 6, .07, .12, 'earth', 'site')
a.slab('plinth_lower', -4.5, -3.7, 4.5, 3.7, .25, .18, 'stone_dark', 'platform')
a.slab('plinth_body', -4.35, -3.55, 4.35, 3.55, .55, .30, 'stone', 'platform')
a.slab('plinth_cap', -4.4, -3.6, 4.4, 3.6, .65, .10, 'stone_light', 'platform')
# 表面小缝用离散石块表达，避免整板与饰面共面。
for ix in range(11):
    for iz in range(9):
        x, z = -4.0+ix*.8, -3.2+iz*.8
        a.box(f'paver_{ix}_{iz}', x, .658, z, .786, .016, .786,
              'paving' if (ix+iz)%5 else 'stone_light', 'platform')
for k in range(4):
    top = .07+(k+1)*(.58/4)
    a.slab(f'entry_step_{k}', -1.55, -5.12+k*.38, 1.55, -3.59,
           top, top-.07, 'stone_light', 'entry')
    a.box(f'entry_nosing_{k}', 0, top+.007, -5.12+k*.38+.045, 3.12, .025, .09, 'stone_dark', 'entry')
a.slab('entry_walk', -1.15, -6.65, 1.15, -5.1, .085, .04, 'paving', 'site')

posts = [(x, z) for x in [-3.4, 3.4] for z in [-2.5, 0, 2.5]]
for k, (x, z) in enumerate(posts):
    cylinder(f'base_pad_{k}', x, .70, z, .32, .10, 'stone_dark', 'timber')
    cylinder(f'base_drum_{k}', x, .83, z, .24, .16, 'stone_light', 'timber', .21)
    a.add(dict(id=f'wood_post_{k}', type='column', base=[x, .91, z], height=2.65,
               radiusBottom=.17, radiusTop=.15, style='chinese_wooden', material='wood'), 'timber')
    # 柱头两向叠涩，逐层改变挑出长度。
    for j, (y, reach, hh) in enumerate([(3.47, .52, .12), (3.62, .76, .12), (3.77, .98, .12)]):
        a.box(f'bracket_x_{k}_{j}', x, y, z, reach, hh, .17, 'wood_edge', 'timber')
        a.box(f'bracket_z_{k}_{j}', x, y+.055, z, .17, hh, reach, 'wood_edge', 'timber')
        for s in [-1, 1]:
            a.box(f'bracket_block_{k}_{j}_{s}', x+s*reach*.34, y+.085, z,
                  .12, .08, .22, 'wood', 'timber')
    for s in [-1, 1]:
        beam(f'brace_x_{k}_{s}', [x, 3.00, z], [x+s*.65, 3.47, z], .09, .11)
        beam(f'brace_z_{k}_{s}', [x, 3.00, z], [x, 3.47, z+s*.65], .09, .11)

for s in [-1, 1]:
    beam(f'lintel_x_{s}', [-3.58, 3.43, s*2.5], [3.58, 3.43, s*2.5], .24, .28)
    beam(f'lintel_z_{s}', [s*3.4, 3.43, -2.68], [s*3.4, 3.43, 2.68], .24, .28)
    beam(f'eave_beam_x_{s}', [-3.95, 3.78, s*2.9], [3.95, 3.78, s*2.9], .19, .22)
    beam(f'eave_beam_z_{s}', [s*3.9, 3.78, -2.98], [s*3.9, 3.78, 2.98], .19, .22)
beam('middle_tie', [-3.4, 3.43, 0], [3.4, 3.43, 0], .22, .26)

# 四坡实体与瓦作。实际坡面函数与共用作者工具相同。
a.hip_roof('main_roof', 0, 0, 9.6, 7.6, 4.05, 1.9)
def roof_y(x, z):
    return 4.05+1.9*min(4.8-abs(x), 3.8-abs(z), 3.8)/3.8
# 檐下椽木：端点贴实际坡面下侧，沿各坡到斜脊止住。
for k in range(23):
    x = -4.6+k*.4
    end = 3.8-min(4.8-abs(x), 3.8)
    for s in [-1, 1]:
        beam(f'rafter_s_{k}_{s}', [x, roof_y(x, s*3.74)-.22, s*3.74],
             [x, roof_y(x, s*end)-.22, s*end], .065, .09, 'wood_edge', 'roof_detail')
for k in range(17):
    z = -3.4+k*.4
    end = 4.8-(3.8-abs(z))
    for s in [-1, 1]:
        beam(f'rafter_e_{k}_{s}', [s*4.74, roof_y(s*4.74, z)-.22, z],
             [s*end, roof_y(s*end, z)-.22, z], .065, .09, 'wood_edge', 'roof_detail')
for sx in [-1, 1]:
    for sz in [-1, 1]:
        a.sweep(f'corner_fin_{sx}_{sz}', [[sx*4.1, 4.50, sz*3.1], [sx*4.55, 4.29, sz*3.55],
                 [sx*4.83, 4.32, sz*3.83], [sx*4.98, 4.60, sz*3.98]], .065,
                 'tile_ridge', 'roof_detail', 10)
for s in [-1, 1]:
    a.sweep(f'ridge_tail_{s}', [[s*.7, 6.02, 0], [s*1.03, 6.10, 0], [s*1.19, 6.48, 0]],
            .095, 'tile_ridge', 'roof_detail', 10)
    a.sphere(f'ridge_bead_{s}', s*1.19, 6.49, 0, .13, 'tile_ridge', layer='roof_detail')

# 三面坐凳，不封正面入口。
for s in [-1, 1]:
    a.box(f'bench_side_{s}', s*3.12, 1.10, 0, .47, .12, 4.55, 'wood_edge', 'seating')
    for k, z in enumerate([-1.95, -.65, .65, 1.95]):
        a.box(f'bench_leg_{s}_{k}', s*3.12, .85, z, .23, .40, .18, 'wood', 'seating')
    fret(f'lattice_side_{s}', [s*3.4, 0, -2.45], [s*3.4, 0, 2.45])
a.box('bench_back', 0, 1.10, 2.25, 6.3, .12, .48, 'wood_edge', 'seating')
for k, x in enumerate([-2.7, -1.35, 0, 1.35, 2.7]):
    a.box(f'bench_back_leg_{k}', x, .85, 2.25, .18, .4, .23, 'wood', 'seating')
fret('lattice_back', [-3.4, 0, 2.5], [3.4, 0, 2.5])
cylinder('tea_table_base', 0, .87, .25, .28, .42, 'stone_dark', 'seating', .23)
cylinder('tea_table_top', 0, 1.15, .25, .8, .14, 'stone_light', 'seating')
for k, angle in enumerate([0, math.pi/2, math.pi, 3*math.pi/2]):
    x, z = math.cos(angle)*1.23, .25+math.sin(angle)*1.23
    cylinder(f'stool_{k}_foot', x, .84, z, .23, .36, 'wood', 'seating', .18)
    cylinder(f'stool_{k}_seat', x, 1.05, z, .28, .09, 'wood_edge', 'seating')
cylinder('tea_tray', 0, 1.24, .25, .29, .035, 'bronze', 'seating')
cylinder('teapot', .03, 1.31, .25, .075, .13, 'stone_dark', 'seating', .055)
for k, x in enumerate([-.16, .18]):
    cylinder(f'teacup_{k}', x, 1.28, .15, .04, .05, 'stone_light', 'seating')

# 两盏带实际光源的悬灯，灯体局部坐标与光源同组。
for k, x in enumerate([-2.3, 2.3]):
    beam(f'lantern_hanger_{k}', [x, 3.32, -2.5], [x, 2.95, -2.5], .025, .025, 'bronze', 'lighting')
    a.add(dict(id=f'lantern_{k}', type='light', position=[x, 2.77, -2.5], lightType='point',
               color=[1, .76, .40], lowIntensity=2, highIntensity=7, distance=3.5, initiallyOn=True,
               body=[dict(shape='box', dimensions=[.23, .34, .23], position=[0, 0, 0], material='warm_glow', interactive=True),
                     dict(shape='box', dimensions=[.29, .055, .29], position=[0, .19, 0], material='bronze'),
                     dict(shape='box', dimensions=[.29, .055, .29], position=[0, -.19, 0], material='bronze')]), 'components')

# 池岸：不与入口踏步重叠。
a.slab('pond_base', -6.7, -5.9, -2.0, -3.75, .10, .10, 'stone_dark', 'landscape')
a.box('pond_water', -4.35, .16, -4.825, 4.54, .10, 1.99, 'water', 'landscape')
for k, (x, z, w, d) in enumerate([(-4.35, -5.94, 4.9, .20), (-6.78, -4.82, .2, 2.45),
                                  (-4.35, -3.7, 4.9, .20), (-1.92, -4.82, .2, 2.45)]):
    a.box(f'pond_coping_{k}', x, .23, z, w, .23, d, 'stone_light', 'landscape')
for k in range(4):
    a.box(f'pond_stepping_{k}', -5.95+k*.95, .245, -4.83, .62, .13, .71, 'stone', 'landscape')
for group, (cx, cz) in enumerate([(5.7, 2.2), (-5.6, 3.9), (2.5, 4.8)]):
    a.box(f'planter_{group}', cx, .26, cz, 1.45, .36, .95, 'stone_dark', 'landscape')
    for k in range(6):
        x, z = cx+((k*7)%5-2)*.19, cz+((k*3)%5-2)*.13
        height = 1.8+(k%3)*.38
        beam(f'bamboo_{group}_{k}', [x, .42, z], [x+.10, .42+height, z], .032, .032, 'bamboo', 'landscape')
        for j in range(3):
            a.sphere(f'bamboo_leaf_{group}_{k}_{j}', x+(-1 if j%2 else 1)*.18, height*.62+.55+j*.24,
                     z+.09*j, .27, 'leaf' if k%2 else 'leaf_light', [1.6, .16, .6], 'landscape')
for k, (x, z) in enumerate([(-5.7, -.2), (5.9, -1.4), (4.8, 4.6), (-3, 4.8)]):
    a.sphere(f'rock_{k}', x, .33, z, .52, 'stone', [1, .55, .75], 'landscape')
    for j in range(3):
        a.sphere(f'shrub_{k}_{j}', x+.4+j*.27, .38, z+.42, .38, 'leaf', [1, .65, 1], 'landscape')

bp = dict(meta=dict(version='1.1', type='building', name='听雨水榭 · 临水木构凉亭',
                    author='Codex', style='中式园林木构'),
          geometry=dict(elements=a.E, components=a.C), materials=a.M, editor=dict(revision=1))
data = (json.dumps(bp, ensure_ascii=False, separators=(',', ':'))+'\n').encode('utf-8')
target = BASE/'听雨水榭-凉亭.wild'
target.write_bytes(data)
(BASE/'03-过程记录/构件分层.json').write_text(json.dumps(a.LAYERS, ensure_ascii=False, indent=2), encoding='utf-8')
snapshot = BASE/'03-过程记录'/rev
snapshot.mkdir(parents=True, exist_ok=True)
(snapshot/'听雨水榭.wild').write_bytes(data)
shutil.copyfile(__file__, snapshot/'生成脚本.py')
summary = dict(revision=rev, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data),
               elements=len(a.E), components=len(a.C), materials=len(a.M))
(snapshot/'生成摘要.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
