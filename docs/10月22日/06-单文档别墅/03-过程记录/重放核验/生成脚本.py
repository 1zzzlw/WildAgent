"""仅按《Wild蓝图设计语言》1.2 版重新设计，完整展开自足 WILD。

无项目/其他作者工具导入；标准库只用于数学、JSON、文件和可重放记录。
"""
import argparse
import hashlib
import json
import math
import shutil
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[2]
RULE = ROOT/'docs/Wild蓝图设计语言.md'
parser = argparse.ArgumentParser()
parser.add_argument('--revision', required=True)
args = parser.parse_args()
E, C, LAYERS, M = [], [], {}, {}

def add(obj, layer):
    assert obj['id'] not in LAYERS, obj['id']
    LAYERS[obj['id']] = layer
    (C if obj['type'] in {'door','window','railing','light'} else E).append(obj)
    return obj['id']

def material(i, rgb, rough=.8, metallic=0, **extra):
    M[i] = dict(baseColor=rgb, roughness=rough, metallic=metallic,
                albedo=1, lightingCondition='D65_noon', **extra)

def box(i, x, y, z, w, h, d, mat, layer='detail', rot=None):
    row = dict(id=i, type='primitive', shape='box', position=[x,y,z],
               dimensions=[w,h,d], material=mat)
    if rot is not None: row['rotation'] = rot
    return add(row, layer)

def cylinder(i, x, y, z, r, h, mat, layer='detail', rt=None):
    return add(dict(id=i, type='primitive', shape='cylinder', position=[x,y,z],
        radiusBottom=r, radiusTop=r if rt is None else rt, height=h,
        segments=20, material=mat), layer)

def sphere(i, x, y, z, r, mat, scale=(1,1,1)):
    return add(dict(id=i, type='primitive', shape='sphere', position=[x,y,z],
        radius=r, segments=16, heightSegments=12, scale=list(scale), material=mat), 'landscape')

def slab(i, x0, z0, x1, z1, top, t, mat, layer='floor'):
    return add(dict(id=i, type='floor', **{'from':[x0,top-t,z0]}, to=[x1,top-t,z1],
                    thickness=t, material=mat), layer)

def wall(i, ax, az, bx, bz, f, top, mat='plaster', t=.26, layer='walls_l1'):
    return add(dict(id=i, type='wall', **{'from':[ax,f,az]}, to=[bx,top,bz],
                    thickness=t, material=mat), layer)

def rod(i, p, q, w, h, mat, layer='detail'):
    dx,dy,dz = [q[k]-p[k] for k in range(3)]
    length = math.sqrt(dx*dx+dy*dy+dz*dz)
    assert length>.001
    rx = math.atan2(-dy,dz) if math.hypot(dy,dz)>1e-9 else 0
    ry = math.asin(max(-1,min(1,dx/length)))
    return box(i,*[(p[k]+q[k])/2 for k in range(3)],w,h,length,mat,layer,[rx,ry,0])

def furnished(i, kind, x, f, z, w, d, h, mat, rot=0, level=1):
    return add(dict(id=i,type='furniture',subtype=kind,position=[x,f,z],
        dimensions=dict(width=w,depth=d,height=h),rotation=[0,rot,0],material=mat),f'furniture_l{level}')

def guard(i, path, h=1.10, glass=False, layer='components_l2'):
    row=dict(id=i,type='railing',path=path,height=h,postSpacing=1.0,postRadius=.02,
             railRadius=.025,railLevels=[.10,1],material='bronze')
    if glass: row.update(infillType='glass',infillThickness=.014,infillTopRatio=.93,infillMaterial='glass')
    return add(row,layer)

def opening(i, kind, host, cx, cz, bottom, w, h, level=1, vm=1, glass=False, slide=False, trim=True):
    wallrow=next(e for e in E if e['id']==host)
    ax,_,az=wallrow['from']; bx,_,bz=wallrow['to']
    length=math.hypot(bx-ax,bz-az); ux,uz=(bx-ax)/length,(bz-az)/length
    start=(cx-ax)*ux+(cz-az)*uz-w/2
    assert start>=-.0001 and start+w<=length+.0001,(i,start,w,length)
    row=dict(id=i,type=kind,parentWall=host,**{'from':[round(start,6),bottom,0]},width=w,height=h,
             frameWidth=.055,frameDepth=wallrow['thickness'],frameMaterial='frame')
    if kind=='window':
        row.update(glassDepth=.012,verticalMullions=vm,horizontalMullions=0,
                   mullionWidth=.028,glassMaterial='glass')
        if slide: row['interaction']=dict(mode='slide',openDistance=w*.45,initiallyOpen=False)
    else:
        row.update(leafDepth=.038,leafMaterial='glass' if glass else 'walnut',
                   doorStyle='double' if w>1.5 else 'single',leafRows=2,
                   interaction=dict(mode='swing',hingeSide='left',openAngle=85,initiallyOpen=False))
    add(row,f'components_l{level}')
    if not trim: return i
    # 所有外墙按内部在左侧布置，因此实际外法向为右法向。
    ex,ez=uz,-ux
    offset=wallrow['thickness']/2+.05-.02
    xx,zz=cx+ex*offset,cz+ez*offset
    layer=f'facade_l{level}'
    trimwidth=.10
    for suffix,sign in [('a',-1),('b',1)]:
        pos=[xx+ux*sign*(w/2+trimwidth/2),bottom+h/2,zz+uz*sign*(w/2+trimwidth/2)]
        rod(i+'_trim_'+suffix,[pos[0],bottom,pos[2]],[pos[0],bottom+h,pos[2]],
            .10,.10,'limestone',layer)
    rod(i+'_lintel',[xx-ux*(w/2+.10),bottom+h+.05,zz-uz*(w/2+.10)],
        [xx+ux*(w/2+.10),bottom+h+.05,zz+uz*(w/2+.10)],.10,.10,'limestone',layer)
    if kind=='window':
        # 窗台宽沿墙、厚沿 Y；底与窗底不同，顶恰为窗底。
        rod(i+'_sill',[cx+ex*.17-ux*(w/2+.15),bottom-.055,cz+ez*.17-uz*(w/2+.15)],
            [cx+ex*.17+ux*(w/2+.15),bottom-.055,cz+ez*.17+uz*(w/2+.15)],
            .26,.11,'limestone',layer)
    return i

def lamp(i, x, y, z, level, wallmounted=False):
    body=[dict(shape='box',position=[x,y,z],dimensions=[.12,.27,.12],material='warm_glow',interactive=True),
          dict(shape='box',position=[x,y+.16,z],dimensions=[.18,.045,.18],material='bronze')]
    add(dict(id=i,type='light',position=[x,y,z],lightType='point',color=[1,.82,.58],
        lowIntensity=2,highIntensity=8,distance=3.8,initiallyOn=True,body=body),f'lighting_l{level}')

def planter(i, x, top, z, w, d, tree=False):
    box(i+'_shell',x,top+.22,z,w,.44,d,'limestone','landscape')
    box(i+'_soil',x,top+.445,z,w-.10,.012,d-.10,'soil','landscape')
    if tree:
        cylinder(i+'_trunk',x,top+1.22,z,.065,1.56,'bark','landscape',.04)
        for j,(dx,dy,dz,r) in enumerate([(-.35,1.8,0,.68),(.35,2.0,.12,.66),(0,2.5,0,.55)]):
            sphere(i+f'_crown_{j}',x+dx,top+dy,z+dz,r,'leaf' if j%2 else 'leaf_light',(1,.67,1))
    else:
        n=max(1,round(w/.58))
        for j in range(n):
            sphere(i+f'_shrub_{j}',x-w/2+w*(j+.5)/n,top+.66,z,.33,'leaf',(1,.74,1))

def bed(i,x,f,z,w,level=2):
    layer=f'furniture_l{level}'
    box(i+'_frame',x,f+.18,z,w+.12,.36,2.18,'walnut',layer)
    box(i+'_mattress',x,f+.43,z,w,.18,2.10,'linen',layer)
    box(i+'_duvet',x,f+.55,z-.22,w-.02,.10,1.62,'sage',layer)
    box(i+'_runner',x,f+.61,z-.72,w,.025,.42,'clay',layer)
    box(i+'_headboard',x,f+.70,z+1.15,w+.30,1.08,.14,'walnut',layer)
    for j,dx in enumerate([-w*.25,w*.25]):
        box(i+f'_pillow_{j}',x+dx,f+.56,z+.70,w*.39,.16,.39,'linen',layer)
    for j,sign in enumerate([-1,1]):
        furnished(i+f'_nightstand_{j}','nightstand',x+sign*(w/2+.38),f,z+.72,.54,.48,.52,'walnut',level=level)

def bath(i,x,f,z,level):
    layer=f'furniture_l{level}'
    box(i+'_vanity',x,f+.42,z,.96,.84,.52,'walnut',layer)
    box(i+'_counter',x,f+.875,z,1.02,.07,.57,'limestone',layer)
    box(i+'_basin',x,f+.93,z,.56,.06,.35,'porcelain',layer)
    box(i+'_basin_inner',x,f+.965,z,.41,.012,.24,'stone_dark',layer)
    rod(i+'_tap_stem',[x+.29,f+.91,z+.08],[x+.29,f+1.12,z+.08],.025,.025,'bronze',layer)
    rod(i+'_tap_spout',[x+.29,f+1.12,z+.08],[x+.12,f+1.12,z+.08],.025,.025,'bronze',layer)
    box(i+'_mirror',x,f+1.55,z+.292,.91,1.02,.025,'mirror',layer)
    cylinder(i+'_toilet_base',x-.05,f+.20,z-.92,.21,.40,'porcelain',layer)
    box(i+'_toilet_tank',x-.05,f+.52,z-.65,.42,.55,.18,'porcelain',layer)
    cylinder(i+'_toilet_seat',x-.05,f+.425,z-.92,.24,.055,'porcelain',layer)

for i,rgb,rough,metal in [
    ('plaster',[.84,.82,.74],.86,0),('limestone',[.67,.64,.55],.82,0),
    ('stone_dark',[.30,.32,.30],.9,0),('wood',[.34,.20,.105],.65,0),
    ('walnut',[.24,.13,.069],.65,0),('frame',[.11,.16,.17],.40,.35),
    ('bronze',[.48,.34,.17],.43,.55),('roof',[.20,.25,.25],.95,0),
    ('flooring',[.68,.62,.50],.84,0),('linen',[.79,.75,.64],.95,0),
    ('sage',[.37,.48,.39],.94,0),('clay',[.54,.29,.18],.86,0),
    ('soil',[.25,.25,.18],.99,0),('leaf',[.17,.30,.12],.95,0),
    ('leaf_light',[.28,.39,.17],.95,0),('bark',[.25,.17,.10],.93,0),
    ('porcelain',[.87,.86,.80],.32,0),('screen',[.045,.10,.12],.25,.05),
    ('mirror',[.57,.64,.64],.08,.95),('lawn',[.29,.37,.20],.98,0),
    ('paving',[.60,.59,.51],.94,0),('gravel',[.53,.52,.45],.96,0)]:
    material(i,rgb,rough,metal)
material('glass',[.70,.84,.86],.08,materialClass='glass',transmission=.85,ior=1.5,thickness=.014,side='double')
material('warm_glow',[1,.84,.53],.8,emissive=[1,.64,.29],emissiveIntensity=.45)

# 场地与入口，饰面不覆盖同位置结构板。
slab('site',-3.0,-4.6,18.5,15.0,.015,.12,'lawn','site')
slab('entry_court',-.4,-.8,5.87,2.87,.04,.025,'paving','site')
slab('entry_walk',2.6,-4.6,5.5,-.8,.04,.025,'paving','site')
slab('side_walk',16.15,-1.3,17.35,12.4,.04,.025,'paving','site')
for k in range(4):
    box(f'entry_joint_{k}',1.05+k*1.4,.044,1.0,.012,.007,3.55,'stone_dark','site')
slab('plinth_main',-.13,2.87,10.93,12.13,.34,.30,'flooring')
slab('plinth_wing',5.87,-1.13,16.13,2.87,.34,.30,'flooring')
slab('plinth_wing_return',10.93,2.87,16.13,3.13,.34,.30,'flooring')
slab('entrance_landing',2.75,1.5,5.55,2.87,.34,.30,'limestone','entry')
add(dict(id='entrance_steps',type='stair',**{'from':[4.15,.04,.60]},to=[4.15,.34,1.50],
    width=2.6,stepCount=2,stepHeight=.15,stepDepth=.45,material='limestone'),'entry')

# 一层外墙：单一 L 形外轮廓，无重复共享墙。
outline=[(0,3),(6,3),(6,-1),(16,-1),(16,3),(10.8,3),(10.8,12),(0,12)]
names=['entry','court','living_s','living_e','living_n','main_e','main_n','main_w']
for k,name in enumerate(names):
    p,q=outline[k],outline[(k+1)%len(outline)]
    wall('l1_wall_'+name,*p,*q,.34,3.50,'limestone' if name in {'court','living_e'} else 'plaster')

# 一层西侧书房/楼梯及后部卫浴。
wall('l1_wall_spine',4,3,4,12,.34,3.50,t=.16)
wall('l1_wall_study_back',0,5.1,4,5.1,.34,3.50,t=.16)
wall('l1_wall_bath_s',4,9.4,6.6,9.4,.34,3.50,t=.16)
wall('l1_wall_bath_e',6.6,9.4,6.6,12,.34,3.50,t=.16)
opening('l1_door_entry','door','l1_wall_entry',4.15,3,.34,1.65,2.65)
opening('l1_window_study','window','l1_wall_entry',1.55,3,1.05,1.9,1.8,vm=2)
opening('l1_door_court','door','l1_wall_court',6,1,.34,2.6,2.72,glass=True)
opening('l1_window_living','window','l1_wall_living_s',9.0,-1,.58,4.6,2.62,vm=3)
opening('l1_door_garden','door','l1_wall_living_s',13.6,-1,.34,2.8,2.86,glass=True)
opening('l1_window_east_living','window','l1_wall_living_e',16,1,.70,2.8,2.45,vm=2)
opening('l1_window_living_n','window','l1_wall_living_n',13.6,3,1.10,3.5,1.80,vm=2)
opening('l1_window_dining','window','l1_wall_main_e',10.8,5.8,.92,3.2,2.12,vm=2)
opening('l1_window_kitchen_e','window','l1_wall_main_e',10.8,10.2,1.44,2.45,1.55,vm=1)
opening('l1_window_kitchen_n','window','l1_wall_main_n',8.7,12,1.44,2.65,1.55,vm=2)
opening('l1_window_bath','window','l1_wall_main_n',5.3,12,2.1,1.30,.9,vm=1)
opening('l1_window_stair_n','window','l1_wall_main_n',2.0,12,1.40,2.25,1.60,vm=1)
opening('l1_window_stair_w','window','l1_wall_main_w',0,8.9,1.3,2.1,1.65,vm=1)
opening('l1_window_study_w','window','l1_wall_main_w',0,4.15,1.0,1.40,1.9,vm=1)
opening('l1_door_study','door','l1_wall_spine',4,4.15,.34,.85,2.30,trim=False)
opening('l1_door_stair','door','l1_wall_spine',4,5.92,.34,1.10,2.35,trim=False)
opening('l1_door_bath','door','l1_wall_bath_s',5.25,9.4,.34,.85,2.25,trim=False)

# 实际梯段及半层平台。
for suffix,x,z0,z1,y0,y1 in [('a',1.25,6.8,9.6,.34,2.04),('b',2.85,9.6,6.8,2.04,3.74)]:
    add(dict(id='stair_'+suffix,type='stair',**{'from':[x,y0,z0]},to=[x,y1,z1],width=1.3,
        stepCount=10,stepHeight=.17,stepDepth=.28,material='limestone'),'stairs')
slab('stair_mid',.6,9.6,3.5,11.1,2.04,.18,'limestone','stairs')
guard('stair_guard_a',[[1.93,.51,6.94],[1.93,2.04,9.6]],1.0,layer='stairs')
guard('stair_guard_b',[[2.17,2.21,9.46],[2.17,3.74,6.8]],1.0,layer='stairs')
guard('stair_mid_guard',[[.6,2.04,11.1],[3.5,2.04,11.1]],1.0,layer='stairs')

# 二层地板，四片扣除整段梯井，露台与主楼板片相接。
for i,r in enumerate([(-.13,.45,2.87,12.13),(3.55,10.93,2.87,12.13),
                      (.45,3.55,2.87,6.8),(.45,3.55,11.1,12.13)]):
    slab(f'l2_slab_{i}',r[0],r[2],r[1],r[3],3.74,.24,'flooring','floor_l2')
slab('terrace_slab',5.87,-1.13,16.13,2.87,3.74,.24,'roof','floor_l2')
slab('terrace_slab_return',10.93,2.87,16.13,3.13,3.74,.24,'roof','floor_l2')
for side,coords in [('s',(0,3,10.8,3)),('e',(10.8,3,10.8,12)),
                    ('n',(10.8,12,0,12)),('w',(0,12,0,3))]:
    wall('l2_wall_'+side,*coords,3.74,6.92,layer='walls_l2')
for name,coords in [('spine',(4,3,4,12)),('reading_back',(0,5.1,4,5.1)),
    ('master_w',(6.5,3,6.5,8.1)),('bed_w',(6.5,8.1,6.5,12)),
    ('bed_divider',(6.5,8.1,10.8,8.1)),('bath_s',(4,9.4,6.5,9.4))]:
    wall('l2_wall_'+name,*coords,3.74,6.92,t=.16,layer='walls_l2')
opening('l2_window_reading','window','l2_wall_s',2.0,3,4.24,2.85,2.20,2,vm=2)
opening('l2_door_terrace','door','l2_wall_s',8.5,3,3.74,2.1,2.65,2,glass=True)
opening('l2_window_master','window','l2_wall_e',10.8,5.5,4.40,3.3,2.15,2,vm=2,slide=True)
opening('l2_window_bed','window','l2_wall_e',10.8,10.05,4.6,2.65,1.90,2,vm=2)
opening('l2_window_bed_n','window','l2_wall_n',8.6,12,4.6,2.75,1.90,2,vm=2)
opening('l2_window_bath','window','l2_wall_n',5.3,12,5.40,1.25,.90,2,vm=1)
opening('l2_window_stair_n','window','l2_wall_n',2.1,12,4.70,2.4,1.65,2,vm=1)
opening('l2_window_stair_w','window','l2_wall_w',0,9,4.70,2.2,1.65,2,vm=1)
opening('l2_window_reading_w','window','l2_wall_w',0,4.15,4.45,1.35,1.9,2,vm=1)
for i,host,x,z,w in [('reading','spine',4,4.12,.9),('stairs','spine',4,5.92,1.1),
                      ('master','master_w',6.5,5.0,.95),('bed','bed_w',6.5,8.86,.9),
                      ('bath','bath_s',5.25,9.4,.85)]:
    opening('l2_door_'+i,'door','l2_wall_'+host,x,z,3.74,w,2.30,2,trim=False)
guard('l2_void_guard',[[.45,3.74,6.8],[.45,3.74,11.1],[3.55,3.74,11.1],[3.55,3.74,6.8]])

# 层间、勒脚、墙面木格与入口棚。
for k,(p,q) in enumerate(zip(outline,outline[1:]+outline[:1])):
    dx,dz=q[0]-p[0],q[1]-p[1]; length=math.hypot(dx,dz); ex,ez=dz/length,-dx/length
    for name,y,h,d,mat in [('base',.45,.20,.10,'stone_dark'),('belt',3.62,.20,.12,'limestone')]:
        off=.13+d/2-.015
        rod(f'l1_{name}_{k}',[p[0]+ex*off,y,p[1]+ez*off],
            [q[0]+ex*off,y,q[1]+ez*off],d,h,mat,'facade_l1')
box('entry_canopy',4.15,3.19,2.26,3.15,.14,1.65,'frame','facade_l1')
for k in range(9):
    box(f'entry_soffit_{k}',2.75+k*.35,3.09,2.26,.16,.045,1.5,'wood','facade_l1')
for k in range(8):
    box(f'entry_accent_slat_{k}',5.24+k*.085,1.66,2.82,.036,2.30,.075,'wood','facade_l1')
# 阅读窗外木格：明示支框和有节奏的竖片，不封门口。
for k in range(10):
    box(f'l2_reading_screen_{k}',.61+k*.305,5.28,2.66,.042,2.17,.09,'wood','facade_l2')
for name,y in [('bottom',4.18),('top',6.38)]:
    box('l2_reading_screen_'+name,2.0,y,2.68,3.0,.06,.12,'bronze','facade_l2')

# 主屋面、檐下木色、四面女儿墙及压顶。
add(dict(id='main_roof',type='roof',roofType='flat',position=[5.4,6.92,7.5],
    span=11.5,depth=9.7,height=.22,thickness=.22,material='roof'),'roof')
for name,x,z,w,d in [('s',5.4,2.78,11.35,.13),('n',5.4,12.22,11.35,.13),
                    ('w',-.21,7.5,.13,9.31),('e',11.01,7.5,.13,9.31)]:
    box('parapet_'+name,x,7.44,z,w,.60,d,'plaster','roof_detail')
    box('coping_'+name,x,7.78,z,w+.05,.08,d+.06,'bronze','roof_detail')
for side,x,z,w,d in [('s',5.4,2.63,11.60,.09),('n',5.4,12.37,11.60,.09),
                    ('w',-.37,7.5,.09,9.65),('e',11.17,7.5,.09,9.65)]:
    box('roof_fascia_'+side,x,6.99,z,w,.18,d,'limestone','roof_detail')
    box('roof_soffit_'+side,x,6.925,z,w,.035,d+.11,'wood','roof_detail')

# 翼部露台、防护和格棚，铺装在结构板顶之上。
for k in range(18):
    box(f'terrace_deck_{k}',6.11+k*.55,3.756,.95,.536,.032,3.82,'wood','terrace')
guard('terrace_guard',[[6.0,3.74,3],[5.99,3.74,-1.02],[16.02,3.74,-1.02],
    [16.02,3.74,3.02],[10.8,3.74,3.02]],1.12,True)
for k,(x,z) in enumerate([(12,-.7),(15.7,-.7),(12,2.55),(15.7,2.55)]):
    box(f'pergola_post_{k}',x,5.036,z,.09,2.56,.09,'bronze','terrace')
for k,z in enumerate([-.7,2.55]):
    box(f'pergola_tie_{k}',13.85,6.33,z,3.95,.12,.12,'wood','terrace')
for k in range(10):
    box(f'pergola_blade_{k}',12+k*.41,6.44,.925,.055,.10,3.55,'wood','terrace')
furnished('terrace_table','table',13.85,3.772,.90,1.4,.75,.72,'wood',level=2)
for k,(x,angle) in enumerate([(12.65,math.pi/2),(15.05,-math.pi/2)]):
    furnished(f'terrace_chair_{k}','chair',x,3.772,.90,.55,.55,.95,'sage',angle,2)
planter('terrace_herbs',11.0,3.772,-.55,1.05,.65)
planter('terrace_tree',15.35,3.772,2.5,.85,.85,True)

# 一层家具：起居翼、餐厅、书房和厨房。
box('l1_living_rug',9.15,.355,1.0,4.45,.03,2.65,'linen','furniture_l1')
furnished('l1_sofa','sofa',9.05,.37,1.99,3.2,.86,.88,'sage',math.pi)
furnished('l1_coffee_table','table',9.05,.37,.65,1.6,.70,.42,'walnut')
furnished('l1_lounge_chair','chair',11.10,.34,1.1,.72,.74,.9,'linen',-math.pi/2)
box('l1_tv_base',9.02,.57,-.69,2.55,.46,.34,'walnut','furniture_l1')
box('l1_tv_screen',9.02,1.22,-.69,1.5,.78,.045,'screen','furniture_l1')
furnished('l1_dining_table','table',8.65,.34,5.55,2.2,1.12,.76,'walnut')
for k,x in enumerate([7.95,9.35]):
    for side,z in [('s',4.55),('n',6.55)]:
        furnished(f'l1_dining_chair_{k}_{side}','chair',x,.34,z,.50,.50,.9,'linen',0 if side=='s' else math.pi)
box('l1_dining_sideboard',7.35,.78,7.45,1.35,.88,.45,'walnut','furniture_l1')
furnished('l1_study_desk','table',1.75,.34,4.48,2.30,.65,.74,'walnut')
furnished('l1_study_chair','chair',1.75,.34,3.70,.52,.52,.88,'sage')
box('l1_study_laptop',1.75,1.24,4.48,.58,.34,.035,'screen','furniture_l1')
furnished('l1_study_shelf','bookshelf',.48,.34,3.65,.62,.35,1.65,'walnut')
box('l1_kitchen_base_n',8.77,.78,11.54,3.6,.88,.65,'walnut','furniture_l1')
box('l1_kitchen_counter_n',8.77,1.25,11.54,3.72,.06,.73,'limestone','furniture_l1')
box('l1_kitchen_base_e',10.32,.78,10.03,.65,.88,2.28,'walnut','furniture_l1')
box('l1_kitchen_counter_e',10.32,1.25,10.03,.73,.06,2.30,'limestone','furniture_l1')
box('l1_kitchen_island',8.10,.78,9.10,1.9,.88,.78,'walnut','furniture_l1')
box('l1_kitchen_island_top',8.10,1.26,9.10,2.02,.08,.90,'limestone','furniture_l1')
box('l1_sink_rim',8.45,1.294,11.53,.72,.025,.46,'frame','furniture_l1')
box('l1_sink_inner',8.45,1.31,11.53,.56,.015,.32,'stone_dark','furniture_l1')
rod('l1_sink_tap',[8.87,1.28,11.63],[8.87,1.62,11.63],.025,.025,'bronze','furniture_l1')
rod('l1_sink_tap_top',[8.87,1.62,11.63],[8.57,1.62,11.63],.025,.025,'bronze','furniture_l1')
box('l1_hob',10.32,1.296,10.0,.54,.025,.74,'frame','furniture_l1')
for k,z in enumerate([9.82,10.18]):
    cylinder(f'l1_burner_{k}',10.32,1.32,z,.14,.014,'stone_dark','furniture_l1')
for k in range(6):
    box(f'l1_cabinet_joint_{k}',7.1+k*.58,.78,11.205,.012,.82,.014,'stone_dark','furniture_l1')
bath('l1_bath',5.35,.34,11.47,1)

# 上层阅读、卧室、衣柜、卫浴。
furnished('l2_reading_sofa','sofa',1.85,3.74,4.54,2.45,.70,.84,'sage',math.pi,2)
furnished('l2_reading_table','table',1.85,3.74,3.55,1.05,.48,.42,'walnut',level=2)
bed('l2_master_bed',8.65,3.74,6.33,1.8)
furnished('l2_master_wardrobe','wardrobe',6.95,3.74,3.80,.60,1.10,2.3,'walnut',level=2)
bed('l2_bedroom_bed',8.65,3.74,10.45,1.5)
furnished('l2_bedroom_wardrobe','wardrobe',6.95,3.74,10.8,.60,1.65,2.2,'walnut',level=2)
bath('l2_bath',5.35,3.74,11.46,2)
box('l2_shower_base',4.7,3.79,10.08,1.08,.10,1.1,'limestone','furniture_l2')
box('l2_shower_screen',4.16,4.89,10.08,.014,2.10,1.08,'glass','furniture_l2')

# 有限数量的真实灯具与室内悬挂细部。
lamp('entry_lantern_a',3.12,2.22,2.76,1)
lamp('entry_lantern_b',5.26,2.22,2.76,1)
for k,x in enumerate([8.0,9.3]):
    rod(f'dining_light_stem_{k}',[x,3.45,5.55],[x,2.72,5.55],.014,.014,'bronze','lighting_l1')
    lamp(f'dining_light_{k}',x,2.55,5.55,1)
lamp('reading_light',3.52,5.85,4.62,2)
for k,x in enumerate([-.9,17.15]):
    box(f'garden_bollard_{k}',x,.52,.4,.14,.96,.14,'frame','landscape')
    box(f'garden_bollard_lens_{k}',x,.88,.32,.11,.13,.025,'warm_glow','landscape')

# 入口庭院和起居翼外的平面接续、园景。
slab('garden_living_landing',11.95,-2.15,15.25,-1.13,.34,.30,'limestone','entry')
add(dict(id='garden_steps',type='stair',**{'from':[13.6,.04,-3.05]},to=[13.6,.34,-2.15],
    width=2.4,stepCount=2,stepHeight=.15,stepDepth=.45,material='limestone'),'entry')
slab('garden_walk',11.8,-4.6,15.4,-3.05,.04,.025,'paving','site')
planter('garden_entry_tree',-.95,.015,1.20,1.25,1.25,True)
planter('garden_corner_tree',17.15,.015,8.6,1.1,1.1,True)
planter('garden_north_tree',3.2,.015,13.85,1.1,1.1,True)
planter('garden_front_hedge',8.8,.015,-3.25,4.8,.65)
planter('garden_side_hedge',17.2,.015,3.3,.8,2.1)
for k in range(8):
    slab(f'garden_stepping_{k}',-.95,4.0+k*.94,-.15,4.64+k*.94,.045,.03,'paving','site')
box('court_bench_top',.95,.53,1.02,1.85,.10,.44,'wood','landscape')
for k,x in enumerate([.30,1.60]):
    box(f'court_bench_leg_{k}',x,.28,1.02,.14,.40,.35,'frame','landscape')

# 交付、每轮输入与脚本快照。禁止把时间写入 WILD，保证完全重放。
bp=dict(meta=dict(version='1.1',type='building',name='栖光别墅 · 叠院露台住宅',
    author='Codex · 单文档生成',style='现代石木住宅'),geometry=dict(elements=E,components=C),
    materials=M,editor=dict(revision=1))
def rounded(v):
    if isinstance(v,float): return round(v,6)
    if isinstance(v,list): return [rounded(x) for x in v]
    if isinstance(v,dict): return {k:rounded(x) for k,x in v.items()}
    return v
bp=rounded(bp)
raw=(json.dumps(bp,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8')
for directory in ['03-过程记录','04-校验','05-效果图','06-剖切查看']:
    (BASE/directory).mkdir(parents=True,exist_ok=True)
snapshot=BASE/'03-过程记录'/args.revision
snapshot.mkdir(parents=True,exist_ok=False)
(BASE/'栖光别墅-单文档生成.wild').write_bytes(raw)
(snapshot/'栖光别墅.wild').write_bytes(raw)
shutil.copyfile(__file__,snapshot/'生成脚本.py')
(BASE/'03-过程记录/构件分层.json').write_text(json.dumps(LAYERS,ensure_ascii=False,indent=2),encoding='utf-8')
summary=dict(revision=args.revision,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),
    elements=len(E),components=len(C),materials=len(M),layers=dict(Counter(LAYERS.values())),
    author_source=str(RULE.relative_to(ROOT)),rule_sha256=hashlib.sha256(RULE.read_bytes()).hexdigest(),
    rule_version='1.2',other_building_sources_used=False)
(snapshot/'生成摘要.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
