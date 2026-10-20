"""本次概念方案的可重放作者脚本；只写本目录的交付文件，不是通用别墅生成器。"""
import json
import math
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
DESIGN = json.loads((HERE / '01-设计事实.json').read_text(encoding='utf-8'))
LEVEL, AX = DESIGN['levels'], DESIGN['axes']
F0, F1, TOP = LEVEL['ground'], LEVEL['upper'], LEVEL['roof_support']
T, HALF = LEVEL['slab_thickness'], LEVEL['half_landing']
W, E, S, N = AX['west'], AX['east'], AX['south'], AX['north']
FRONT, WING, LIVING = AX['main_front'], AX['wing_east'], AX['living_west']
elements, components, materials = [], [], {}


def mat(name, color, roughness=0.8, metallic=0, **extra):
    materials[name] = dict(baseColor=color, roughness=roughness, metallic=metallic,
                           albedo=1, lightingCondition='D65_noon', **extra)


def box(name, bounds, material):
    x0, x1, y0, y1, z0, z1 = bounds
    elements.append(dict(type='primitive', id=name, shape='box',
                         position=[(x0+x1)/2, (y0+y1)/2, (z0+z1)/2],
                         dimensions=[x1-x0, y1-y0, z1-z0], material=material))


def floor(name, rect, top, thickness, material):
    x0, x1, z0, z1 = rect
    elements.append({'type': 'floor', 'id': name, 'from': [x0, top-thickness, z0],
                     'to': [x1, top-thickness, z1], 'thickness': thickness, 'material': material})


def wall(name, x0, z0, x1, z1, bottom, top, material='chalk', thickness=0.24):
    elements.append({'type': 'wall', 'id': name, 'from': [x0, bottom, z0],
                     'to': [x1, top, z1], 'thickness': thickness, 'material': material})


def window(name, host, along, bottom, width, height, vertical=0, horizontal=0):
    components.append(dict(type='window', id=name, parentWall=host,
                           **{'from': [along, bottom, 0]}, width=width, height=height,
                           frameWidth=0.05, frameDepth=0.24, glassDepth=0.012,
                           verticalMullions=vertical, horizontalMullions=horizontal,
                           mullionWidth=0.025, frameMaterial='bronze', glassMaterial='clear_glass'))


def door(name, host, along, bottom, width=0.9, height=2.3, glazed=False):
    components.append(dict(type='door', id=name, parentWall=host,
                           **{'from': [along, bottom, 0]}, width=width, height=height,
                           frameWidth=0.055, frameDepth=0.24, leafDepth=0.035,
                           frameMaterial='bronze', leafMaterial='clear_glass' if glazed else 'walnut',
                           openingStyle='rectangular', doorStyle='double' if width > 1.3 else 'single',
                           interaction={'mode': 'slide' if glazed else 'swing', 'hingeSide': 'left'}))


def furniture(name, subtype, x, y, z, width, depth, height, material, angle=0):
    elements.append(dict(type='furniture', id=name, subtype=subtype, position=[x,y,z],
                         rotation=[0,angle,0], dimensions=dict(width=width, depth=depth, height=height),
                         material=material))


def railing(name, path, glass=False, height=1.08):
    row = dict(type='railing', id=name, path=path, height=height,
               postSpacing=1.15, postRadius=0.017, railRadius=0.018,
               railLevels=[1] if glass else [0.5,1], material='bronze')
    if glass:
        row.update(infillType='glass', infillThickness=0.012, infillTopRatio=0.96,
                   infillMaterial='clear_glass')
    components.append(row)


def sphere(name, x, y, z, radius, material, scale=None):
    row = dict(type='primitive', id=name, shape='sphere', position=[x,y,z],
               radius=radius, segments=18, material=material)
    if scale:
        row['scale'] = scale
    elements.append(row)


def cylinder(name, x, bottom, z, radius, height, material):
    elements.append(dict(type='primitive', id=name, shape='cylinder',
                         position=[x,bottom+height/2,z], radiusTop=radius,
                         radiusBottom=radius, height=height, segments=14, material=material))


def light(name, x, y, z, radius=0.11):
    components.append(dict(type='light', id=name, position=[x,y,z],
                           body=[dict(shape='sphere', radius=radius, position=[0,0,0], material='warm_glow')],
                           lightType='point', color=[1,0.84,0.63], lowIntensity=2, highIntensity=10,
                           distance=7, initiallyOn=True))


mat('chalk', [0.88,0.865,0.82], 0.84)
mat('travertine', [0.61,0.565,0.46], 0.9)
mat('sandstone', [0.73,0.69,0.59], 0.9)
mat('basalt', [0.22,0.245,0.235], 0.92)
mat('roof_graphite', [0.24,0.27,0.265], 0.72, 0.18)
mat('teak', [0.48,0.30,0.16], 0.74)
mat('oak_floor', [0.65,0.49,0.31], 0.78)
mat('walnut', [0.30,0.19,0.115], 0.72)
mat('bronze', [0.25,0.215,0.16], 0.34, 0.75)
mat('clear_glass', [0.88,0.95,0.96], 0.07, materialClass='glass',
    transmission=0.92, ior=1.5, thickness=0.012, opacity=1, side='double')
mat('water_jade', [0.21,0.54,0.50], 0.1, materialClass='glass',
    transmission=0.64, ior=1.333, thickness=0.04, opacity=1, side='double')
mat('pool_liner', [0.26,0.47,0.405], 0.78)
mat('linen', [0.84,0.80,0.70], 0.98)
mat('clay_fabric', [0.58,0.34,0.24], 0.97)
mat('sage_fabric', [0.40,0.46,0.36], 0.99)
mat('rug', [0.66,0.625,0.53], 1)
mat('porcelain', [0.88,0.89,0.85], 0.25)
mat('screen', [0.035,0.045,0.048], 0.23)
mat('soil', [0.18,0.14,0.095], 1)
mat('grass', [0.31,0.39,0.255], 1)
mat('leaf', [0.22,0.33,0.215], 1)
mat('leaf_light', [0.37,0.43,0.27], 1)
mat('warm_glow', [1,0.83,0.55], 0.4, emissive=[0.4,0.23,0.09])

# 场地与水平板。水池、种植床和上层空洞均由分区板留空。
floor('site', DESIGN['site'], 0, 0.12, 'sandstone')
floor('west_lawn', [-2.4,-0.65,-2.5,16.2], 0.035, 0.035, 'grass')
floor('east_lawn', [19.1,20.4,-2.5,16.2], 0.035, 0.035, 'grass')
floor('north_lawn', [-0.65,19.1,15.2,16.8], 0.035, 0.035, 'grass')
box('foundation_main', [-0.18,18.18,0,0.12,6.42,14.58], 'basalt')
box('foundation_wing', [-0.18,6.18,0,0.12,-0.18,6.42], 'basalt')
floor('ground_main', [-0.12,18.12,6.48,14.52], F0, T, 'sandstone')
floor('ground_library', [-0.12,6.12,-0.12,6.48], F0, T, 'oak_floor')
for i, rect in enumerate(DESIGN['upper_slab_rectangles']):
    floor(f'upper_slab_{i}', rect, F1, T, 'oak_floor')
for i, rect in enumerate([[6,18.5,-0.3,0.7],[6,18.5,4.8,6.48],[6,7,0.7,4.8],
                          [10.7,12.4,0.7,4.8],[7,10.7,0.7,1],[7,10.7,4.5,4.8],[17.5,18.5,0.7,4.8]]):
    floor(f'courtyard_deck_{i}', rect, F0, 0.22, 'sandstone')
floor('garden_soil', [7,10.7,1,4.5], 0.27, 0.15, 'soil')
floor('garden_green', [7.08,10.62,1.08,4.42], 0.285, 0.015, 'grass')
floor('pond_bottom', [12.4,17.5,0.7,4.8], 0.045, 0.065, 'pool_liner')
box('pond_water', [12.5,17.4,0.265,0.285,0.8,4.7], 'water_jade')
for i, bounds in enumerate([[12.4,12.52,0.045,F0,0.7,4.8],[17.38,17.5,0.045,F0,0.7,4.8],
                             [12.52,17.38,0.045,F0,0.7,0.82],[12.52,17.38,0.045,F0,4.68,4.8]]):
    box(f'pond_edge_{i}', bounds, 'travertine')
for i in range(4):
    floor(f'approach_step_{i}', [6.7,8.3,-2.05+i*0.47,-1.68+i*0.47], 0.075*(i+1), 0.075*(i+1), 'basalt')
railing('approach_left', [[6.65,0,-2.2],[6.65,F0,-0.3]], height=0.9)
railing('approach_right', [[8.35,0,-2.2],[8.35,F0,-0.3]], height=0.9)

# 外围护共享界面只建一面墙；门窗全部由组件生成开口、框扇和玻璃。
wall('library_south', 0,0,6,0,F0,F1-T)
wall('library_west', 0,0,0,6.6,F0,F1-T,'travertine')
wall('library_east', 6,0,6,6.6,F0,F1-T)
wall('library_dining_interface', 0,6.6,6,6.6,F0,F1-T)
wall('entry_front', 6,6.6,LIVING,6.6,F0,F1-T,'travertine')
wall('living_front', LIVING,6.6,18,6.6,F0,TOP)
wall('main_west_lower', 0,6.6,0,14.4,F0,F1-T,'travertine')
wall('main_west_upper', 0,6.6,0,14.4,F1,TOP,'travertine')
wall('upper_front', 0,6.6,LIVING,6.6,F1,TOP)
wall('main_north_lower', 0,14.4,LIVING,14.4,F0,F1-T)
wall('main_north_upper', 0,14.4,LIVING,14.4,F1,TOP)
wall('living_north', LIVING,14.4,18,14.4,F0,TOP)
wall('living_east', 18,6.6,18,14.4,F0,TOP)
wall('dining_hall', 5.9,6.6,5.9,11.2,F0,F1-T,thickness=0.18)
wall('bath_ground_front', 5.9,11.2,8.35,11.2,F0,F1-T,thickness=0.18)
wall('bath_ground_east', 8.35,11.2,8.35,14.4,F0,F1-T,thickness=0.18)
wall('kitchen_bath', 5.9,11.2,5.9,14.4,F0,F1-T,thickness=0.18)
wall('bedrooms_front', 0,9.7,8.35,9.7,F1,TOP,thickness=0.18)
wall('bedroom_divide', 4.8,9.7,4.8,14.4,F1,TOP,thickness=0.18)
wall('guest_stair', 8.35,9.7,8.35,14.4,F1,TOP,thickness=0.18)
wall('bath_upper_east', 2.65,6.6,2.65,9.7,F1,TOP,thickness=0.18)
door('main_entry','entry_front',0.8,F0,1.4,2.5)
door('dining_entry','dining_hall',0.85,F0,1.3,2.35,True)
door('library_connection','library_dining_interface',1.8,F0,2.4,2.6,True)
door('living_garden','living_front',3.2,F0,2.8,2.75,True)
door('bath_ground_door','bath_ground_front',0.45,F0,0.85,2.2)
door('master_door','bedrooms_front',3.35,F1,0.95,2.3)
door('guest_door','bedrooms_front',5.85,F1,0.9,2.3)
door('bath_upper_door','bath_upper_east',0.85,F1,0.85,2.2)
door('terrace_connection','upper_front',3.5,F1,1.6,2.5,True)
window('library_courtyard_glass','library_east',0.65,F0+0.35,5.3,2.45,3)
window('library_south_glass','library_south',0.65,F0+0.35,4.7,2.45,2)
window('library_west_slot','library_west',1.0,F0+2.15,4.6,0.55,2)
window('dining_west_glass','main_west_lower',0.8,F0+0.65,2.65,2.15,1)
window('kitchen_west_slot','main_west_lower',4.85,F0+1.4,2.15,1.1,1)
window('kitchen_north_slot','main_north_lower',1.2,F0+1.4,4.0,1.1,2)
window('bath_ground_slot','main_north_lower',6.5,F0+1.9,1.2,0.65)
window('stair_lower_slot','main_north_lower',9.0,F0+0.9,1.75,1.9)
window('master_north_glass','main_north_upper',0.65,F1+0.8,3.5,2.0,1)
window('guest_north_glass','main_north_upper',5.1,F1+1.2,2.75,1.6,1)
window('stair_upper_glass','main_north_upper',8.9,F1+0.65,1.9,2.15,1)
window('bath_upper_slot','upper_front',0.6,F1+1.9,1.4,0.65)
window('gallery_front_glass','upper_front',6.05,F1+0.45,4.65,2.35,2)
window('living_front_tall','living_front',0.55,F0+0.5,2.15,5.55,0,1)
window('living_front_high','living_front',3.2,F1+0.15,2.8,2.6,1)
window('living_east_tall','living_east',1.0,F0+0.55,5.8,5.5,3,1)
window('living_north_glass','living_north',0.85,F0+0.6,4.9,5.45,2,1)

# 原生 roof 承担真实覆盖面。露台板顶与上层门底使用同一个 F1。
elements.append(dict(type='roof', id='main_roof', roofType='flat', ridgeAxis='x',
                     span=19.3, depth=9.1, height=T, thickness=T,
                     position=[9,TOP,10.5], material='roof_graphite'))
elements.append(dict(type='roof', id='library_terrace_roof', roofType='flat', ridgeAxis='x',
                     span=6.5, depth=7.0, height=T, thickness=T,
                     position=[3,F1-T,3.1], material='sandstone'))
box('main_soffit', [-0.65,18.65,TOP-0.11,TOP,5.95,15.05], 'chalk')
for i, bounds in enumerate([[-0.45,18.45,TOP+T,TOP+T+0.3,6.15,6.28],
                            [-0.45,18.45,TOP+T,TOP+T+0.3,14.72,14.85],
                            [-0.45,-0.32,TOP+T,TOP+T+0.3,6.28,14.72],
                            [18.32,18.45,TOP+T,TOP+T+0.3,6.28,14.72]]):
    box(f'roof_parapet_{i}', bounds, 'chalk')
box('entry_canopy', [6.2,10.2,3.14,3.34,5.25,6.65], 'chalk')
for i,x in enumerate([6.35,10.05]):
    box(f'entry_post_{i}', [x-0.07,x+0.07,F0,3.14,5.33,5.47], 'bronze')
box('living_stone_spine', [10.92,11.3,F0,TOP,6.34,6.48], 'travertine')
for i in range(12):
    z=0.48+i*0.48
    box(f'library_timber_rib_{i}', [6.13,6.24,F0+0.24,F1-T-0.2,z,z+0.065], 'teak')
railing('terrace_guard', [[0.13,F1,6.38],[0.13,F1,0.13],[5.87,F1,0.13],[5.87,F1,6.38]], True)
for i,(x,z) in enumerate([(0.35,0.35),(5.65,0.35),(0.35,3.8),(5.65,3.8)]):
    box(f'pergola_post_{i}', [x-0.065,x+0.065,F1,5.72,z-0.065,z+0.065], 'bronze')
for i,z in enumerate([0.35,3.8]):
    box(f'pergola_beam_{i}', [0.27,5.73,5.72,5.95,z-0.08,z+0.08], 'teak')
for i in range(14):
    x=0.35+i*(5.3/13)
    box(f'pergola_slat_{i}', [x-0.045,x+0.045,5.95,6.08,0.2,3.95], 'teak')

# 梯段、平台、洞口与上层出口一起安排，不由渲染器猜补。
st=DESIGN['stair']
for name,x,y0,y1,z0,z1 in [('stair_first',st['x_first'],F0,HALF,st['z_front'],st['z_back']),
                           ('stair_second',st['x_second'],HALF,F1,st['z_back'],st['z_front'])]:
    elements.append(dict(type='stair', id=name, **{'from':[x,y0,z0], 'to':[x,y1,z1]},
                         width=st['width'], stepCount=st['steps_each'],
                         stepDepth=abs(z1-z0)/st['steps_each'], stepHeight=(y1-y0)/st['steps_each'], material='teak'))
floor('stair_half_landing', st['landing_rect'], HALF, 0.18, 'teak')
railing('stair_first_guard', [[8.43,F0,9.4],[8.43,HALF,12.2]], height=0.96)
railing('stair_central_guard', [[9.7,F0,9.4],[9.7,HALF,12.2],[9.9,HALF,12.2],[9.9,F1,9.4]], height=0.96)
railing('stair_second_guard', [[11.17,HALF,12.2],[11.17,F1,9.4]], height=0.96)
railing('landing_back_guard', [[8.43,HALF,13.5],[11.17,HALF,13.5]], height=0.96)
railing('void_front_guard', [[8.35,F1,9.4],[9.78,F1,9.4]], True)
railing('void_back_guard', [[8.35,F1,13.6],[11.25,F1,13.6]], True)
railing('living_gallery_guard', [[11.33,F1,6.8],[11.33,F1,14.2]], True)

# 家具按照底面中心锚点落地，椅子/沙发朝向由目标用途决定。
floor('living_rug', [12.25,17.1,8.75,12.25], F0+0.012, 0.012, 'rug')
furniture('living_sofa','sofa',14.4,F0,12.55,3.1,1.0,0.86,'linen',math.pi)
furniture('living_table','table',14.4,F0,10.45,1.65,0.85,0.38,'walnut')
furniture('living_armchair','chair',16.8,F0,10.35,0.85,0.85,0.9,'clay_fabric',-math.pi/2)
furniture('living_media','tv_cabinet',13.15,F0,7.04,2.0,0.45,0.45,'walnut')
box('living_screen',[12.45,13.85,F0+0.65,F0+1.5,6.86,6.93],'screen')
furniture('dining_table','table',3.2,F0,9.8,2.5,1.0,0.77,'teak')
for i,x in enumerate([2.35,3.2,4.05]):
    furniture(f'dining_chair_s_{i}','chair',x,F0,8.8,0.5,0.52,0.86,'linen')
    furniture(f'dining_chair_n_{i}','chair',x,F0,10.8,0.5,0.52,0.86,'linen',math.pi)
box('kitchen_base_north',[0.35,5.5,F0,F0+0.84,13.55,14.23],'teak')
box('kitchen_worktop_north',[0.3,5.55,F0+0.84,F0+0.9,13.5,14.28],'porcelain')
box('kitchen_base_west',[0.18,0.88,F0,F0+0.84,11.55,13.55],'teak')
box('kitchen_worktop_west',[0.15,0.92,F0+0.84,F0+0.9,11.5,13.55],'porcelain')
box('kitchen_hob',[3.65,4.45,F0+0.902,F0+0.925,13.65,14.1],'screen')
box('kitchen_sink',[1.25,2.05,F0+0.901,F0+0.92,13.65,14.1],'bronze')
for i in range(7):
    x=0.53+i*0.71
    box(f'kitchen_pull_{i}',[x,x+0.28,F0+0.68,F0+0.7,13.525,13.55],'bronze')
furniture('library_bookcase','bookshelf',0.64,F0,2.9,3.6,0.46,2.15,'walnut',math.pi/2)
furniture('library_sofa','sofa',4.85,F0,2.9,2.0,0.86,0.83,'sage_fabric',-math.pi/2)
furniture('library_coffee','table',3.35,F0,2.65,1.15,0.65,0.4,'teak')
furniture('library_chair','chair',2.5,F0,1.2,0.75,0.75,0.87,'linen')
furniture('library_desk','table',1.55,F0,5.55,1.6,0.65,0.76,'teak')
furniture('library_desk_chair','chair',1.55,F0,4.65,0.52,0.52,0.85,'linen')
furniture('master_bed','bed',1.68,F1,12.1,2.0,2.2,1.05,'linen',math.pi/2)
for i,z in enumerate([10.75,13.45]):
    furniture(f'master_nightstand_{i}','nightstand',0.74,F1,z,0.5,0.5,0.52,'walnut')
furniture('master_wardrobe','wardrobe',1.65,F1,10.13,2.55,0.6,2.35,'teak')
furniture('guest_bed','bed',6.6,F1,12.5,1.5,2.0,1.05,'linen',math.pi)
furniture('guest_nightstand','nightstand',7.75,F1,13.25,0.45,0.45,0.5,'walnut')
furniture('guest_wardrobe','wardrobe',5.22,F1,10.95,1.55,0.58,2.3,'teak',math.pi/2)
for name,x,z,y in [('ground',6.7,13.6,F0),('upper',0.75,8.75,F1)]:
    box(f'bath_{name}_vanity',[x-0.45,x+0.45,y,y+0.82,z-0.28,z+0.28],'walnut')
    box(f'bath_{name}_basin',[x-0.35,x+0.35,y+0.82,y+0.94,z-0.22,z+0.22],'porcelain')
    box(f'bath_{name}_wc',[x+0.55,x+1.1,y,y+0.46,z-1.0,z-0.3],'porcelain')
furniture('terrace_chair_a','chair',1.8,F1,2.1,0.85,0.85,0.86,'linen',0.55)
furniture('terrace_chair_b','chair',3.8,F1,2.1,0.85,0.85,0.86,'linen',-0.55)
furniture('terrace_table','table',2.8,F1,3.05,0.9,0.65,0.4,'teak')
furniture('garden_bench','sofa',15.2,F0,0.1,1.8,0.65,0.74,'teak')

# 景观按模型原语表达，无外部模型、贴图或图片。
for i,(x,z,bottom,radius) in enumerate([(8.8,2.8,0.285,1.1),(-1.25,3.2,0.035,0.95),(19.65,12.0,0.035,0.9)]):
    cylinder(f'tree_trunk_{i}',x,bottom,z,0.075,2.15,'walnut')
    for j,(dx,dy,dz,rr) in enumerate([(0,2.6,0,radius),(-0.55,2.15,0.2,radius*0.7),(0.5,2.3,-0.2,radius*0.8)]):
        sphere(f'tree_crown_{i}_{j}',x+dx,bottom+dy,z+dz,rr,'leaf' if j%2 else 'leaf_light',[1,0.8,1])
for i in range(6):
    sphere(f'garden_shrub_{i}',7.5+(i%3)*1.2,0.5,1.45+(i//3)*2.5,0.32,'leaf',[1,0.65,1])
for i in range(5):
    x=0.75+i*1.1
    box(f'north_planter_{i}',[x-0.4,x+0.4,0.035,0.42,15.6,16.3],'travertine')
    sphere(f'north_shrub_{i}',x,0.62,15.95,0.38,'leaf',[1,0.7,1])
for i,(x,z,y) in enumerate([(2.6,9.8,2.7),(3.8,9.8,2.7),(13.3,10.5,5.5),(15.0,10.5,5.15),(16.2,10.5,5.7)]):
    cylinder(f'pendant_cord_{i}',x,y+0.11,z,0.009,(TOP-0.11 if i>1 else F1-T)-(y+0.11),'bronze')
    light(f'pendant_{i}',x,y,z)
for i,(x,z) in enumerate([(6.5,5.75),(9.65,5.75),(0.9,0.7),(5.25,0.7)]):
    light(f'exterior_light_{i}',x,2.75 if i<2 else 5.45,z,0.085)


def rounded(value):
    if isinstance(value,float):
        if not math.isfinite(value):
            raise ValueError('Non-finite coordinate')
        return round(value,5)
    if isinstance(value,list):
        return [rounded(x) for x in value]
    if isinstance(value,dict):
        return {k:rounded(v) for k,v in value.items()}
    return value


blueprint = rounded(dict(meta=dict(version='1.0',type='building',name=DESIGN['name'],author='Codex',
                                   style='warm-modern-courtyard',description='两层主楼与单层书房翼围合庭院；通高客厅、屋顶露台与浅水庭。'),
                         geometry=dict(elements=elements,components=components),materials=materials,assets={}))
target=HERE.parent/'汀院别墅-Codex.wild'
target.write_text(json.dumps(blueprint,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps(dict(file=str(target),elements=len(elements),components=len(components),materials=len(materials),
                      bytes=target.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest()),ensure_ascii=False))
