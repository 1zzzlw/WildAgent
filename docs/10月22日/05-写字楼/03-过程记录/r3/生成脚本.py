"""本次六层办公方案；确定性展开完整 WILD，不使用别墅几何或 Agent。"""
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
for name, rgb, rough, metal in [
    ('stone', [.76, .76, .68], .83, 0), ('concrete', [.59, .61, .59], .88, 0),
    ('plaster', [.86, .86, .81], .89, 0), ('dark', [.13, .18, .20], .55, .3),
    ('bronze', [.52, .36, .17], .45, .52), ('wood', [.38, .23, .12], .67, 0),
    ('flooring', [.64, .65, .61], .85, 0), ('carpet', [.29, .36, .37], .97, 0),
    ('fabric', [.30, .42, .40], .92, 0), ('linen', [.71, .68, .57], .96, 0),
    ('black', [.04, .06, .07], .61, .1), ('screen', [.08, .17, .21], .28, .08),
    ('roof_membrane', [.26, .30, .30], .96, 0), ('soil', [.22, .25, .17], .99, 0),
    ('leaf', [.16, .29, .14], .93, 0), ('leaf_light', [.30, .42, .20], .95, 0),
    ('bark', [.25, .17, .11], .96, 0), ('paving', [.64, .65, .61], .95, 0),
    ('solar', [.055, .12, .18], .28, .35), ('walnut', [.30, .18, .09], .7, 0)]:
    a.material(name, rgb, rough, metal)
a.material('glass', [.65, .81, .84], .10, materialClass='glass', transmission=.87,
           ior=1.5, thickness=.018, side='double')
a.material('warm_glow', [.96, .88, .69], .8, emissive=[1, .82, .57], emissiveIntensity=.4)

def box(i, x, y, z, w, h, d, mat, rotation=None):
    return a.box(i, x, y, z, w, h, d, mat, 'architecture', rotation)

def window(i, host, start, f, w, h=2.90, bottom=.45, vm=3, hm=0):
    return a.add(dict(type='window', id=i, parentWall=host, **{'from': [start, f+bottom, 0]},
        width=w, height=h, frameWidth=.055, frameDepth=.25, glassDepth=.014,
        verticalMullions=vm, horizontalMullions=hm, mullionWidth=.035,
        frameMaterial='dark', glassMaterial='glass'), 'components')

def door(i, host, s, f, w=1.05, h=2.50, glass=False, slide=False):
    return a.add(dict(type='door', id=i, parentWall=host, **{'from': [s, f, 0]}, width=w,
        height=h, frameWidth=.06, frameDepth=.22, leafDepth=.035,
        doorStyle='double' if w>1.5 else 'single', frameMaterial='dark',
        leafMaterial='glass' if glass else 'wood', interaction=dict(mode='slide' if slide else 'swing',
        hingeSide='left', openDistance=.9, openAngle=90, initiallyOpen=False)), 'components')

def guard(i, path, height=1.1, glass=False):
    data = dict(type='railing', id=i, path=path, height=height, postSpacing=1.1,
        postRadius=.022, railRadius=.025, railLevels=[.12, 1], material='bronze')
    if glass:
        data.update(infillType='glass', infillMaterial='glass', infillThickness=.016, infillTopRatio=.94)
    return a.add(data, 'components')

def furnished(i, kind, x, f, z, w, d, h, mat, angle=0):
    return a.add(dict(type='furniture', id=i, subtype=kind, position=[x, f, z],
        dimensions=dict(width=w, depth=d, height=h), rotation=[0, angle, 0], material=mat), 'furniture')

def planter(i, x, f, z, w, d, tall=False):
    box(i+'_base', x, f+.23, z, w, .46, d, 'concrete')
    box(i+'_soil', x, f+.467, z, w-.10, .015, d-.10, 'soil')
    if tall:
        a.add(dict(type='primitive', id=i+'_trunk', shape='cylinder', position=[x, f+1.30, z],
                   height=1.68, radiusBottom=.07, radiusTop=.045, segments=12, material='bark'), 'landscape')
        for k, (dx, dz, y, r) in enumerate([(-.28, 0, 1.9, .65), (.28, .1, 2.2, .65), (0, 0, 2.7, .53)]):
            a.sphere(i+f'_crown_{k}', x+dx, f+y, z+dz, r, 'leaf_light' if k%2 else 'leaf', [1, .65, 1])
    else:
        for k in range(max(1, math.floor(w/.55))):
            a.sphere(i+f'_shrub_{k}', x-w/2+.32+k*.55, f+.66, z, .34, 'leaf', [1, .72, 1])

def desk(i, x, f, z):
    furnished(i+'_desk', 'table', x, f, z, 2.40, 1.1, .75, 'wood')
    for sign in [-1, 1]:
        furnished(i+f'_chair_{sign}', 'chair', x+sign*.64, f, z-.92, .52, .52, .94, 'dark', 0)
        box(i+f'_screen_{sign}', x+sign*.64, f+1.03, z+.22, .55, .34, .035, 'screen')
        box(i+f'_stand_{sign}', x+sign*.64, f+.82, z+.22, .04, .14, .06, 'black')
        box(i+f'_keyboard_{sign}', x+sign*.64, f+.77, z-.12, .40, .025, .14, 'black')

# 场地在 ±16m 内，入口无障碍坡道与台阶占用不同位置。
a.slab('site', -16.5, -13.5, 16.5, 12.5, .05, .12, 'soil', 'site')
a.slab('plaza', -14.2, -12.7, 14.2, 10.5, .12, .07, 'paving', 'site')
a.slab('l0_floor', -12.2, -8.7, 12.2, 8.7, .30, .18, 'flooring', 'floor')
for k in range(2):
    a.slab(f'entry_step_{k}', -2.6, -9.66+k*.48, 2.6, -9.66+(k+1)*.48,
           .21+.09*k, .09*(k+1), 'stone', 'entry')
a.add(dict(type='ramp', id='entry_ramp', **{'from': [6.7, .12, -11.85]}, to=[6.7, .30, -8.7],
    width=1.5, thickness=.08, railingSides='right', railingHeight=.9, postSpacing=1.1,
    material='stone', railingMaterial='bronze'), 'components')
box('canopy_plate', 0, 3.56, -9.5, 7.4, .18, 3.2, 'dark')
box('canopy_edge', 0, 3.57, -11.11, 7.5, .22, .075, 'bronze')
for k in range(11):
    box(f'canopy_slat_{k}', -3.45+k*.69, 3.43, -9.5, .065, .075, 3.1, 'wood')

holes = [(-11.1, -7.9, 1.5, 7.1), (-7.02, -4.58, 2.1, 4.5)]
def floor_with_holes(prefix, f):
    # 按孔的 X 边界分条，条内扣掉 Z 区间，不生成互相重叠的网格单元。
    xs = sorted({-12.2, 12.2, *[v for r in holes for v in r[:2]]})
    n = 0
    for xa, xb in zip(xs, xs[1:]):
        blocked = sorted((za, zb) for x0, x1, za, zb in holes if x0<(xa+xb)/2<x1)
        intervals, current = [], -8.7
        for za, zb in blocked:
            intervals.append((current, za)); current = zb
        intervals.append((current, 8.7))
        for za, zb in intervals:
            if zb-za>.001:
                a.slab(f'{prefix}_slab_{n}', xa, za, xb, zb, f, .24, 'flooring', 'floor')
                n += 1

for level in range(6):
    f = round(.30+level*3.9, 3)
    prefix = f'l{level}'
    xmax, zmin = (9, -5.5) if level==5 else (12, -8.5)
    if level:
        floor_with_holes(prefix, f)
    top = round(f+3.66, 3)
    south = a.wall(prefix+'_wall_s', -12, zmin, xmax, zmin, f, top, .24, 'plaster')
    east = a.wall(prefix+'_wall_e', xmax, zmin, xmax, 8.5, f, top, .24, 'plaster')
    north = a.wall(prefix+'_wall_n', xmax, 8.5, -12, 8.5, f, top, .24, 'plaster')
    west = a.wall(prefix+'_wall_w', -12, 8.5, -12, zmin, f, top, .24, 'plaster')
    if level==0:
        door(prefix+'_entry', south, 10.7, f, 2.6, 3.0, True)
        for j, (cx, w) in enumerate([(-8.5, 5.4), (-3.7, 2.2), (3.7, 2.2), (8.5, 5.4)]):
            window(f'{prefix}_south_{j}', south, cx+12-w/2, f, w, 3.10, .28, 2)
    elif level==5:
        door(prefix+'_terrace_door', south, 14.8, f, 2.0, 2.8, True)
        for j, (cx, w) in enumerate([(-8.8, 4.9), (-2.8, 4.9), (7.25, 2.2)]):
            window(f'{prefix}_south_{j}', south, cx+12-w/2, f, w, vm=3 if w>3 else 1)
    else:
        for j, cx in enumerate([-9, -3, 3, 9]):
            window(f'{prefix}_south_{j}', south, cx+12-2.60, f, 5.20)
    for j, cz in enumerate([-4.5, 1, 6]):
        if cz-2.0 >= zmin+.2:
            window(f'{prefix}_east_{j}', east, cz-zmin-2, f, 4.0, vm=2)
    for j, cx in enumerate([-9.7, -1.6, 3.8, 8.6]):
        w = 1.25 if j==0 else 3.9
        if cx+w/2 < xmax-.2:
            window(f'{prefix}_north_{j}', north, xmax-cx-w/2, f, w, 2.55, .65, 1 if j==0 else 2)
    for j, cz in enumerate([-5.5, -.1, 4.8]):
        w = 1.2 if j==2 else 3.5
        if cz-w/2 > zmin+.2:
            window(f'{prefix}_west_{j}', west, 8.5-cz-w/2, f, w, 2.55, .65, 1)
    # 每层石色楼层边带与细金属滴水线；六层外墙按退台定位。
    box(prefix+'_band_s', (xmax-12)/2, f-.07, zmin-.15, xmax+12+.48, .26, .34, 'stone')
    box(prefix+'_band_e', xmax+.15, f-.07, (zmin+8.5)/2, .34, .26, 8.5-zmin+.48, 'stone')
    box(prefix+'_band_n', (xmax-12)/2, f-.07, 8.65, xmax+12+.48, .26, .34, 'stone')
    box(prefix+'_band_w', -12.15, f-.07, (zmin+8.5)/2, .34, .26, 8.5-zmin+.48, 'stone')
    box(prefix+'_drip_s', (xmax-12)/2, f+.10, zmin-.34, xmax+12+.55, .035, .035, 'bronze')

    # 楼梯围合、会议室与电梯井。每段墙都接入外墙或另一段墙。
    stairfront = a.wall(prefix+'_stair_front', -12, 1.3, -7.7, 1.3, f, top, .16, 'plaster')
    a.wall(prefix+'_stair_side', -7.7, 1.3, -7.7, 8.5, f, top, .16, 'plaster')
    door(prefix+'_stair_door', stairfront, 1.20, f, 1.25)
    for side, coords in [('s', (-7.1, 2, -4.5, 2)), ('e', (-4.5, 2, -4.5, 4.6)),
                         ('n', (-4.5, 4.6, -7.1, 4.6)), ('w', (-7.1, 4.6, -7.1, 2))]:
        # 采用项目识别井道的稳定语义前缀，几何仍由本次四壁坐标决定。
        host = a.wall('wall_core_'+prefix+'_'+side, *coords, f, top, .16, 'concrete')
        if side=='n':
            door(prefix+'_lift_door', host, .70, f, 1.2, 2.50, False, True)
    meetingfront = a.wall(prefix+'_meeting_front', 0, 1.3, xmax, 1.3, f, top, .16, 'plaster')
    a.wall(prefix+'_meeting_side', 0, 1.3, 0, 8.5, f, top, .16, 'plaster')
    door(prefix+'_meeting_door', meetingfront, .75, f, 1.1, 2.5, True)
    window(prefix+'_meeting_glass', meetingfront, 2.3, f, xmax-2.7, 2.25, .8, 3)
    if level<5:
        mid = f+1.95
        a.add(dict(type='stair', id=prefix+'_stair_up_a', **{'from': [-10.25, f, 1.5]},
            to=[-10.25, mid, 5.4], width=1.4, stepCount=13, stepHeight=.15, stepDepth=.30,
            material='concrete'), 'stair')
        a.slab(prefix+'_landing', -10.95, 5.4, -7.95, 7.1, mid, .18, 'concrete', 'stair')
        a.add(dict(type='stair', id=prefix+'_stair_up_b', **{'from': [-8.65, mid, 5.4]},
            to=[-8.65, f+3.9, 1.5], width=1.4, stepCount=13, stepHeight=.15, stepDepth=.30,
            material='concrete'), 'stair')
        guard(prefix+'_stair_guard_a', [[-9.55, f+.15, 1.65], [-9.55, mid, 5.4]])
        guard(prefix+'_stair_guard_b', [[-9.35, mid+.15, 5.25], [-9.35, f+3.9, 1.5]])
        guard(prefix+'_landing_guard', [[-10.95, mid, 7.1], [-7.95, mid, 7.1]])
    if level:
        # 梯口只封非到达边，保留南面两跑出入口。
        guard(prefix+'_stair_void_guard', [[-11.12, f, 1.5], [-11.12, f, 7.13],
                                          [-7.80, f, 7.13], [-7.80, f, 1.5]])

    # 接待、工位、会议与茶水空间。
    if level==0:
        box(prefix+'_reception', 0, f+.55, -1.4, 4.4, 1.10, .85, 'stone')
        box(prefix+'_reception_inlay', 0, f+.55, -1.84, 3.6, .66, .035, 'wood')
        box(prefix+'_reception_top', 0, f+1.13, -1.4, 4.55, .06, .95, 'dark')
        for j, x in enumerate([-7, 7]):
            box(f'{prefix}_rug_{j}', x, f+.012, -4.1, 4.3, .025, 3.2, 'carpet')
            furnished(f'{prefix}_sofa_{j}', 'sofa', x, f+.03, -4.9, 2.65, .90, .86, 'fabric')
            furnished(f'{prefix}_coffee_{j}', 'table', x, f+.03, -3.7, 1.5, .70, .43, 'wood')
        planter(prefix+'_lobby_tree', 9.7, f, -.3, 1.1, 1.1, True)
    elif level<5:
        for ix, x in enumerate([-6.0, 0, 6.0]):
            for iz, z in enumerate([-5.5, -1.6]):
                desk(f'{prefix}_work_{ix}_{iz}', x, f, z)
        box(prefix+'_office_rug', 0, f+.005, -3.3, 18, .01, 7.5, 'carpet')
    else:
        for k, x in enumerate([-6.8, -.8]):
            desk(f'{prefix}_executive_{k}', x, f, -2.5)
        furnished(prefix+'_executive_sofa', 'sofa', 5.8, f, -1.9, 2.4, .85, .87, 'linen')
        furnished(prefix+'_executive_coffee', 'table', 5.8, f, -.5, 1.35, .65, .45, 'wood')
    cx = min(6, (xmax+1)/2)
    furnished(prefix+'_meeting_table', 'table', cx, f, 5.0, 4.0, 1.35, .76, 'wood')
    for k, x in enumerate([cx-1.35, cx, cx+1.35]):
        for sign in [-1, 1]:
            furnished(f'{prefix}_meeting_chair_{k}_{sign}', 'chair', x, f, 5+sign*1.10,
                      .53, .53, .96, 'fabric', 0 if sign<0 else math.pi)
    box(prefix+'_presentation', xmax-.20, f+1.65, 5.0, .055, 1.45, 2.55, 'screen')
    box(prefix+'_pantry', -2.1, f+.45, 8.0, 3.25, .9, .65, 'wood')
    box(prefix+'_pantry_top', -2.1, f+.93, 8.0, 3.36, .07, .72, 'stone')
    box(prefix+'_pantry_sink', -1.5, f+.973, 7.97, .50, .025, .42, 'dark')
    box(prefix+'_coffee_machine', -2.8, f+1.13, 7.98, .35, .36, .32, 'black')
    for j in range(4):
        box(f'{prefix}_pantry_seam_{j}', -3.6+j*.8, f+.45, 7.669, .015, .83, .008, 'dark')
    # 每层两条吸顶发光面，仅六个组合实际光源，控制渲染成本。
    for j, x in enumerate([-5.0, 5.0]):
        box(f'{prefix}_ceiling_light_{j}', x, top-.04, -3.5, 3.6, .055, .12, 'warm_glow')
    a.add(dict(type='light', id=prefix+'_lobby_light', position=[-2, top-.20, 5.8],
        bulbRadius=.055, material='warm_glow', lowIntensity=3, highIntensity=12, distance=6,
        initiallyOn=True, color=[1, .88, .67]), 'components')

a.add(dict(type='elevator', id='lift_six_stops', position=[-5.8, .30, 3.3],
    dimensions=dict(width=2.2, depth=2.1, height=2.65), floorHeight=3.9, floorCount=6,
    initialFloor=0, material='dark', frameMaterial='bronze'), 'components')

# 连续竖向遮阳片与石边框，顶层独立退台。
for side in [-1, 1]:
    for k in range(13):
        x = -11.7+k*1.95
        box(f'facade_fin_{side}_{k}', x, 11.90, side*8.79, .085, 15.55, .46, 'bronze')
    box(f'corner_frame_{side}', side*12.18, 10.08, -8.68, .38, 19.56, .42, 'stone')
    for k in range(7):
        z = -7.9+k*2.65
        box(f'east_fin_{side}_{k}', side*12.22, 11.9, z, .48, 15.55, .085, 'bronze')

# 六层转角露台：南面、东面连续防护，墙边留通往露台的门。
guard('l5_terrace_guard', [[-12.15, 19.8, -5.5], [-12.15, 19.8, -8.65], [12.15, 19.8, -8.65],
                          [12.15, 19.8, 8.65], [9.13, 19.8, 8.65]], 1.12, True)
for k in range(34):
    box(f'l5_deck_board_{k}', -11.8+k*.71, 19.817, -6.99, .694, .034, 2.78, 'wood')
for k in range(20):
    box(f'l5_deck_e_{k}', 10.55, 19.817, -5.2+k*.69, 2.68, .034, .674, 'wood')
for k, (x, z) in enumerate([(-10.5, -7), (10.6, 6.7), (10.6, -5.8)]):
    planter(f'l5_terrace_planter_{k}', x, 19.84, z, 1.0, 1.0, True)
for k, (x, z) in enumerate([(7.0, -7.7), (7.0, -5.95), (10.9, -7.7), (10.9, -5.95)]):
    box(f'l5_pergola_post_{k}', x, 21.18, z, .10, 2.68, .10, 'bronze')
for k in range(10):
    box(f'l5_pergola_slat_{k}', 7+k*.44, 22.56, -6.82, .065, .16, 2.15, 'wood')
box('l5_pergola_tie_front', 8.98, 22.44, -7.7, 4.2, .15, .10, 'bronze')
box('l5_pergola_tie_back', 8.98, 22.44, -5.95, 4.2, .15, .10, 'bronze')
furnished('l5_terrace_table', 'table', 3.6, 19.84, -6.95, 1.6, .7, .74, 'wood')
for k, x in enumerate([2.3, 4.9]):
    furnished(f'l5_terrace_chair_{k}', 'chair', x, 19.84, -7.0, .55, .55, .9, 'linen', math.pi/2 if k else -math.pi/2)

# 设备屋面：实体平顶、女儿墙、设备屏风与光伏板，均显式标高。
a.add(dict(type='roof', id='roof_main', roofType='flat', position=[-1.5, 23.46, 1.5],
    span=21.45, depth=14.45, height=.24, thickness=.24, material='roof_membrane'), 'roof')
for k, (x, z, w, d) in enumerate([(-1.5, -5.64, 21.4, .20), (-1.5, 8.64, 21.4, .20),
                                  (-12.14, 1.5, .20, 14.4), (9.14, 1.5, .20, 14.4)]):
    box(f'roof_parapet_{k}', x, 24.08, z, w, .76, d, 'stone')
    box(f'roof_coping_{k}', x, 24.49, z, w+.08, .08, d+.08, 'dark')
box('roof_equipment_unit', -8.8, 24.28, 5.4, 3.5, 1.16, 3.3, 'concrete')
for s in [-1, 1]:
    for k in range(8):
        box(f'roof_screen_{s}_{k}', -8.8, 23.84+k*.19, 5.4+s*1.93, 4.4, .085, .07, 'bronze')
for k in range(8):
    box(f'roof_screen_end_{k}', -11.0, 23.84+k*.19, 5.4, .07, .085, 3.9, 'bronze')
for k in range(8):
    x, z = -3.8+(k%4)*2.7, .5+(k//4)*2.6
    box(f'roof_solar_panel_{k}', x, 24.10, z, 2.35, .07, 1.65, 'solar', [-.20, 0, 0])
    for sign in [-1, 1]:
        box(f'roof_solar_leg_{k}_{sign}', x+sign*.85, 23.89, z, .07, .38, .12, 'dark')
    for j in range(5):
        box(f'roof_solar_grid_{k}_{j}', x-1+j*.5, 24.10+.045*math.cos(.2), z-.045*math.sin(.2),
            .015, .012, 1.55, 'bronze', [-.20, 0, 0])
for k, x in enumerate([-10.8, 7.9]):
    box(f'roof_drain_{k}', x, 23.714, -4.5, .25, .025, .25, 'dark')

# 前庭带座椅花池、铺地接缝与导向灯。
for k, (x, z) in enumerate([(-13.7, -7), (13.7, 4), (-9, -11.4), (10.4, -11.4)]):
    planter(f'garden_planter_{k}', x, .12, z, 1.5, 1.3, True)
for k, x in enumerate([-8, 9.5]):
    box(f'garden_bench_{k}', x, .57, -10.3, 3.0, .10, .55, 'wood')
    for j, dx in enumerate([-.95, .95]):
        box(f'garden_bench_leg_{k}_{j}', x+dx, .32, -10.3, .15, .40, .45, 'dark')
for k in range(11):
    box(f'plaza_joint_{k}', -13+k*2.6, .123, -11.2, .018, .008, 2.7, 'concrete')
for k, x in enumerate([-4, 4]):
    box(f'entry_bollard_{k}', x, .64, -11.5, .14, 1.04, .14, 'dark')
    box(f'entry_bollard_lens_{k}', x, 1.06, -11.58, .11, .15, .025, 'warm_glow')

bp = dict(meta=dict(version='1.1', type='building', name='云序中心 · 六层退台写字楼',
    author='Codex', style='现代办公建筑'), geometry=dict(elements=a.E, components=a.C),
    materials=a.M, editor=dict(revision=1))
data = (json.dumps(bp, ensure_ascii=False, separators=(',', ':'))+'\n').encode('utf-8')
(BASE/'云序中心-写字楼.wild').write_bytes(data)
(BASE/'03-过程记录/构件分层.json').write_text(json.dumps(a.LAYERS, ensure_ascii=False, indent=2), encoding='utf-8')
snapshot = BASE/'03-过程记录'/rev
snapshot.mkdir(parents=True, exist_ok=True)
(snapshot/'云序中心.wild').write_bytes(data)
shutil.copyfile(__file__, snapshot/'生成脚本.py')
summary = dict(revision=rev, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data),
    elements=len(a.E), components=len(a.C), materials=len(a.M), floor_heights=[round(.3+i*3.9, 3) for i in range(6)])
(snapshot/'生成摘要.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
