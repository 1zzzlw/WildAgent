"""本栋建筑的确定性作者脚本。只写本栋目录，不改项目源码。"""
import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
E, C, LAYERS = [], [], {}
M = {}


def material(name, color, roughness=.8, metallic=0, **extra):
    M[name] = dict(baseColor=color, roughness=roughness, metallic=metallic,
                   albedo=1, lightingCondition='D65_noon', **extra)


def add(row, layer):
    assert row['id'] not in LAYERS, row['id']
    LAYERS[row['id']] = layer
    (C if layer == 'components' else E).append(row)
    return row['id']


def box(i, x, y, z, w, h, d, mat, layer='detail', rotation=None):
    row = dict(type='primitive', id=i, shape='box', position=[x, y, z],
               dimensions=[w, h, d], material=mat)
    if rotation:
        row['rotation'] = rotation
    return add(row, layer)


def slab(i, x0, z0, x1, z1, top, t=.18, mat='limestone', layer='floor'):
    return add(dict(type='floor', id=i, **{'from': [x0, top-t, z0]},
                    to=[x1, top-t, z1], thickness=t, material=mat), layer)


def wall(i, x0, z0, x1, z1, bottom, top, t=.24, mat='plaster', layer='wall_ground'):
    return add(dict(type='wall', id=i, **{'from': [x0, bottom, z0]},
                    to=[x1, top, z1], thickness=t, material=mat), layer)


def sweep(i, points, r, mat, layer='detail', segments=8):
    return add(dict(type='primitive', id=i, shape='profile_sweep', path=points,
                    radius=r, segments=segments, material=mat), layer)


def sphere(i, x, y, z, r, mat, scale=None, layer='landscape'):
    row = dict(type='primitive', id=i, shape='sphere', position=[x, y, z],
               radius=r, material=mat)
    if scale:
        row['scale'] = scale
    return add(row, layer)


def window(i, host, start, bottom, w, h, vm=1, hm=0):
    return add(dict(type='window', id=i, parentWall=host, **{'from': [start, bottom, 0]},
                    width=w, height=h, frameWidth=.055, frameDepth=.25,
                    glassDepth=.014, verticalMullions=vm, horizontalMullions=hm,
                    mullionWidth=.025, frameMaterial='dark_wood', glassMaterial='glass'), 'components')


def door(i, host, start, bottom=.5, w=1.1, h=2.45, glass=False):
    return add(dict(type='door', id=i, parentWall=host, **{'from': [start, bottom, 0]},
                    width=w, height=h, frameWidth=.06, frameDepth=.26, leafDepth=.045,
                    doorStyle='double' if w > 1.5 else 'single',
                    frameMaterial='dark_wood', leafMaterial='glass' if glass else 'walnut',
                    interaction=dict(enabled=True, motion='swing', hingeSide='left',
                                     openAngle=90, initiallyOpen=False)), 'components')


def guard(i, path, height=1.05, glass=False):
    row = dict(type='railing', id=i, path=path, height=height, postSpacing=.95,
               postRadius=.018, railRadius=.022, railLevels=[.12, 1], material='bronze')
    if glass:
        row.update(infillType='glass', infillThickness=.014,
                   infillTopRatio=.94, infillMaterial='glass')
    return add(row, 'components')


def hip_roof(i, cx, cz, w, d, y, h):
    """瓦垄与瓦缝严格从原生 hip 的四坡平面推导；不复制历史屋顶参数。"""
    add(dict(type='roof', id=i, roofType='hip', span=w, depth=d,
             height=h, thickness=.16, position=[cx, y, cz], material='tile'), 'roof')
    hw, hd = w/2, d/2
    s = min(hw, hd)
    def point(x, z, lift=.023):
        return [round(cx+x, 5), round(y+h*min(hw-abs(x), hd-abs(z), s)/s+lift, 5), round(cz+z, 5)]
    nx, nz = math.ceil(w/.28), math.ceil(d/.28)
    for j in range(nx):
        x = -hw + (j+.5)*w/nx
        end = hd - min(hw-abs(x), hd)
        for sign in [-1, 1]:
            sweep(f'{i}_tile_z_{j}_{sign}', [point(x, sign*hd), point(x, sign*end)],
                  .027, 'tile_alt' if j % 4 == 0 else 'tile', 'roof_detail', 6)
    for j in range(nz):
        z = -hd + (j+.5)*d/nz
        end = hw - min(hd-abs(z), hw)
        for sign in [-1, 1]:
            sweep(f'{i}_tile_x_{j}_{sign}', [point(sign*hw, z), point(sign*end, z)],
                  .027, 'tile_alt' if j % 4 == 0 else 'tile', 'roof_detail', 6)
    # 沿等高线排瓦缝，间距约 0.44 米。
    for j in range(1, math.ceil(s/.44)):
        inset = j*.44
        x, z = hw-inset, hd-inset
        ring = [point(-x, -z, .011), point(x, -z, .011), point(x, z, .011),
                point(-x, z, .011), point(-x, -z, .011)]
        sweep(f'{i}_tile_course_{j}', ring, .008, 'tile_joint', 'roof_detail', 4)
    if hw >= hd:
        ridge = [point(-hw+hd, 0, .085), point(hw-hd, 0, .085)]
        corners = [(-hw, -hd, -hw+hd, 0), (-hw, hd, -hw+hd, 0),
                   (hw, -hd, hw-hd, 0), (hw, hd, hw-hd, 0)]
    else:
        ridge = [point(0, -hd+hw, .085), point(0, hd-hw, .085)]
        corners = [(-hw, -hd, 0, -hd+hw), (hw, -hd, 0, -hd+hw),
                   (-hw, hd, 0, hd-hw), (hw, hd, 0, hd-hw)]
    sweep(f'{i}_ridge', ridge, .085, 'tile_ridge', 'roof_detail', 10)
    for j, (x, z, rx, rz) in enumerate(corners):
        sweep(f'{i}_hip_cap_{j}', [point(x, z, .065), point(rx, rz, .065)],
              .057, 'tile_ridge', 'roof_detail', 8)
    for sign in [-1, 1]:
        box(f'{i}_fascia_z_{sign}', cx, y-.12, cz+sign*hd, w, .21, .12, 'dark_wood', 'roof_detail')
        box(f'{i}_fascia_x_{sign}', cx+sign*hw, y-.12, cz, .12, .21, d, 'dark_wood', 'roof_detail')


def chair(i, x, z, y=.5, angle=0):
    # 单椅由座垫、靠背和四根木脚组成。
    box(i+'_seat', x, y+.46, z, .5, .10, .5, 'linen', 'furniture')
    bx, bz = x+math.sin(angle)*.23, z+math.cos(angle)*.23
    box(i+'_back', bx, y+.78, bz, .5, .5, .065, 'walnut', 'furniture', [0, angle, 0])
    for a in [-1, 1]:
        for b in [-1, 1]:
            box(f'{i}_leg_{a}_{b}', x+a*.19, y+.22, z+b*.19, .045, .44, .045, 'walnut', 'furniture')


def table(i, x, z, w, d, y=.5, height=.74, mat='walnut'):
    box(i+'_top', x, y+height-.035, z, w, .07, d, mat, 'furniture')
    for a in [-1, 1]:
        for b in [-1, 1]:
            box(f'{i}_leg_{a}_{b}', x+a*(w/2-.12), y+(height-.07)/2,
                z+b*(d/2-.12), .065, height-.07, .065, 'walnut', 'furniture')


def bed(i, x, z, y=4.05, w=2.0):
    box(i+'_base', x, y+.2, z, w, .4, 2.25, 'walnut', 'furniture')
    box(i+'_mattress', x, y+.47, z, w-.07, .18, 2.16, 'linen', 'furniture')
    box(i+'_duvet', x, y+.58, z-.25, w-.05, .08, 1.6, 'sage_fabric', 'furniture')
    box(i+'_runner', x, y+.63, z-.65, w, .035, .52, 'clay', 'furniture')
    box(i+'_head', x, y+.66, z+1.15, w+.2, 1.1, .12, 'walnut', 'furniture')
    for j, dx in enumerate([-.49, .49]):
        box(f'{i}_pillow_{j}', x+dx, y+.61, z+.72, .75, .13, .42, 'linen', 'furniture')
        box(f'{i}_nightstand_{j}', x+(-1 if j == 0 else 1)*(w/2+.4), y+.27,
            z+.73, .58, .54, .55, 'walnut', 'furniture')


def tree(i, x, z, y=.5, scale=1):
    sweep(i+'_trunk', [[x, y, z], [x+.13*scale, y+1.6*scale, z],
                       [x-.1*scale, y+2.65*scale, z+.1*scale]], .09*scale, 'bark', 'landscape')
    for j, (dx, dz, dy, radius) in enumerate([(-.65, .05, 2.0, .82), (.65, .1, 2.3, .86),
                                             (-.18, -.3, 2.9, .78), (.2, .3, 3.15, .68)]):
        sweep(f'{i}_branch_{j}', [[x+.08*scale, y+1.6*scale, z],
                                [x+dx*scale, y+dy*scale, z+dz*scale]],
              .035*scale, 'bark', 'landscape')
        sphere(f'{i}_leaf_{j}', x+dx*scale, y+dy*scale, z+dz*scale,
               radius*scale, 'leaf' if j % 2 else 'leaf_light', [1, .56, 1])


def lantern(i, x, z, y, hanging=False):
    box(i+'_frame', x, y, z, .22, .4, .22, 'bronze', 'lighting')
    box(i+'_diffuser', x, y, z-.116, .15, .29, .014, 'warm_glow', 'lighting')
    box(i+'_cap', x, y+.22, z, .3, .05, .3, 'bronze', 'lighting')
    if hanging:
        sweep(i+'_stem', [[x, y+.22, z], [x, y+.65, z]], .012, 'bronze', 'lighting')
    add(dict(type='light', id=i+'_light', position=[x, y, z],
             body=[dict(shape='sphere', radius=.025, position=[0, 0, 0], material='warm_glow')],
             lightType='point', color=[1, .81, .52], lowIntensity=2, highIntensity=8,
             distance=4, initiallyOn=True), 'components')


def build():
    material('plaster', [.89, .87, .81], .91)
    material('limestone', [.68, .68, .61], .87)
    material('stone', [.24, .285, .29], .9)
    material('stone_light', [.46, .49, .46], .87)
    material('tile', [.135, .17, .18], .79)
    material('tile_alt', [.19, .225, .23], .78)
    material('tile_joint', [.075, .095, .10], .95)
    material('tile_ridge', [.205, .235, .24], .72)
    material('dark_wood', [.22, .12, .065], .7)
    material('walnut', [.38, .23, .12], .73)
    material('oak', [.58, .44, .29], .83)
    material('bronze', [.19, .19, .16], .34, .65)
    material('linen', [.87, .82, .71], .98)
    material('sage_fabric', [.37, .43, .34], 1)
    material('clay', [.55, .29, .18], .96)
    material('porcelain', [.82, .86, .81], .25)
    material('glass', [.85, .93, .92], .08, materialClass='glass', transmission=.91,
             ior=1.5, thickness=.014, side='double')
    material('water', [.11, .35, .30], .11, materialClass='glass', transmission=.55,
             ior=1.333, thickness=.04, side='double')
    material('pool', [.16, .29, .25], .85)
    material('pebbles', [.54, .52, .44], 1)
    material('soil', [.16, .14, .10], 1)
    material('grass', [.28, .35, .22], 1)
    material('leaf', [.19, .29, .19], 1)
    material('leaf_light', [.33, .40, .24], 1)
    material('bark', [.24, .17, .1], 1)
    material('warm_glow', [1, .82, .48], .35, emissive=[.65, .35, .10])

    # 场地、台基与有标高的室内楼板。
    slab('site', -3, -4.2, 23, 18.8, .08, .1, layer='site')
    for side, xa, xb in [('west', -3, -1), ('east', 21, 23)]:
        slab(side+'_lawn', xa, -3, xb, 18.8, .11, .03, 'grass', 'site')
    slab('north_lawn', -1, 17.6, 21, 18.8, .11, .03, 'grass', 'site')
    for i, (x0, z0, x1, z1) in enumerate([(0, 9, 20, 16), (0, 1, 5.2, 9), (14.8, 3.5, 20, 9)]):
        slab(f'foundation_{i}', x0-.16, z0-.16, x1+.16, z1+.16, .36, .26, 'stone', 'foundation')
        slab(f'ground_{i}', x0-.10, z0-.10, x1+.10, z1+.1, .5, .14, 'oak', 'floor_ground')
    # 二层梯井：x=[10,12.8], z=[11.1,15.2]。
    for i, rect in enumerate([(-.1, 8.95, 10, 16.1), (12.8, 8.95, 20.1, 16.1),
                               (10, 8.95, 12.8, 11.1), (10, 15.2, 12.8, 16.1)]):
        slab(f'upper_slab_{i}', *rect, 4.05, .23, 'oak', 'floor_upper')
    slab('gallery_slab', 5.15, 7.5, 14.85, 8.95, 4.05, .23, layer='floor_upper')
    # 庭院铺装环绕下沉水池，不拿连续地板穿过池水。
    for i, rect in enumerate([(5.2, .35, 14.8, 3.3), (5.2, 6.9, 14.8, 9),
                               (5.2, 3.3, 6.15, 6.9), (10.65, 3.3, 14.8, 6.9)]):
        slab(f'court_paving_{i}', *rect, .5, .16, layer='site')
    slab('pool_liner', 6.15, 3.3, 10.65, 6.9, .16, .08, 'pool', 'landscape')
    slab('pool_water', 6.25, 3.4, 10.55, 6.8, .36, .03, 'water', 'landscape')
    for i, (x, z, w, d) in enumerate([(8.4, 3.28, 4.7, .22), (8.4, 6.92, 4.7, .22),
                                     (6.13, 5.1, .22, 3.42), (10.67, 5.1, .22, 3.42)]):
        box(f'pool_coping_{i}', x, .46, z, w, .14, d, 'stone_light', 'landscape')
    for j in range(4):
        slab(f'entry_step_{j}', 10.15, -2.4+j*.62, 13.65, -1.78+j*.62,
             .185+j*.105, .105, 'stone_light', 'site')
    slab('entry_top_landing', 10.15, .08, 13.65, .35, .5, .16, layer='site')
    # 较低的分缝只发生在铺装表面。
    for j in range(8):
        box(f'court_joint_{j}', 12.65, .504, 2.6+j*.75, 2.8, .006, .012, 'stone_light', 'site')
    for j in range(6):
        box(f'front_paving_joint_{j}', 5.2+j*2.2, .085, -2.7, .012, .008, 2.5,
            'stone_light', 'site')

    for level, b, t, layer in [('g', .5, 3.82, 'wall_ground'), ('u', 4.05, 7.35, 'wall_upper')]:
        wall(f'main_front_{level}', 0, 9, 20, 9, b, t, layer=layer)
        wall(f'main_back_{level}', 0, 16, 20, 16, b, t, layer=layer)
        wall(f'main_west_{level}', 0, 9, 0, 16, b, t, layer=layer)
        wall(f'main_east_{level}', 20, 9, 20, 16, b, t, layer=layer)
    for wing, x0, x1, z0 in [('tea', 0, 5.2, 1), ('study', 14.8, 20, 3.5)]:
        wall(wing+'_front', x0, z0, x1, z0, .5, 3.75)
        wall(wing+'_west', x0, z0, x0, 9, .5, 3.75)
        wall(wing+'_east', x1, z0, x1, 9, .5, 3.75)
    # 勒脚按墙段设置，前立面避开落地开口。
    for i, (x, z, w, d) in enumerate([(-.13, 5, .12, 8), (20.13, 6.25, .12, 5.5),
                                     (-.13, 12.5, .12, 7), (20.13, 12.5, .12, 7),
                                     (10, 16.13, 20, .12), (2.6, .87, 5.2, .12),
                                     (17.4, 3.37, 5.2, .12)]):
        box(f'plinth_{i}', x, .72, z, w, .44, d, 'stone', 'facade')
    # 二层分层线与墙柱，不压住开口。
    box('floor_band_front', 10, 3.91, 8.86, 20.2, .24, .15, 'limestone', 'facade')
    box('floor_band_back', 10, 3.91, 16.14, 20.2, .24, .15, 'limestone', 'facade')
    for x in [0, 5.2, 14.8, 20]:
        box(f'front_pier_{x}', x, 5.69, 8.84, .22, 3.28, .15, 'limestone', 'facade_upper')

    door('living_to_tea', 'main_front_g', 1.8)
    window('living_court', 'main_front_g', 5.65, .68, 1.3, 2.83, 0)
    window('hall_court', 'main_front_g', 8.0, .68, 1.6, 2.83, 1)
    door('main_entry', 'main_front_g', 10.7, w=2.6, h=2.8, glass=True)
    door('dining_to_study', 'main_front_g', 16.7)
    for i, (start, w) in enumerate([(.75, 3.0), (4.65, 2.35), (8.4, 1.6), (15.4, 3.8)]):
        window(f'upper_court_{i}', 'main_front_u', start, 4.55, w, 2.45, 2 if w > 2 else 0)
    door('upper_gallery_access', 'main_front_u', 10.8, 4.05, 2.0, 2.7, glass=True)
    for level, base in [('g', 1.25), ('u', 4.8)]:
        for i, (start, w) in enumerate([(1.1, 2.65), (4.8, 1.95), (8.1, 1.1), (10.7, 1.5), (15.1, 3.6)]):
            window(f'north_{level}_{i}', 'main_back_'+level, start, base, w, 1.9, 1)
        for side in ['west', 'east']:
            for i, start in enumerate([.8, 4.0]):
                window(f'main_{side}_{level}_{i}', f'main_{side}_{level}', start, base, 2.1, 1.9, 1)
    window('tea_front_glazing', 'tea_front', .75, 1.0, 3.7, 2.35, 3)
    for i, start in enumerate([.8, 4.8]):
        window(f'tea_west_{i}', 'tea_west', start, 1.2, 2.35, 2.05, 1)
    window('tea_court_glass', 'tea_east', .85, .78, 2.8, 2.6, 2)
    door('tea_court_door', 'tea_east', 5.4, w=1.5, h=2.7, glass=True)
    window('study_front_glazing', 'study_front', .8, 1.05, 3.6, 2.25, 3)
    window('study_court_glass', 'study_west', .65, .8, 2.5, 2.55, 2)
    door('study_court_door', 'study_west', 3.65, w=1.1, h=2.6, glass=True)
    window('study_east_glass', 'study_east', .8, 1.2, 3.9, 2.05, 2)
    # 外侧挑出的木格栅与玻璃保持实际间距。
    for j in range(13):
        box(f'tea_front_screen_{j}', 1+j*.27, 2.15, .69, .045, 2.45, .085, 'walnut', 'facade')
    for j in range(10):
        box(f'study_front_screen_{j}', 15.85+j*.34, 2.13, 3.20, .045, 2.35, .085, 'walnut', 'facade')
    for x0 in [5.33, 13.95]:
        for j in range(5):
            box(f'upper_screen_{x0}_{j}', x0+j*.14, 5.65, 8.49, .04, 2.85, .09,
                'walnut', 'facade_upper')

    # 露廊真实支承与细栏杆。
    for j, x in enumerate([5.45, 9.8, 14.55]):
        box(f'gallery_column_base_{j}', x, .65, 7.72, .37, .3, .37, 'stone', 'structure')
        box(f'gallery_column_{j}', x, 2.23, 7.72, .17, 2.86, .17, 'dark_wood', 'structure')
        box(f'gallery_column_cap_{j}', x, 3.73, 7.72, .33, .14, .33, 'dark_wood', 'structure')
    box('gallery_edge_beam', 10, 3.76, 7.73, 9.6, .22, .19, 'dark_wood', 'structure')
    guard('gallery_guard', [[5.23, 4.05, 8.8], [5.23, 4.05, 7.62],
                             [14.77, 4.05, 7.62], [14.77, 4.05, 8.8]])
    for j in range(48):
        box(f'gallery_baluster_{j}', 5.36+j*.196, 4.55, 7.62, .027, .86, .032,
            'dark_wood', 'facade_upper')
    box('gallery_wood_handrail', 10, 5.12, 7.62, 9.65, .065, .065, 'walnut', 'facade_upper')
    for j in range(20):
        box(f'porch_rafter_{j}', 5.5+j*.47, 3.67, 8.23, .055, .1, 1.35, 'walnut', 'structure')

    # 室内隔墙、门洞与两跑楼梯。
    for level, b, t, layer in [('g', .5, 3.82, 'wall_ground'), ('u', 4.05, 7.35, 'wall_upper')]:
        wall('partition_l_'+level, 7.4, 9, 7.4, 16, b, t, .16, layer=layer)
        wall('partition_r_'+level, 14.1, 9, 14.1, 16, b, t, .16, layer=layer)
        door('room_l_'+level, 'partition_l_'+level, 1.1, b, 1.1)
        door('room_r_'+level, 'partition_r_'+level, 1.1, b, 1.1)
    wall('kitchen_partition', 14.1, 13, 20, 13, .5, 3.82, .14)
    door('kitchen_door', 'kitchen_partition', .6, .5, 1.0)
    wall('upper_bath_front', 7.4, 13.3, 10, 13.3, 4.05, 7.35, .14, layer='wall_upper')
    wall('upper_bath_side', 9.65, 13.3, 9.65, 16, 4.05, 7.35, .14, layer='wall_upper')
    door('upper_bath_door', 'upper_bath_front', .65, 4.05, .9)
    for i, a, b in [(1, [10.65, .5, 11.2], [10.65, 2.275, 13.9]),
                     (2, [12.15, 2.275, 13.9], [12.15, 4.05, 11.2])]:
        add(dict(type='stair', id=f'stair_flight_{i}', **{'from': a}, to=b, width=1.2,
                 stepCount=10, stepHeight=.1775, stepDepth=.27, material='stone_light'), 'stair')
    slab('stair_half_landing', 10, 13.9, 12.8, 15.15, 2.275, .18, 'stone_light', 'stair')
    guard('stair_outer_first', [[10.05, .5, 11.2], [10.05, 2.275, 13.9], [10.05, 2.275, 15.1]], .95)
    guard('stair_outer_second', [[12.75, 2.275, 15.1], [12.75, 2.275, 13.9], [12.75, 4.05, 11.2]], .95)
    guard('stair_half_back', [[10.05, 2.275, 15.1], [12.75, 2.275, 15.1]], .95)
    guard('upper_void_guard', [[11.37, 4.05, 11.1], [10, 4.05, 11.1],
                                [10, 4.05, 15.2], [12.8, 4.05, 15.2], [12.8, 4.05, 11.2]], glass=True)
    # 阶梯中央两侧分别设置扶手，避免把两跑接成陡直折线。
    guard('stair_inner_first', [[11.25, .5, 11.2], [11.25, 2.275, 13.9]], .95)
    guard('stair_inner_second', [[11.55, 2.275, 13.9], [11.55, 4.05, 11.2]], .95)

    hip_roof('main_roof', 10, 12.5, 21.6, 9.8, 7.50, 1.70)
    hip_roof('tea_roof', 2.6, 5.0, 6.55, 9.55, 3.88, 1.35)
    hip_roof('study_roof', 17.4, 6.25, 6.55, 7.05, 3.88, 1.32)
    for j in range(17):
        box(f'main_soffit_rafter_{j}', .2+j*1.22, 7.31, 8.23, .07, .12, 1.6,
            'walnut', 'roof_detail')

    # 月洞门：水平分片构成有实际孔洞的实体墙，圆环遮住微小阶梯边。
    cx, cy, cz, radius = 11.9, 2.0, .62, 1.45
    low, high, count = .5, 3.65, 48
    for j in range(count):
        y0, y1 = low+j*(high-low)/count, low+(j+1)*(high-low)/count
        # 以切片最接近圆心的点算半宽，保证墙片不侵入圆洞。
        nearest = 0 if y0 <= cy <= y1 else min(abs(y0-cy), abs(y1-cy))
        opening = math.sqrt(max(0, radius*radius-nearest*nearest)) if nearest < radius else 0
        outer = 2.15
        for sign in [-1, 1]:
            w = outer-opening
            box(f'moon_wall_{j}_{sign}', cx+sign*(opening+w/2), (y0+y1)/2, cz,
                w, y1-y0, .26, 'plaster', 'gate')
    moonpath = [[cx+radius*math.cos(k*2*math.pi/96), cy+radius*math.sin(k*2*math.pi/96), cz-.16]
                for k in range(97)]
    sweep('moon_gate_stone_ring', moonpath, .065, 'stone', 'gate', 10)
    box('moon_gate_coping', cx, 3.72, cz, 4.65, .14, .43, 'tile_ridge', 'gate')
    wall('court_screen_left', 5.25, .62, 9.75, .62, .5, 1.66, .24, layer='gate')
    box('court_screen_left_cap', 7.5, 1.72, .62, 4.65, .12, .35, 'tile_ridge', 'gate')
    wall('court_screen_right', 14.05, .62, 17.6, .62, .5, 1.66, .24, layer='gate')
    box('court_screen_right_cap', 15.82, 1.72, .62, 3.65, .12, .35, 'tile_ridge', 'gate')
    # 门侧铜色灯体和入户木格屏。
    for j, x in enumerate([9.4, 14.4]):
        lantern('entry_lantern_'+str(j), x, .38, 2.18)
    for j, x in enumerate([5.85, 9.6, 14.25]):
        lantern('porch_lantern_'+str(j), x, 8.35, 2.92, True)

    # 室内：客厅、餐厨、茶室、书斋、卧室及浴室。
    slab('living_rug', 1, 10, 6.5, 13.6, .515, .015, 'linen', 'furniture')
    box('living_sofa_base', 3.6, .75, 12.9, 3.6, .46, 1.0, 'walnut', 'furniture')
    box('living_sofa_back', 3.6, 1.12, 13.32, 3.6, .75, .16, 'sage_fabric', 'furniture')
    for j in range(3):
        box(f'sofa_cushion_{j}', 2.48+j*1.12, 1.01, 12.8, 1.05, .18, .82, 'linen', 'furniture')
        box(f'sofa_pillow_{j}', 2.5+j*1.1, 1.23, 13.04, .43, .36, .16,
            'clay' if j == 1 else 'sage_fabric', 'furniture')
    table('living_coffee', 3.7, 11.35, 1.8, .9, height=.43)
    box('living_tv_console', 3.5, .78, 9.28, 3.7, .52, .35, 'walnut', 'furniture')
    chair('living_armchair', 5.9, 11.25, angle=-math.pi/2)
    table('dining_table', 17.15, 11, 2.3, 1.0)
    for j, (x, z, a) in enumerate([(16.35, 10.1, math.pi), (17.2, 10.1, math.pi),
                                  (18, 10.1, math.pi), (16.35, 11.9, 0), (17.2, 11.9, 0), (18, 11.9, 0)]):
        chair('dining_chair_'+str(j), x, z, angle=a)
    for j in range(5):
        box(f'kitchen_base_{j}', 15.25+j*.85, .93, 15.42, .82, .86, .65, 'walnut', 'furniture')
        box(f'kitchen_handle_{j}', 15.25+j*.85, 1.05, 15.08, .32, .018, .025, 'bronze', 'furniture')
    box('kitchen_worktop', 17, 1.395, 15.42, 4.3, .07, .72, 'limestone', 'furniture')
    box('sink', 16.2, 1.44, 15.42, .72, .04, .45, 'bronze', 'furniture')
    box('stove', 18.3, 1.44, 15.42, .7, .03, .44, 'bronze', 'furniture')
    box('fridge', 19.4, 1.5, 14.16, .7, 2.0, .7, 'stone_light', 'furniture')
    table('tea_table', 2.65, 4.0, 2.1, 1.0, height=.68)
    for j, (x, z, a) in enumerate([(1.9, 3.0, math.pi), (3.3, 3.0, math.pi), (1.9, 5.0, 0), (3.3, 5.0, 0)]):
        chair('tea_chair_'+str(j), x, z, angle=a)
    box('tea_sideboard', 1.05, .95, 7.45, 1.5, .9, .55, 'walnut', 'furniture')
    table('study_desk', 17.35, 6.4, 2.4, .85)
    chair('study_chair', 17.35, 7.25)
    for j in range(5):
        box(f'bookcase_shelf_{j}', 19.5, .65+j*.45, 6.3, .38, .06, 3.5, 'walnut', 'furniture')
        for k in range(9):
            box(f'book_{j}_{k}', 19.49, .83+j*.45, 4.85+k*.35, .22, .29, .12,
                ['linen', 'clay', 'sage_fabric'][k % 3], 'furniture')
    for j, x in enumerate([2.8, 17.15]):
        bed('bedroom_'+str(j), x, 13.6)
        box('wardrobe_'+str(j), x, 5.15, 15.48, 3.4, 2.2, .65, 'walnut', 'furniture')
        for k in range(4):
            box(f'wardrobe_handle_{j}_{k}', x-1.15+k*.76, 5.25, 15.14, .018, .32, .025,
                'bronze', 'furniture')
    table('master_desk', 5.5, 10.3, 1.7, .65, y=4.05)
    chair('master_chair', 5.5, 11.1, y=4.05)
    box('bath_vanity', 8.5, 4.52, 15.45, 1.7, .94, .6, 'walnut', 'furniture')
    box('bath_basin', 8.5, 5.03, 15.42, .7, .1, .42, 'porcelain', 'furniture')
    box('bath_mirror', 8.5, 5.82, 15.88, 1.25, 1.15, .035, 'bronze', 'furniture')
    for j, (x, z, y) in enumerate([(2.65, 4, 1.23), (3.7, 11.35, .97), (17.15, 11, 1.29)]):
        sphere('ceramic_vase_'+str(j), x, y+.1, z, .11, 'porcelain', [.7, 1.3, .7], 'furniture')

    # 院落种植：分层冠幅、小竹与景石，避免巨球遮住建筑。
    for j, (x, z, s) in enumerate([(-1.8, 3.0, 1), (21.8, 13.5, 1.15),
                                  (6.0, 7.5, .68), (17.7, -1.3, .9)]):
        slab(f'tree_bed_{j}', x-.85, z-.85, x+.85, z+.85, .15 if j != 2 else .51,
             .06, 'soil', 'landscape')
        tree('tree_'+str(j), x, z, .15 if j != 2 else .51, s)
    slab('dry_garden', 14.8, 1.15, 20, 2.85, .16, .05, 'pebbles', 'landscape')
    for j, (x, z, r) in enumerate([(16.1, 2.0, .58), (16.85, 1.75, .37), (17.3, 2.05, .28)]):
        sphere('garden_rock_'+str(j), x, .3, z, r, 'stone_light', [.8, .75, 1.0])
    for j in range(8):
        x, z = 18.3+j*.14, 2.15+(j % 3)*.14
        sweep(f'bamboo_{j}', [[x, .16, z], [x+.05, 1.9+j%3*.15, z]], .018, 'leaf', 'landscape')
        for k in range(3):
            sphere(f'bamboo_leaf_{j}_{k}', x+.1*(-1 if k % 2 else 1), 1.0+k*.35,
                   z, .18, 'leaf_light', [1.8, .25, .5])
    for j in range(15):
        x, z = (-.55, 1.5+j*.95) if j < 8 else (20.55, 4+(j-8)*1.6)
        sphere('hedge_'+str(j), x, .37, z, .3, 'leaf', [1, .7, 1])
    for j in range(6):
        sphere(f'pool_lily_{j}', 6.65+(j % 3)*.36, .39, 3.85+(j//3)*.37,
               .12, 'leaf', [1, .07, 1])
    box('court_bench', 6.35, .76, 2.05, 1.8, .14, .48, 'walnut', 'landscape')
    for j, x in enumerate([5.67, 7.03]):
        box(f'court_bench_leg_{j}', x, .61, 2.05, .12, .25, .4, 'stone', 'landscape')
    for j, (x, z) in enumerate([(5.6, 2.85), (10.95, 3.2), (10.95, 6.5), (14.2, 7.3)]):
        lantern('garden_lantern_'+str(j), x, z, .83)
    for j, (x, z, y) in enumerate([(3.6, 11.6, 2.95), (17.1, 11, 3.05), (2.65, 4, 2.85)]):
        lantern('interior_pendant_'+str(j), x, z, y, True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--revision', default='r1')
    args = parser.parse_args()
    build()
    bp = dict(meta=dict(version='1.1', type='building', name='听澜合院 · 新中式别墅',
                        author='Codex', style='neo-chinese-courtyard', seed=20261022),
              geometry=dict(elements=E, components=C), materials=M, assets={}, behaviors={}, editor=dict(revision=0))
    raw = (json.dumps(bp, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n').encode('utf-8')
    final = HERE/'听澜合院-新中式别墅.wild'
    final.write_bytes(raw)
    archive = HERE/'03-过程记录'/args.revision
    archive.mkdir(parents=True, exist_ok=True)
    (archive/f'听澜合院-{args.revision}.wild').write_bytes(raw)
    (archive/'生成脚本.py').write_bytes(Path(__file__).read_bytes())
    (HERE/'03-过程记录'/'构件分层.json').write_text(json.dumps(LAYERS, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = dict(revision=args.revision, file=final.name, sha256=hashlib.sha256(raw).hexdigest(),
                   bytes=len(raw), elements=len(E), components=len(C), materials=len(M),
                   element_types=dict(Counter(e['type'] for e in E)),
                   layers=dict(Counter(LAYERS.values())), generator='当前对话 Codex 设计 + 确定性 Python 作者脚本',
                   model_calls=0, application_source_modified=False)
    (archive/'生成摘要.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
