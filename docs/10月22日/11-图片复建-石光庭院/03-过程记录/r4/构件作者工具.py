"""本日两栋建筑的原语作者工具；从听澜本轮作者脚本抽取，无建筑方案参数。"""
import math
E, C, LAYERS, M = [], [], {}, {}

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
                    interaction=dict(mode='swing', hingeSide='left',
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
