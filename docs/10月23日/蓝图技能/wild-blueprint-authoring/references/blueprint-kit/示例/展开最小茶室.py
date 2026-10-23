"""仅展开本文教学茶室，不是按自然语言生成任意建筑的通用生成器。"""
import argparse
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent


def blueprint():
    materials = {}
    for name, color, roughness, metallic, extra in (
        ('plaster', [.84, .82, .76], .85, 0, {}),
        ('stone', [.60, .61, .56], .78, 0, {}),
        ('wood', [.34, .19, .10], .58, 0, {}),
        ('frame', [.10, .13, .13], .35, .6, {}),
        ('glass', [.87, .93, .94], .08, 0, dict(materialClass='glass', transmission=.88, ior=1.5, thickness=.012)),
        ('linen', [.65, .69, .57], .92, 0, {}),
        ('glow', [1, .82, .52], .4, 0, dict(emissive=[1, .65, .25], emissiveIntensity=1.4)),
    ):
        materials[name] = dict(baseColor=color, roughness=roughness, metallic=metallic,
                               albedo=1, lightingCondition='D65_noon', **extra)
    elements = []

    def add(kind, identifier, **fields):
        elements.append(dict(type=kind, id=identifier, **fields))

    def box(identifier, position, dimensions, material, **extra):
        add('primitive', identifier, shape='box', position=position, dimensions=dimensions,
            material=material, **extra)

    add('floor', 'site', **{'from': [-6, -.12, -5]}, to=[6, -.12, 5], thickness=.18, material='stone')
    box('plinth', [0, .19, .4], [6.24, .26, 5.04], 'stone')
    add('floor', 'floor_l1', **{'from': [-3.12, .32, -2.12]}, to=[3.12, .32, 2.92], thickness=.04, material='wood')
    add('floor', 'porch', **{'from': [-1.8, .06, -3.1]}, to=[1.8, .06, -2.12], thickness=.30, material='stone')
    add('stair', 'entry_stair', **{'from': [0, .06, -3.64]}, to=[0, .36, -3.1], width=1.6,
        stepCount=2, stepHeight=.15, stepDepth=.27, material='stone')
    for name, a, b in (
        ('front', [-3, .36, -2], [3, 3.22, -2]),
        ('right', [3, .36, -2], [3, 3.22, 2.8]),
        ('back', [3, .36, 2.8], [-3, 3.22, 2.8]),
        ('left', [-3, .36, 2.8], [-3, 3.22, -2]),
    ):
        add('wall', 'wall_'+name, **{'from': a}, to=b, thickness=.24, material='plaster')
    add('roof', 'roof_main', roofType='flat', position=[0, 3.22, .4], span=6.7, depth=5.5,
        height=.18, thickness=.18, material='stone')
    box('roof_cap_front', [0, 3.44, -2.29], [6.7, .08, .12], 'frame')
    box('roof_cap_back', [0, 3.44, 3.09], [6.7, .08, .12], 'frame')
    box('roof_cap_left', [-3.29, 3.44, .4], [.12, .08, 5.26], 'frame')
    box('roof_cap_right', [3.29, 3.44, .4], [.12, .08, 5.26], 'frame')
    box('name_board', [0, 2.86, -2.17], [2.1, .36, .08], 'wood', rotation=[0, math.pi, 0],
        label=dict(text='听风茶室', color=[1, .9, .62], fontFamily='serif'))
    box('pendant', [0, 2.75, .7], [.16, .12, .16], 'glow',
        lightSource=dict(lightType='point', color=[1, .78, .46], intensity=8, distance=5, initiallyOn=True))
    box('pendant_cable', [0, 3.01, .7], [.018, .40, .018], 'frame')
    box('counter_body', [1.95, .76, 1.75], [1.4, .8, .7], 'wood')
    box('counter_top', [1.95, 1.2, 1.75], [1.5, .08, .8], 'stone')
    add('furniture', 'tea_table', subtype='table', position=[-.7, .36, .65],
        dimensions=dict(width=1.3, depth=.75, height=.74), material='wood')
    for identifier, x, angle in (('chair_w', -1.75, -math.pi/2), ('chair_e', .35, math.pi/2)):
        add('furniture', identifier, subtype='chair', position=[x, .36, .65], rotation=[0, angle, 0],
            dimensions=dict(width=.5, depth=.55, height=.85), material='linen')
    for index, x in enumerate((-2.1, 2.1)):
        box(f'front_sill_{index}', [x, 1.145, -2.16], [1.38, .11, .38], 'stone')
        box(f'front_lintel_{index}', [x, 2.64, -2.15], [1.42, .12, .34], 'stone')
    components = [dict(type='door', id='entry_door', parentWall='wall_front',
                       **{'from': [2.35, .36, 0]}, width=1.3, height=2.2, frameWidth=.055,
                       frameDepth=.24, leafDepth=.035, frameMaterial='frame', leafMaterial='glass',
                       interaction=dict(mode='swing', hingeSide='left', openAngle=90, initiallyOpen=False))]
    for identifier, host, along, width in (
        ('front_w', 'wall_front', .3, 1.2), ('front_e', 'wall_front', 4.5, 1.2),
        ('east', 'wall_right', 1.25, 2.2), ('west', 'wall_left', 1.25, 2.2),
        ('back', 'wall_back', 1.8, 2.4),
    ):
        components.append(dict(type='window', id='window_'+identifier, parentWall=host,
                               **{'from': [along, 1.2, 0]}, width=width, height=1.36,
                               frameWidth=.05, frameDepth=.24, glassDepth=.012,
                               verticalMullions=1, mullionWidth=.025,
                               frameMaterial='frame', glassMaterial='glass'))
    return dict(meta=dict(version='1.1', type='building', name='听风茶室 · 语法教学例'),
                geometry=dict(elements=elements, components=components), materials=materials)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / '听风茶室.wild')
    args = parser.parse_args()
    text = json.dumps(blueprint(), ensure_ascii=False, separators=(',', ':')) + '\n'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding='utf-8', newline='\n')
    print(args.output)


if __name__ == '__main__':
    main()
