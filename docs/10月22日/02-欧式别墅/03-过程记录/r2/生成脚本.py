"""玫庭庄园：本次 Codex 原创方案，复用本日原语作者工具。"""
import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
COMMON = HERE.parent/'00-公共脚本'
sys.path.insert(0, str(COMMON))
from 构件作者工具 import (E, C, M, LAYERS, material, add, box, slab, wall, sweep, sphere,
                         window, door, guard, hip_roof, chair, table, bed, tree, lantern)


def frame(i, x, z, bottom, w, h, face='front', upper=False):
    """石窗套在开口外沿，石台阶、竖边、过梁分开，避免覆盖玻璃。"""
    layer = 'facade_upper' if upper else 'facade'
    def part(suffix, along, y, width, height, depth, mat='limestone'):
        if face == 'front':
            box(i+suffix, x+along, y, z, width, height, depth, mat, layer)
        else:
            box(i+suffix, x, y, z+along, depth, height, width, mat, layer)
    part('_sill', 0, bottom-.075, w+.42, .15, .38)
    for sign in [-1, 1]:
        part('_jamb_'+str(sign), sign*(w/2+.07), bottom+h/2, .14, h+.03, .19)
    part('_lintel', 0, bottom+h+.095, w+.32, .19, .24)
    part('_hood', 0, bottom+h+.225, w+.52, .09, .35)
    part('_keystone', 0, bottom+h+.03, .23, .25, .27, 'stone_light')


def ironwork(i, x0, x1, z, y, h=.98, layer='facade_upper'):
    box(i+'_handrail', (x0+x1)/2, y+h, z, x1-x0+.08, .045, .055, 'bronze', layer)
    box(i+'_bottomrail', (x0+x1)/2, y+.12, z, x1-x0, .035, .035, 'bronze', layer)
    count = max(2, round((x1-x0)/.18))
    for j in range(count+1):
        x = x0+(x1-x0)*j/count
        box(f'{i}_bar_{j}', x, y+h/2, z, .021, h, .025, 'bronze', layer)
    for j in range(max(1, round((x1-x0)/.7))):
        cx = x0+.35+j*.7
        if cx+.23 > x1:
            break
        pts = [[cx+.21*math.cos(k*2*math.pi/24), y+.53+.28*math.sin(k*2*math.pi/24), z-.012]
               for k in range(25)]
        sweep(f'{i}_oval_{j}', pts, .013, 'bronze', layer, 6)


def cylinder(i, x, y, z, r, h, mat, layer='detail'):
    add(dict(type='primitive', id=i, shape='cylinder', radius=r, height=h,
             segments=40, position=[x, y, z], material=mat), layer)


def build():
    material('plaster', [.79, .755, .665], .89)
    material('limestone', [.86, .82, .72], .84)
    material('stone', [.43, .43, .38], .9)
    material('stone_light', [.69, .66, .57], .87)
    material('tile', [.17, .205, .235], .74)
    material('tile_alt', [.23, .265, .29], .76)
    material('tile_joint', [.085, .105, .125], .89)
    material('tile_ridge', [.27, .285, .29], .64)
    material('dark_wood', [.15, .12, .09], .65)
    material('walnut', [.34, .21, .12], .73)
    material('oak', [.6, .46, .3], .8)
    material('bronze', [.11, .125, .12], .33, .72)
    material('linen', [.89, .85, .75], .99)
    material('sage_fabric', [.36, .42, .39], .99)
    material('clay', [.54, .29, .22], .95)
    material('porcelain', [.9, .88, .8], .22)
    material('glass', [.86, .93, .95], .07, materialClass='glass', transmission=.91,
             ior=1.5, thickness=.014, side='double')
    material('water', [.19, .40, .39], .1, materialClass='glass', transmission=.55,
             ior=1.333, thickness=.04, side='double')
    material('soil', [.19, .14, .10], 1)
    material('grass', [.28, .35, .23], 1)
    material('leaf', [.18, .29, .19], 1)
    material('leaf_light', [.32, .39, .24], 1)
    material('bark', [.24, .16, .1], .98)
    material('rose', [.59, .25, .27], .95)
    material('warm_glow', [1, .82, .48], .35, emissive=[.65, .35, .1])

    slab('site', -4, -8.6, 25.5, 18.5, .08, .1, 'stone_light', 'site')
    slab('main_foundation', -.18, 3.82, 18.18, 15.18, .43, .32, 'stone', 'foundation')
    slab('ground_main', -.12, 3.88, 18.12, 15.12, .6, .17, 'oak', 'floor_ground')
    slab('wintergarden_foundation', 18.18, 6.82, 22.68, 13.18, .43, .32, 'stone', 'foundation')
    slab('ground_wintergarden', 18.12, 6.88, 22.62, 13.12, .6, .17, 'limestone', 'floor_ground')
    slab('porch_foundation', 6.0, 1.15, 12.0, 3.82, .43, .32, 'stone', 'foundation')
    slab('porch_floor', 6.0, 1.15, 12.0, 3.88, .6, .17, 'limestone', 'floor_ground')
    # 梯井 x=[7.55,10.45], z=[7.2,11.8]，与二层前、后廊连通。
    for j, rect in enumerate([(-.12, 3.88, 7.55, 15.12), (10.45, 3.88, 18.12, 15.12),
                               (7.55, 3.88, 10.45, 7.2), (7.55, 11.8, 10.45, 15.12)]):
        slab(f'upper_slab_{j}', *rect, 4.2, .25, 'oak', 'floor_upper')
    slab('porch_balcony', 6.0, 1.1, 12.0, 3.88, 4.2, .25, 'limestone', 'floor_upper')
    for j in range(5):
        slab('entry_step_'+str(j), 6.4, -1.55+j*.54, 11.6, -1.01+j*.54,
             .184+j*.104, .104, 'limestone', 'site')
    # 最后一级末端 z=1.15，直接连接门廊，避免重复铺板。
    for j, rect in enumerate([(-4, -8.6, 4.4, 2.6), (13.6, -8.6, 25.5, 2.6),
                               (-4, 2.6, -1.3, 18.5), (23.8, 2.6, 25.5, 18.5),
                               (-1.3, 16.3, 23.8, 18.5)]):
        slab(f'lawn_{j}', *rect, .12, .035, 'grass', 'site')

    for level, b, t, layer in [('g', .6, 3.95, 'wall_ground'), ('u', 4.2, 7.55, 'wall_upper')]:
        wall('front_'+level, 0, 4, 18, 4, b, t, layer=layer)
        wall('back_'+level, 0, 15, 18, 15, b, t, layer=layer)
        wall('west_'+level, 0, 4, 0, 15, b, t, layer=layer)
        wall('east_'+level, 18, 4, 18, 15, b, t, layer=layer)
        wall('interior_l_'+level, 6.4, 4, 6.4, 15, b, t, .16, layer=layer)
        wall('interior_r_'+level, 11.6, 4, 11.6, 15, b, t, .16, layer=layer)
        door('room_l_'+level, 'interior_l_'+level, 1.5, b, 1.15, 2.5)
        door('room_r_'+level, 'interior_r_'+level, 1.5, b, 1.15, 2.5)
    wall('kitchen_divider', 11.6, 10.5, 18, 10.5, .6, 3.95, .16)
    door('kitchen_entry', 'kitchen_divider', .7, .6, 1.05, 2.5)
    wall('study_divider', 0, 11, 6.4, 11, .6, 3.95, .16)
    door('study_entry', 'study_divider', 4.7, .6, 1.05, 2.5)
    wall('upper_bath_front', 6.4, 12.25, 9.25, 12.25, 4.2, 7.55, .14, layer='wall_upper')
    wall('upper_bath_side', 9.25, 12.25, 9.25, 15, 4.2, 7.55, .14, layer='wall_upper')
    door('bath_entry', 'upper_bath_front', .7, 4.2, .95, 2.4)
    door('entrance', 'front_g', 7.65, .6, 2.7, 3.0)
    C[-1].update(openingStyle='arched', leafRows=3)
    door('balcony_door', 'front_u', 7.9, 4.2, 2.2, 2.95, glass=True)
    C[-1].update(openingStyle='arched')
    # 五段立面，主入口两侧各两组高窗。
    for level, bottom, height in [('g', 1.0, 2.55), ('u', 4.65, 2.45)]:
        for j, start in enumerate([1.0, 4.0, 12.0, 15.0]):
            window(f'front_window_{level}_{j}', 'front_'+level, start, bottom, 2.0, height, 1, 2)
            frame(f'front_surround_{level}_{j}', start+1, 3.80, bottom, 2, height, upper=level == 'u')
        for j, start in enumerate([1.1, 4.2, 7.35, 10.1, 13.2, 15.8]):
            window(f'back_window_{level}_{j}', 'back_'+level, start, bottom+.15, 1.45, 2.25, 1, 1)
        for side in ['west', 'east']:
            starts = [1.0, 4.35, 8.0] if side == 'west' else [1.0, 8.0]
            for j, start in enumerate(starts):
                window(f'{side}_window_{level}_{j}', side+'_'+level, start, bottom+.2, 2.0, 2.25, 1, 1)
                frame(f'{side}_surround_{level}_{j}', -.20 if side == 'west' else 18.2,
                      4+start+1, bottom+.2, 2, 2.25, 'side', level == 'u')
    # 两侧首层百叶：百叶实体位于窗套之外。
    for j, start in enumerate([1.0, 4.0, 12.0, 15.0]):
        for sign in [-1, 1]:
            x = start+1+sign*1.28
            box(f'shutter_panel_{j}_{sign}', x, 2.25, 3.72, .35, 2.45, .06,
                'sage_fabric', 'facade')
            for k in range(13):
                box(f'shutter_louver_{j}_{sign}_{k}', x, 1.15+k*.17, 3.68,
                    .30, .025, .035, 'dark_wood', 'facade')
    # 正门石拱：从拱脚到拱顶的轮廓来自门洞半圆。
    arch = [[9+1.44*math.cos(math.pi-k*math.pi/48), 2.25+1.44*math.sin(math.pi-k*math.pi/48), 3.77]
            for k in range(49)]
    sweep('entrance_arch_stone', arch, .115, 'limestone', 'facade', 10)
    for sign in [-1, 1]:
        box('entrance_jamb_'+str(sign), 9+sign*1.44, 1.425, 3.77, .23, 1.65, .24,
            'limestone', 'facade')
    box('entrance_keystone', 9, 3.72, 3.7, .30, .4, .3, 'stone_light', 'facade')

    # 柱廊与多层石线脚，柱顶直接承托二层露台。
    for j, x in enumerate([6.35, 11.65]):
        box(f'column_plinth_{j}', x, .76, 1.48, .7, .32, .7, 'stone_light', 'structure')
        add(dict(type='column', id=f'portico_column_{j}', base=[x, .92, 1.48],
                 height=3.03, bottomRadius=.24, topRadius=.205, style='ionic', flutes=24,
                 material='limestone'), 'structure')
    box('portico_architrave', 9, 3.86, 1.48, 6.25, .18, .55, 'limestone', 'structure')
    for j, (y, h, d) in enumerate([(3.98, .09, .65), (4.12, .12, .73)]):
        box('portico_cornice_'+str(j), 9, y, 1.48, 6.4, h, d, 'limestone', 'facade_upper')
    guard('balcony_rail', [[6.1, 4.2, 3.8], [6.1, 4.2, 1.22],
                           [11.9, 4.2, 1.22], [11.9, 4.2, 3.8]], 1.03)
    ironwork('balcony_iron', 6.15, 11.85, 1.22, 4.2, 1.03)
    for j, x in enumerate([6.1, 11.9]):
        box(f'balcony_pier_{j}', x, 4.7, 1.22, .28, 1.0, .28, 'limestone', 'facade_upper')
        sphere(f'balcony_finial_{j}', x, 5.28, 1.22, .16, 'limestone', layer='facade_upper')
    for j, start in enumerate([1.0, 4.0, 12.0, 15.0]):
        ironwork('juliet_'+str(j), start-.04, start+2.04, 3.57, 4.55, .82)
    # 石材角隅、层间腰线、双层檐口及齿饰。
    for corner, x, z in [('sw', -.08, 3.92), ('se', 18.08, 3.92),
                          ('nw', -.08, 15.08), ('ne', 18.08, 15.08)]:
        for j in range(16):
            y = .8+j*.41
            box(f'quoin_{corner}_{j}', x, y, z, .68 if j % 2 else .49, .34,
                .49 if j % 2 else .68, 'limestone', 'facade' if y < 4 else 'facade_upper')
    for j, (y, h, out) in enumerate([(3.91, .17, .20), (4.09, .12, .27),
                                     (7.31, .13, .22), (7.49, .16, .38)]):
        for side, z in [('front', 4-out/2), ('back', 15+out/2)]:
            box(f'band_{j}_{side}', 9, y, z, 18.45, h, out, 'limestone', 'facade_upper')
        for side, x in [('west', -out/2), ('east', 18+out/2)]:
            box(f'band_{j}_{side}', x, y, 9.5, out, h, 11.45, 'limestone', 'facade_upper')
    for j in range(37):
        for side, z in [('front', 3.73), ('back', 15.27)]:
            box(f'dentil_{side}_{j}', .08+j*.495, 7.19, z, .18, .15, .22, 'limestone', 'facade_upper')
    # 正面石材横缝按窗间实墙留白，不穿过开口。
    for j in range(6):
        y = .88+j*.49
        for k, (a, b) in enumerate([(.35, .8), (3.25, 3.8), (6.3, 7.5), (10.5, 11.7), (14.25, 14.8), (17.25, 17.65)]):
            box(f'rustication_{j}_{k}', (a+b)/2, y, 3.865, b-a, .012, .012, 'stone_light', 'facade')

    # 侧面玻璃花房，与主楼有真实通门。
    wall('winter_front', 18, 7, 22.5, 7, .6, 3.65)
    wall('winter_east', 22.5, 7, 22.5, 13, .6, 3.65)
    wall('winter_back', 18, 13, 22.5, 13, .6, 3.65)
    door('winter_link', 'east_g', 5.25, .6, 1.6, 2.6, glass=True)
    for host, width in [('winter_front', 3.8), ('winter_back', 3.8), ('winter_east', 5.3)]:
        window(host+'_glass', host, .35, .8, width, 2.55, 3 if width < 4 else 5, 1)
    add(dict(type='roof', id='winter_roof', roofType='hip', span=5.2, depth=6.7,
             height=.65, thickness=.1, position=[20.25, 3.65, 10], material='glass'), 'roof')
    for j in range(8):
        x = 17.78+j*.70
        if x > 22.85:
            break
        local = x-20.25
        end = 3.35-min(2.6-abs(local), 2.6)
        for sign in [-1, 1]:
            sweep(f'winter_roof_bar_{j}_{sign}', [[x, 3.675, 10+sign*3.35],
                       [x, 3.675+.65*min(2.6-abs(local), 2.6)/2.6, 10+sign*end]],
                  .025, 'bronze', 'roof_detail', 6)
    # 内楼梯：20 级，每跑10级，高差 3.6 米。
    for j, a, b in [(1, [8.2, .6, 7.2], [8.2, 2.4, 10.2]),
                     (2, [9.8, 2.4, 10.2], [9.8, 4.2, 7.2])]:
        add(dict(type='stair', id='stair_flight_'+str(j), **{'from': a}, to=b, width=1.2,
                 stepCount=10, stepHeight=.18, stepDepth=.3, material='limestone'), 'stair')
    slab('stair_landing', 7.55, 10.2, 10.45, 11.75, 2.4, .2, 'limestone', 'stair')
    guard('stair_l', [[7.6, .6, 7.2], [7.6, 2.4, 10.2], [7.6, 2.4, 11.65]], .95)
    guard('stair_r', [[10.4, 2.4, 11.65], [10.4, 2.4, 10.2], [10.4, 4.2, 7.2]], .95)
    guard('stair_mid_l', [[8.8, .6, 7.2], [8.8, 2.4, 10.2]], .95)
    guard('stair_mid_r', [[9.2, 2.4, 10.2], [9.2, 4.2, 7.2]], .95)
    guard('stair_landing_back', [[7.6, 2.4, 11.65], [10.4, 2.4, 11.65]], .95)
    guard('stair_void', [[9.05, 4.2, 7.2], [7.55, 4.2, 7.2], [7.55, 4.2, 11.8],
                          [10.45, 4.2, 11.8], [10.45, 4.2, 7.2]], glass=True)

    hip_roof('main_roof', 9, 9.5, 19.25, 12.25, 7.55, 2.8)
    # 三个独立老虎窗，墙底与主坡面相交，窗玻璃位于坡面之上。
    for j, cx in enumerate([3.1, 9.0, 14.9]):
        for side, args in [('f', (cx-.78, 4.85, cx+.78, 4.85)),
                            ('b', (cx-.78, 6.45, cx+.78, 6.45)),
                            ('l', (cx-.78, 4.85, cx-.78, 6.45)),
                            ('r', (cx+.78, 4.85, cx+.78, 6.45))]:
            wall(f'dormer_{j}_{side}', *args, 8.12, 9.43, .15, 'limestone', 'roof_detail')
        window(f'dormer_window_{j}', f'dormer_{j}_f', .30, 8.38, .96, .88, 1, 1)
        add(dict(type='roof', id=f'dormer_roof_{j}', roofType='gable', span=2.05, depth=2.12,
                 height=.65, thickness=.12, position=[cx, 9.43, 5.65], material='tile'), 'roof')
        sweep(f'dormer_pediment_{j}', [[cx-1.025, 9.47, 4.56], [cx, 10.12, 4.56],
                                      [cx+1.025, 9.47, 4.56]], .055, 'limestone', 'roof_detail')
    for j, x in enumerate([2.05, 15.95]):
        box(f'chimney_{j}', x, 9.68, 11.7, .76, 2.1, .9, 'plaster', 'roof_detail')
        for k in range(6):
            box(f'chimney_course_{j}_{k}', x, 8.92+k*.3, 11.7, .82, .04, .96,
                'stone_light', 'roof_detail')
        box(f'chimney_cap_{j}', x, 10.79, 11.7, .98, .17, 1.12, 'limestone', 'roof_detail')
        for k, dx in enumerate([-.19, .19]):
            cylinder(f'chimney_pot_{j}_{k}', x+dx, 11.03, 11.7, .115, .36, 'tile_ridge', 'roof_detail')

    # 起居室与餐厨，家具不占主入口和楼梯前廊。
    slab('living_rug', .9, 6, 5.6, 9.8, .615, .015, 'linen', 'furniture')
    box('sofa_base', 3.2, .87, 9.1, 3.4, .43, 1.0, 'walnut', 'furniture')
    box('sofa_back', 3.2, 1.25, 9.52, 3.4, .8, .16, 'sage_fabric', 'furniture')
    for j in range(3):
        box(f'sofa_cushion_{j}', 2.15+j*1.05, 1.11, 9, .98, .16, .82, 'linen', 'furniture')
        box(f'sofa_pillow_{j}', 2.15+j*1.05, 1.35, 9.3, .4, .38, .16, 'clay', 'furniture')
    table('coffee', 3.3, 7.45, 1.8, .9, y=.6, height=.45, mat='limestone')
    chair('lounge_chair', 1.4, 7.2, y=.6, angle=math.pi/2)
    box('fireplace_base', 3.2, .85, 4.35, 2.4, .5, .55, 'stone_light', 'furniture')
    box('fireplace_opening', 3.2, 1.18, 4.32, 1.2, .75, .17, 'bronze', 'furniture')
    for j, x in enumerate([2.32, 4.08]):
        box(f'fireplace_jamb_{j}', x, 1.27, 4.44, .3, .95, .45, 'limestone', 'furniture')
    box('fireplace_mantel', 3.2, 1.83, 4.44, 2.5, .18, .62, 'limestone', 'furniture')
    table('dining', 14.9, 7.4, 2.7, 1.15, y=.6)
    for j, (x, z, a) in enumerate([(13.9, 6.4, math.pi), (14.9, 6.4, math.pi), (15.9, 6.4, math.pi),
                                  (13.9, 8.4, 0), (14.9, 8.4, 0), (15.9, 8.4, 0)]):
        chair('dining_chair_'+str(j), x, z, y=.6, angle=a)
    for j in range(5):
        box(f'kitchen_cabinet_{j}', 12.5+j*1.05, 1.05, 14.45, 1.02, .9, .64, 'walnut', 'furniture')
        box(f'kitchen_handle_{j}', 12.5+j*1.05, 1.18, 14.11, .32, .018, .025, 'bronze', 'furniture')
    box('kitchen_counter', 14.6, 1.54, 14.45, 5.3, .08, .74, 'limestone', 'furniture')
    box('kitchen_sink', 13.5, 1.60, 14.45, .8, .04, .45, 'bronze', 'furniture')
    box('kitchen_stove', 16.2, 1.6, 14.45, .8, .035, .45, 'bronze', 'furniture')
    box('kitchen_island', 15.1, 1.05, 12.3, 2.1, .9, .85, 'walnut', 'furniture')
    box('kitchen_island_top', 15.1, 1.54, 12.3, 2.2, .08, .95, 'limestone', 'furniture')
    table('library_desk', 3.3, 12.3, 2.3, .85, y=.6)
    chair('library_chair', 3.3, 13.15, y=.6)
    for j in range(5):
        box(f'library_shelf_{j}', 2.5, .75+j*.5, 14.5, 3.7, .055, .4, 'walnut', 'furniture')
        for k in range(10):
            box(f'library_book_{j}_{k}', .93+k*.34, .95+j*.5, 14.49, .13, .34, .25,
                ['linen', 'clay', 'sage_fabric'][k % 3], 'furniture')
    for j, x in enumerate([3.0, 14.85]):
        bed('bedroom_'+str(j), x, 11.75, y=4.2)
        box('wardrobe_'+str(j), x, 5.3, 14.5, 3.8, 2.2, .65, 'walnut', 'furniture')
        for k in range(4):
            box(f'wardrobe_handle_{j}_{k}', x-1.35+k*.9, 5.4, 14.16, .02, .3, .026,
                'bronze', 'furniture')
    table('bedroom_desk', 4.7, 6.1, 1.8, .7, y=4.2)
    chair('bedroom_chair', 4.7, 6.95, y=4.2)
    box('bath_vanity', 7.85, 4.65, 14.5, 1.9, .9, .6, 'walnut', 'furniture')
    box('bath_basin', 7.85, 5.15, 14.5, .75, .1, .45, 'porcelain', 'furniture')
    box('bath_mirror', 7.85, 6.0, 14.87, 1.35, 1.25, .03, 'bronze', 'furniture')
    # 花房桌椅、盆景与露台休憩。
    table('winter_table', 20.1, 9.5, 1.15, .8, y=.6)
    chair('winter_chair_0', 20.1, 8.5, y=.6, angle=math.pi)
    chair('winter_chair_1', 20.1, 10.5, y=.6)
    table('balcony_table', 10.3, 2.6, .7, .6, y=4.2, height=.57)
    chair('balcony_chair', 9.0, 2.6, y=4.2, angle=-math.pi/2)
    for j, (x, z) in enumerate([(21.8, 7.7), (21.8, 12.2)]):
        cylinder(f'flowerpot_{j}', x, .85, z, .29, .5, 'clay', 'furniture')
        sphere(f'flowerpot_leaf_{j}', x, 1.35, z, .48, 'leaf', [.8, 1.2, .8], 'furniture')

    # 前庭的圆形喷泉，以实体盆体和独立水面组成。
    cylinder('fountain_base', 9, .16, -5.2, 1.85, .16, 'stone_light', 'landscape')
    cylinder('fountain_basin', 9, .36, -5.2, 1.62, .25, 'stone', 'landscape')
    cylinder('fountain_water', 9, .51, -5.2, 1.46, .025, 'water', 'landscape')
    cylinder('fountain_pedestal', 9, .94, -5.2, .23, .86, 'limestone', 'landscape')
    cylinder('fountain_dish', 9, 1.42, -5.2, .65, .13, 'limestone', 'landscape')
    sphere('fountain_finial', 9, 1.64, -5.2, .18, 'limestone')
    circle = [[9+1.58*math.cos(k*2*math.pi/80), .55, -5.2+1.58*math.sin(k*2*math.pi/80)]
              for k in range(81)]
    sweep('fountain_coping', circle, .075, 'limestone', 'landscape', 8)
    for j in range(6):
        a = j*math.pi/3
        pts = [[9+(.1+.95*t)*math.cos(a), 1.5+.48*math.sin(t*math.pi)-.94*t,
                -5.2+(.1+.95*t)*math.sin(a)] for t in [k/20 for k in range(21)]]
        sweep(f'fountain_water_arc_{j}', pts, .018, 'water', 'landscape', 6)
    for j, x in enumerate([2.6, 15.4]):
        slab('flowerbed_'+str(j), x-1.7, -5.6, x+1.7, -.8, .16, .04, 'soil', 'landscape')
        for k in range(14):
            px, pz = x+(-1 if k % 2 else 1)*1.38, -5.3+(k//2)*.68
            sphere(f'flowerbed_hedge_{j}_{k}', px, .46, pz, .36, 'leaf', [1, .9, 1])
        for k in range(8):
            px, pz = x-.65+(k % 2)*1.3, -4.9+(k//2)*1.0
            sphere(f'rose_bush_{j}_{k}', px, .43, pz, .35, 'leaf_light', [1, .75, 1])
            for n in range(3):
                sphere(f'rose_flower_{j}_{k}_{n}', px+(n-1)*.15, .68, pz+.08*(n % 2), .085, 'rose')
    for j, (x, z, scale) in enumerate([(-2.5, 6.0, 1.15), (-2.5, 13.7, 1.1),
                                      (24.0, 5.0, 1.1), (23.9, 15.6, 1.2)]):
        tree('garden_tree_'+str(j), x, z, .12, scale)
    for j, (x, z) in enumerate([(5.65, -1.8), (12.35, -1.8), (5.65, -6.6), (12.35, -6.6)]):
        box(f'garden_light_post_{j}', x, .84, z, .09, 1.4, .09, 'bronze', 'lighting')
        lantern('garden_light_'+str(j), x, z, 1.62)
    for j, x in enumerate([7.15, 10.85]):
        lantern('entry_sconce_'+str(j), x, 3.52, 2.7)
    for j, (x, z, y) in enumerate([(9, 2.55, 3.0), (3.3, 7.4, 3.05), (14.9, 7.4, 3.0)]):
        lantern('pendant_'+str(j), x, z, y, True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--revision', default='r1')
    args = p.parse_args()
    build()
    bp = dict(meta=dict(version='1.1', type='building', name='玫庭庄园 · 欧式别墅',
                        author='Codex', style='french-classical-villa', seed=20261022),
              geometry=dict(elements=E, components=C), materials=M, assets={}, behaviors={}, editor=dict(revision=0))
    data = (json.dumps(bp, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n').encode('utf-8')
    path = HERE/'玫庭庄园-欧式别墅.wild'
    path.write_bytes(data)
    archive = HERE/'03-过程记录'/args.revision
    archive.mkdir(parents=True, exist_ok=True)
    (archive/f'玫庭庄园-{args.revision}.wild').write_bytes(data)
    (archive/'生成脚本.py').write_bytes(Path(__file__).read_bytes())
    (archive/'构件作者工具.py').write_bytes((COMMON/'构件作者工具.py').read_bytes())
    (HERE/'03-过程记录'/'构件分层.json').write_text(json.dumps(LAYERS, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = dict(revision=args.revision, file=path.name, sha256=hashlib.sha256(data).hexdigest(),
                   bytes=len(data), elements=len(E), components=len(C), materials=len(M),
                   layers=dict(Counter(LAYERS.values())), element_types=dict(Counter(e['type'] for e in E)),
                   author='当前对话 Codex', method='确定性脚本；本日公共原语作者工具', model_calls=0,
                   application_source_modified=False)
    (archive/'生成摘要.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
