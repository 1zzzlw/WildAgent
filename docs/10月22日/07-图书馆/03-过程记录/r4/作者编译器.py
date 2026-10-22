"""读取已保存的设计文件，确定性装配完整 WILD。方案与装配均在本目录可复查。"""
import hashlib
import importlib.util
import json
import math
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'wild-server'))
from app.design.contracts import DesignDocument

spec = importlib.util.spec_from_file_location('parts', HERE/'构件作者工具.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
design_path = Path(sys.argv[1]).resolve()
raw = design_path.read_bytes()
doc = DesignDocument.model_validate_json(raw)
p = doc.decisions.model_extra['authoring']
base = design_path.parents[1]
F = .4
H = p['height']

for name, rgb in {
    'limestone':[.72,.69,.60], 'plaster':[.86,.84,.77], 'concrete':[.51,.53,.51],
    'dark_wood':[.09,.12,.11], 'walnut':[.33,.20,.11], 'oak':[.57,.39,.22],
    'bronze':[.27,.23,.16], 'clay':[.53,.25,.16], 'green':[.12,.25,.20],
    'linen':[.85,.79,.64], 'sage_fabric':[.34,.43,.32], 'soil':[.15,.11,.07],
    'grass':[.28,.37,.22], 'leaf':[.17,.28,.14], 'leaf_light':[.33,.42,.21], 'bark':[.24,.16,.10],
    'black':[.025,.035,.034], 'porcelain':[.89,.87,.79], 'red':[.61,.17,.11],
    'yellow':[.83,.60,.18], 'blue':[.17,.32,.40], 'tile':[.55,.61,.58],
}.items():
    a.material(name, rgb, .38 if name=='porcelain' else .84,
               .6 if name=='bronze' else .15 if name=='dark_wood' else 0)
a.material('glass', [.86,.93,.92], .08, materialClass='glass', transmission=.84, ior=1.5, thickness=.014, side='double')
a.material('water', [.23,.56,.52], .055, materialClass='glass', transmission=.95, ior=1.333,
           thickness=.35, attenuationDistance=4, side='front')
a.material('warm_glow', [1,.78,.44], .35, emissive=[1,.63,.25], emissiveIntensity=1.5)

def box(*args, **kwargs):
    return a.box(*args, **kwargs)

def row(i):
    return next(e for e in a.E+a.C if e['id']==i)

def sign(i, text, x, y, z, w, h, mat='green'):
    box(i, x,y,z,w,h,.14,mat,'signage',[0,math.pi,0])
    row(i)['label'] = dict(text=text, color=[.96,.86,.62], fontFamily='serif' if p['kind'] in ['library','villa'] else 'sans-serif')
    for dx in [-w/2+.04,w/2-.04]:
        box(i+('_l' if dx<0 else '_r'), x+dx,y,z-.078,.025,h-.06,.025,'bronze','signage')

def lamp(i,x,y,z,kind='bollard',power=4):
    if kind=='bollard':
        box(i+'_post',x,y+.52,z,.10,1.04,.10,'dark_wood','lighting')
        y += 1.04
        box(i+'_cap',x,y+.21,z,.29,.06,.29,'dark_wood','lighting')
    else:
        box(i+'_back',x,y,z+.04,.24,.38,.09,'dark_wood','lighting')
    box(i+'_glow',x,y,z,.16,.26,.16,'warm_glow','lighting')
    row(i+'_glow')['lightSource'] = dict(lightType='point', color=[1,.79,.51], intensity=power,
        distance=5, initiallyOn=True, offset=[0,-.12,-.11])

def planter(i,x,z,w=2,d=1,y=.08,h=.45):
    box(i+'_body',x,y+h/2,z,w,h,d,'concrete','landscape')
    box(i+'_soil',x,y+h+.006,z,w-.12,.024,d-.12,'soil','landscape')
    n=max(2,round(w/.45))
    for j in range(n):
        a.sphere(i+f'_plant{j}',x-w*.38+j*w*.76/(n-1),y+h+.22,z,.29,'leaf' if j%2 else 'leaf_light',[1,.8,.9])

def floor(i, bounds, y, mat='limestone', holes=(), layer='floor', thickness=.2):
    x0,z0,x1,z1=bounds
    xs=sorted({x0,x1,*[v for h in holes for v in (h[0],h[2])]})
    for j,(xa,xb) in enumerate(zip(xs,xs[1:])):
        blocked=sorted((h[1],h[3]) for h in holes if h[0]<(xa+xb)/2<h[2])
        start=z0
        for k,(za,zb) in enumerate(blocked+[(z1,z1)]):
            if za>start:
                if layer=='roof':
                    a.add(dict(type='roof',id=f'{i}_{j}_{k}',roofType='flat',span=xb-xa,depth=za-start,
                        height=thickness,thickness=thickness,position=[(xa+xb)/2,y,(start+za)/2],material=mat),layer)
                else:
                    a.slab(f'{i}_{j}_{k}',xa,start,xb,za,y,thickness,mat,layer)
            start=max(start,zb)

def shell(i,bounds,y,h,mat='plaster',layer='wall_ground'):
    x0,z0,x1,z1=bounds
    return {face:a.wall(i+'_'+face,*points,y,y+h,.24,mat,layer)
        for face,points in dict(front=(x0,z0,x1,z0),right=(x1,z0,x1,z1),back=(x1,z1,x0,z1),left=(x0,z1,x0,z0)).items()}

def win(i,host,start,y,w,h,vm=2):
    a.window(i,host,start,y,w,h,vm)

def door(i,host,start,y=F,w=1.5,h=2.65):
    a.door(i,host,start,y,w,h,True)

def cornice(i,b,y,mat='plaster'):
    x0,z0,x1,z1=b
    for key,x,z,w,d in [('f',(x0+x1)/2,z0,x1-x0+.6,.36),('b',(x0+x1)/2,z1,x1-x0+.6,.36),
                         ('l',x0,(z0+z1)/2,.36,z1-z0),('r',x1,(z0+z1)/2,.36,z1-z0)]:
        box(i+key,x,y,z,w,.22,d,mat,'roof_detail')
        box(i+key+'_edge',x,y-.13,z,w,.035,d+.025,'bronze','roof_detail')

def stairs(i,x,z,y,rise,run=4.4,width=1.35):
    # 两跑平行折返；上层楼板洞由同一 x/z/run/width 参数生成。
    mid=y+rise/2
    gap=.18
    n=14 if rise>4 else 12
    for suffix,cx,za,zb,ya,yb in [('a',x,z,z+run,y,mid),('b',x+width+gap,z+run,z,mid,y+rise)]:
        a.add(dict(type='stair',id=i+suffix,**{'from':[cx,ya,za]},to=[cx,yb,zb],width=width,
            stepCount=n,stepHeight=rise/(2*n),stepDepth=run/n,material='limestone'),'stair')
        a.guard(i+suffix+'_rail',[[cx-width/2,ya+.08,za],[cx-width/2,yb+.08,zb]],.95)
    a.slab(i+'_landing',x-width/2,z+run,x+width*1.5+gap,z+run+1.25,mid,.18,'limestone','stair')
    a.guard(i+'_landing_guard',[[x-width/2,mid,z+run+1.25],[x+width*1.5+gap,mid,z+run+1.25]],1.05)
    return [x-width/2-.08,z,x+width*1.5+gap+.08,z+run+1.33]

def books(i,x,z,y,w=2.4,levels=4,goods=False):
    box(i+'_back',x,y+1.1,z,w,2.2,.10,'oak','furniture')
    for side in [-1,1]:
        box(i+f'_side{side}',x+side*(w/2-.035),y+1.12,z-.15,.07,2.24,.45,'walnut','furniture')
    for k in range(levels+1):
        sy=y+.12+k*.5
        box(i+f'_shelf{k}',x,sy,z-.15,w,.055,.5,'oak','furniture')
        if k==levels:continue
        n=7 if goods else 11
        for j in range(n):
            bw=(w-.22)/n*.78
            bh=.22+(j%3)*.04 if goods else .28+(j%4)*.035
            box(i+f'_item{k}_{j}',x-w/2+.14+(j+.5)*(w-.28)/n,sy+.03+bh/2,z-.22,bw,bh,.20,
                ['clay','green','linen','blue','yellow'][((j//2)+k)%5],'furniture')

def seating(i,x,z,y=F,w=2.6,d=.95):
    a.table(i,x,z,w,d,y)
    for j,dx in enumerate([-.75,.75] if w>2 else [0]):
        for k,dz in enumerate([-1,1]):
            a.chair(i+f'_chair{j}_{k}',x+dx,z+dz*(d/2+.48),y,0 if dz>0 else math.pi)
    box(i+'_book',x+.22,y+.78,z,.35,.035,.26,'clay','furniture')

def canopy(i,x,z,w,d,y,mat='plaster'):
    box(i+'_slab',x,y,z,w,.20,d,mat,'canopy')
    box(i+'_fascia',x,y+.035,z-d/2,w,.27,.10,'dark_wood','canopy')
    for j,s in enumerate([-1,1]):
        box(i+f'_post{j}',x+s*(w/2-.45),(F+y)/2,z-d/2+.35,.13,y-F,.13,'bronze','canopy')
    for j in range(max(2,round(w/1.2))):
        xx=x-w/2+.6+j*1.2
        if xx<x+w/2-.3:
            box(i+f'_soffit{j}',xx,y-.115,z,.065,.04,d-.1,'oak','canopy')

def site():
    s=p['size']/2
    a.slab('site',-s,-s,s,s,.02,.22,'limestone','site')
    for x in [-s+1,s-1]:
        a.slab('lawn'+str(x),x-.7,-s+.6,x+.7,s-.6,.055,.04,'grass','landscape')
    for j in range(1,int(p['size']/2)):
        z=-s+j*2
        box('pave_joint'+str(j),0,.025,z,p['size']-3,.008,.018,'concrete','landscape')
    # 主入口三级踏步始终低于首层完成面，不挡住门扇。
    z0=p['bounds'][1]
    for j in range(3):
        a.slab('entry_step'+str(j),-3,z0-1.8+j*.5,3,z0+.05,.13+j*.135,.13,'limestone','site')

def library():
    b=p['bounds']; x0,z0,x1,z1=b
    atrium=[-2.8,-.5,2.8,6.3]
    sh=[-11.175,4.86,-8.135,10.59]
    floor('ground',b,F)
    floor('upper',b,F+H,'oak',[atrium,sh],'upper_floor',.24)
    floor('roof',[-12.3,-8.3,12.3,12.3],F+2*H,'concrete',[atrium],'roof',.24)
    for f in range(2):
        y=F+f*H
        s=shell(f'L{f+1}',b,y,H,'plaster','wall_ground' if f==0 else 'wall_upper')
        if f==0:
            door('main_entry',s['front'],10.5,y,3,2.85)
            win('front_left',s['front'],1,y+.35,7,2.65,3)
            win('front_right',s['front'],16,y+.35,7,2.65,3)
            door('rear_exit',s['back'],10.7,y,1.5)
        else:
            for j in range(4):win('upper_front'+str(j),s['front'],.7+j*5.8,y+.38,5.2,2.95,2)
        for face,length in [('right',20),('left',20),('back',24)]:
            for j in range(3 if length==20 else 4):
                start=.8+j*5.8
                if face=='back' and f==0 and j in [1,2]:continue
                win(f'window_{f}_{face}_{j}',s[face],start,y+.65,4.8,2.5,2)
        # 石材竖向接缝与水平腰线；窗口仍由宿主墙真实切洞。
        for j in range(9):
            xx=-12+j*3
            box(f'front_pier_{f}_{j}',xx,y+H/2,-8.17,.17,H,.13,'limestone','facade' if f==0 else 'upper_detail')
        cornice(f'band{f}',b,y+.12,'limestone')
        for side in [-1,1]:
            for j in range(19):
                box(f'terracotta_{f}_{side}_{j}',side*12.25,y+2.2,-7.4+j*1.02,.28,2.95,.10,'clay','facade' if f==0 else 'upper_detail')
        # 书架列留出中央阅览环廊与梯间。
        for j,(xx,zz) in enumerate([(-7,-1.8),(-7,1.4),(7,1.4),(7,5.5),(7,9.8),(-4.8,10)]):
            books(f'books_{f}_{j}',xx,zz,y,2.7)
        for j,(xx,zz) in enumerate([(-6,-5.3),(5.8,-5.3),(5.8,8),(-4.5,7.8)]):
            seating(f'reading_{f}_{j}',xx,zz,y)
        for j,(xx,zz) in enumerate([(-6,-3),(6,-3),(6,7),(-5,8)]):
            lamp(f'reading_lamp_{f}_{j}',xx,y+2.9,zz,'wall',22)
    actual=stairs('main_stair',-10.42,4.86,F,H)
    assert all(abs(x-y)<.02 for x,y in zip(actual,sh)),(actual,sh)
    for j,(pa,pb) in enumerate([([-2.8,F+H,-.5],[2.8,F+H,-.5]),([2.8,F+H,-.5],[2.8,F+H,6.3]),
        ([2.8,F+H,6.3],[-2.8,F+H,6.3]),([-2.8,F+H,6.3],[-2.8,F+H,-.5])]):
        a.guard('atrium_guard'+str(j),[pa,pb],1.08,True)
    a.guard('stair_void_guard',[[sh[0],F+H,sh[1]],[sh[0],F+H,sh[3]],[sh[2],F+H,sh[3]],[sh[2],F+H,sh[1]]],1.05)
    planter('atrium',0,2.8,4.4,5,F,.25);a.tree('courtyard_tree',0,3,F+.27,1.15)
    for j,(x,z) in enumerate([(-2.8,-.5),(2.8,-.5),(-2.8,6.3),(2.8,6.3)]):
        box('atrium_column'+str(j),x,F+H,z,.22,2*H,.22,'limestone','structure')
    for j,y in enumerate([F+H-.15,F+2*H-.15]):
        for k,z in enumerate([-.5,6.3]):
            box(f'atrium_beam_{j}_{k}',0,y,z,5.82,.30,.24,'concrete','structure' if j==0 else 'roof_detail')
        for k,x in enumerate([-2.8,2.8]):
            box(f'atrium_beam_side_{j}_{k}',x,y,2.9,.24,.30,7.04,'concrete','structure' if j==0 else 'roof_detail')
    # 屋面排水边与设备围屏保留高度层次，内庭上方保持开敞。
    for k,x in enumerate([-9.5,9.5]):
        box('roof_service'+str(k),x,9.40,9.5,2.8,.72,2.0,'concrete','roof_detail')
        for j in range(5):
            box(f'roof_screen_{k}_{j}',x,9.12+j*.16,8.43,3.1,.065,.07,'bronze','roof_detail')
    for k,z in enumerate([-8,12]):box('roof_coping'+str(k),0,9.20,z,24.5,.13,.28,'limestone','roof_detail')
    for k,x in enumerate([-12,12]):box('roof_coping_side'+str(k),x,9.20,2,.28,.13,20,'limestone','roof_detail')
    canopy('entry_portico',0,-9.3,10,3.4,3.65)
    sign('building_name',p['sign_text'],0,4.2,-8.35,7.8,.82)
    sign('sub_name','阅见世界 · READ & DISCOVER',-6.5,1.8,-14,5,.55,'dark_wood')
    box('monument_base',-6.5,.8,-13.9,5.4,1.6,.35,'limestone','signage')
    for side in [-1,1]:
        planter('entry_planter'+str(side),side*8,-11.6,4,1.8)
        a.tree('entry_tree'+str(side),side*12.9,-11,.08,1.2)
        lamp('entry_lamp'+str(side),side*5.5,.1,-12)
    cornice('roof_cap',b,F+2*H)

def villa():
    b=p['bounds']; upper=[-10,1,8,11]
    floor('ground',b,F,'oak')
    hole=[-8.88,3.86,-5.84,9.19]
    floor('upper',upper,F+H,'oak',[hole],'upper_floor',.24)
    floor('terrace',[-10,-3,10,1],F+H,'limestone',layer='upper_floor',thickness=.24)
    floor('side_terrace',[8,1,10,11],F+H,'limestone',layer='upper_floor',thickness=.24)
    floor('roof',[-10.3,.7,8.3,11.3],F+2*H,'concrete',layer='roof',thickness=.24)
    s=shell('L1',b,F,H)
    door('main_entry',s['front'],1,F,1.6)
    win('living_glass',s['front'],4,F+.15,8.5,2.85,4)
    win('dining_glass',s['front'],14,F+.15,5,2.85,2)
    for face,length in [('right',14),('left',14),('back',20)]:
        for j in range(2 if length==14 else 3):win('L1_'+face+str(j),s[face],1+j*5.9,F+.7,4.7,2.15,2)
    u=shell('L2',upper,F+H,H,'plaster','wall_upper')
    for j in range(3):win('bedroom_front'+str(j),u['front'],.8+j*5.7,F+H+.25,4.8,2.6,2)
    door('terrace_door',u['front'],6.7,F+H,1.4)
    # 门与第二扇窗不能重叠，移到相邻房间独立宿主。
    a.C.remove(row('bedroom_front1'));del a.LAYERS['bedroom_front1']
    win('bedroom_front1',u['front'],8.5,F+H+.25,2.8,2.6,1)
    for face in ['left','right','back']:
        length=18 if face=='back' else 10
        for j in range(2):win('L2_'+face+str(j),u[face],.8+j*(length/2),F+H+.8,length/2-1.6,2,1)
    actual=stairs('house_stair',-8.125,3.86,F,H,run=4)
    assert all(abs(x-y)<.02 for x,y in zip(actual,hole)),(actual,hole)
    a.guard('house_void_guard',[[hole[0],F+H,hole[1]],[hole[0],F+H,hole[3]],[hole[2],F+H,hole[3]],[hole[2],F+H,hole[1]]],1.05,True)
    # 上层卧室分隔门与浴室，使室内具有明确使用空间。
    host=a.wall('upper_partition',-4,1,-4,11,F+H,F+2*H,.14,'plaster','wall_upper')
    door('bedroom_access',host,1.1,F+H,1.0,2.4)
    host=a.wall('bath_partition',-4,7,8,7,F+H,F+2*H,.14,'plaster','wall_upper')
    door('bath_access',host,9.2,F+H,1,2.4)
    a.bed('master_bed',3,4.2,F+H,2.1);a.bed('guest_bed',-1.5,9,F+H,1.7)
    box('bathtub',5,F+H+.28,9,2.4,.56,1.15,'porcelain','furniture')
    box('bath_inner',5,F+H+.565,9,2.06,.025,.82,'tile','furniture')
    box('vanity',.5,F+H+.42,9.7,2.2,.84,.65,'oak','furniture')
    box('basin',.5,F+H+.88,9.7,.6,.12,.45,'porcelain','furniture')
    # 一层起居、餐厨及客卫。
    box('sofa_base',.4,F+.25,1.5,3.8,.5,1,'linen','furniture')
    box('sofa_back',.4,F+.67,1.92,3.8,.65,.18,'sage_fabric','furniture')
    for j in range(3):box('sofa_cushion'+str(j),-.8+j*1.2,F+.56,1.45,1.12,.18,.84,'linen','furniture')
    a.table('coffee_table',.4,-.3,2.1,1.0,F,.38)
    box('rug',.4,F+.015,.3,4.8,.025,3.6,'sage_fabric','furniture')
    seating('dining',5.7,4,F,3.2,1.1)
    for j in range(6):box('kitchen_unit'+str(j),-2+j*1.1,F+.44,9.8,1.06,.88,.68,'oak','furniture')
    box('countertop',.75,F+.92,9.8,6.7,.08,.76,'limestone','furniture')
    box('sink',-1,F+.967,9.8,.75,.014,.45,'black','furniture')
    box('hob',2,F+.969,9.8,.68,.018,.5,'black','furniture')
    box('fridge',6.7,F+1.0,9.8,1,2.0,.8,'dark_wood','furniture')
    host=a.wall('ground_wc',-5.3,7.8,-5.3,11,F,F+H,.14,'plaster')
    door('wc_door',host,.5,F,1,2.4)
    box('wc_seat',-6.4,F+.3,10,.42,.6,.65,'porcelain','furniture')
    for i,bounds,y in [('ground_band',b,F+H),('roof_band',upper,F+2*H)]:cornice(i,bounds,y)
    a.guard('front_balcony',[[-10,F+H,-3],[10,F+H,-3],[10,F+H,11],[8,F+H,11]],1.08,True)
    for j in range(15):box('wood_screen'+str(j),-9.75+j*.18,F+H+1.6,.83,.07,3.0,.18,'oak','upper_detail')
    canopy('entry',-8.1,-4.0,4.8,2.4,3.35)
    sign('building_name',p['sign_text'],-7.6,2.7,-3.34,4.3,.66,'dark_wood')
    # 泳池是下沉池底、池壁、透明薄水面，四圈围边不让水铺到岸上。
    pool=[-1,-12.3,10,-6.5]
    floor('pool_bottom',pool,-.15,'tile',thickness=.16)
    floor('pool_water',pool,.19,'water',thickness=.025,layer='water')
    for j in range(11):box('pool_joint'+str(j),-.5+j,.018,-9.4,.018,.008,5.7,'concrete','landscape')
    for i,x,z,w,d in [('f',4.5,-12.4,11.5,.22),('b',4.5,-6.4,11.5,.22),('l',-1.1,-9.4,.22,5.8),('r',10.1,-9.4,.22,5.8)]:
        box('pool_wall'+i,x,.02,z,w,.5,d,'limestone','landscape')
    for j in range(17):box('deck_board'+str(j),5.1,F-.12,-5.95+j*.16,10.8,.10,.13,'oak','landscape')
    for j in range(2):
        box('lounger'+str(j),12.2,F+.08,-8.4+j*2.5,1.05,.25,2.0,'linen','furniture')
        box('lounger_back'+str(j),12.2,F+.35,-7.8+j*2.5,1.05,.12,.8,'oak','furniture',[-.35,0,0])
    for j,(x,z) in enumerate([(-12,-9),(-12,10),(12,12)]):
        planter('garden'+str(j),x,z,2.5,2.4);a.tree('tree'+str(j),x,z,.6,1.15)
    for j,(x,z) in enumerate([(-5,-6),(11,-5),(-11,1),(9,10)]):lamp('garden_light'+str(j),x,F,z)
    for j,(x,z,y) in enumerate([(0,2,F),(5,6,F),(-2,4,F+H),(3,5,F+H)]):lamp('room_light'+str(j),x,y+2.8,z,'wall',5)

def cafe():
    b=p['bounds'];floor('ground',b,F,'oak')
    s=shell('shop',b,F,H,'plaster')
    door('entry',s['front'],4.8,F,1.5)
    win('front_showcase',s['front'],.5,F+.25,3.8,2.65,2)
    win('front_seating',s['front'],7,F+.25,4.1,2.65,2)
    for face in ['left','right']:win(face+'_glass',s[face],.6,F+.5,5.3,2.4,3)
    door('rear_exit',s['back'],9.5,F,1,2.5)
    floor('roof',[-6.15,-3.05,6.15,5.85],F+H,'concrete',layer='roof')
    cornice('cafe_cornice',b,F+H,'green')
    canopy('terrace_roof',0,-4.0,12.3,2.9,3.3,'green')
    sign('building_name',p['sign_text'],0,3.78,-3.04,5.1,.72)
    # 低饱和砖铺面：实体表层，窗洞内不横穿砖带。
    for side in [-1,1]:
        for r in range(6):
            for j in range(4):
                xx=side*(4.9+j*.21)
                box(f'brick_{side}_{r}_{j}',xx,F+.16+r*.22,-2.835,.19,.19,.027,'clay','facade')
    for j in range(7):box('bar_unit'+str(j),-2.4+j*.9,F+.49,3.4,.87,.98,.8,'green','furniture')
    box('bar_counter',.3,F+1.01,3.4,6.35,.08,.94,'limestone','furniture')
    box('espresso_machine',-.5,F+1.35,3.5,1.1,.6,.62,'dark_wood','furniture')
    box('espresso_panel',-.5,F+1.42,3.17,.88,.35,.025,'bronze','furniture')
    for j in range(2):
        box('coffee_group'+str(j),-.8+j*.6,F+1.18,3.12,.09,.2,.13,'bronze','furniture')
        a.sweep('coffee_spout'+str(j),[[-.8+j*.6,F+1.18,3.06],[-.8+j*.6,F+1.10,2.99]],.018,'bronze','furniture')
    box('pastry_case',2.1,F+1.28,3.4,1.5,.46,.70,'glass','furniture')
    for j in range(5):a.sphere('pastry'+str(j),1.55+j*.27,F+1.1,3.3,.10,'clay',[1,.5,.7])
    for j in range(6):
        a.add(dict(type='primitive',id='cup'+str(j),shape='cylinder',position=[-2.1+j*.2,F+1.12,3.3],radius=.055,height=.14,segments=16,material='porcelain'),'furniture')
    for j,(x,z) in enumerate([(-3.8,-.5),(3.7,-.5),(-3.8,1.6)]):seating('inside_table'+str(j),x,z,F,1.2,.65)
    for j,(x,z) in enumerate([(-3.6,-5.5),(3.6,-5.5)]):seating('outside_table'+str(j),x,z,.1,1.2,.65)
    host=a.wall('wc_partition',3.5,2.2,5.8,2.2,F,F+H,.14,'plaster')
    door('wc_entry',host,.7,F,.9,2.4)
    a.wall('wc_side',3.5,2.2,3.5,5.5,F,F+H,.14,'plaster')
    box('wc',4.8,F+.3,4.6,.45,.6,.65,'porcelain','furniture')
    sign('menu','COFFEE\n烘焙 · 手冲',-5.0,1.55,-6.5,1.1,1.3,'dark_wood')
    for dx in [-.42,.42]:box('menu_leg'+str(dx),-5+dx,.5,-6.45,.06,1,.12,'oak','signage')
    for j,(x,z) in enumerate([(-6.8,-5.3),(6.8,-5.3),(6.7,5.9)]):planter('plants'+str(j),x,z,1.2,1.2)
    a.tree('street_tree',-6.5,5.5,.1,.85)
    for j,x in enumerate([-4,0,4]):lamp('pendant'+str(j),x,2.8,.9,'wall',4)
    for j,x in enumerate([-5.4,5.4]):lamp('terrace_light'+str(j),x,2.7,-3.7,'wall',3)

def market():
    b=p['bounds'];floor('ground',b,F,'tile')
    s=shell('market',b,F,H,'plaster')
    door('entry',s['front'],5.15,F,2.7,2.85)
    win('front_left',s['front'],.55,F+.2,4,2.65,2)
    win('front_right',s['front'],8.45,F+.2,4,2.65,2)
    win('east_glass',s['right'],.7,F+.8,5.6,2,3)
    win('west_glass',s['left'],3,F+.8,5,2,3)
    door('loading_exit',s['back'],.8,F,1.4,2.65)
    floor('roof',[-6.85,-3.85,6.85,6.85],F+H,'concrete',layer='roof')
    cornice('market_band',b,F+H,'green')
    canopy('street_canopy',0,-4.4,13.8,2.6,3.5,'green')
    sign('building_name',p['sign_text'],0,3.99,-3.87,9.3,.76)
    sign('fresh_sign','每日鲜选 · FRESH MARKET',0,2.9,-5.75,5.6,.34,'dark_wood')
    for side in [-1,1]:
        for j in range(7):box(f'wall_base_{side}_{j}',side*6.65,.75,-3+j*1.4,.10,.7,1.36,'limestone','facade')
    # 三列双面货架。间距2.9米，货架宽1.7米，留1.2米净通道。
    for j,x in enumerate([-3.5,-.6,2.3]):
        for k,z in enumerate([.5,3.1]):
            books(f'aisle_{j}_{k}_a',x,z,F,1.7,3,True)
            books(f'aisle_{j}_{k}_b',x,z+.45,F,1.7,3,True)
    # 冷藏柜可见透明门、分层货物与暗色背衬。
    for j in range(3):
        x=-3+j*1.9
        box('fridge_back'+str(j),x,F+1.18,5.85,1.8,2.35,.65,'dark_wood','furniture')
        for k in range(4):
            box(f'cold_shelf{j}_{k}',x,F+.25+k*.48,5.43,1.67,.035,.47,'porcelain','furniture')
            for n in range(5):box(f'cold_goods{j}_{k}_{n}',x-.65+n*.32,F+.39+k*.48,5.4,.18,.23,.17,['green','yellow','linen'][n%3],'furniture')
        box('fridge_glass'+str(j),x,F+1.15,5.16,1.7,2.17,.025,'glass','furniture')
        box('fridge_handle'+str(j),x+.67,F+1.2,5.12,.025,.55,.025,'bronze','furniture')
    box('checkout',-4.1,F+.5,-1.65,2.8,1,.85,'oak','furniture')
    box('checkout_top',-4.1,F+1.02,-1.65,2.95,.06,.95,'dark_wood','furniture')
    box('pos_base',-3.3,F+1.13,-1.65,.28,.2,.2,'bronze','furniture')
    box('pos_screen',-3.3,F+1.36,-1.7,.43,.30,.06,'black','furniture',[.15,0,0])
    for j in range(3):
        x=3.7+j*.62
        box('produce_crate'+str(j),x,F+.47,-1.5,.58,.6,1.5,'oak','furniture')
        for k in range(12):a.sphere(f'produce_{j}_{k}',x+(k%3-1)*.15,F+.81,-2+(k//3)*.30,.085,['red','yellow','green'][j], [1,.85,1])
    for j,x in enumerate([-4,0,4]):lamp('ceiling_light'+str(j),x,3.6,2,'wall',6)
    for j,x in enumerate([-5.7,5.7]):lamp('entrance_light'+str(j),x,2.9,-4.4,'wall',4)
    for j,x in enumerate([-5.9,5.9]):planter('street_planter'+str(j),x,-6.7,2.2,.8)
    for j in range(3):
        x=5.1+j*.28
        box('cart_basket'+str(j),x,F+.65,3.7,.5,.4,.7,'bronze','furniture')
        for k,dz in enumerate([-.25,.25]):
            a.sweep(f'cart_frame{j}_{k}',[[x-.22,F+.12,3.7+dz],[x-.22,F+.9,3.7+dz],[x+.22,F+.9,3.7+dz]],.018,'dark_wood','furniture')

site()
{'library':library,'villa':villa,'cafe':cafe,'market':market}[p['kind']]()
bp=dict(meta=dict(version='1.1',type='building',name=p['name'],author='Codex',style=p['style'],
                  description=p['concept']+' 地块'+str(p['size'])+'×'+str(p['size'])+'米，招牌文字与真实灯源保存在WILD。'),
        geometry=dict(elements=a.E,components=a.C),materials=a.M,assets={})
target=base/(p['name']+'.wild')
revision=1+len(list((base/'03-过程记录').glob('r[0-9]*')))
snapshot=base/'03-过程记录'/f'r{revision}'
snapshot.mkdir(parents=True)
if target.exists():
    shutil.copyfile(target,snapshot/'修订前.wild')
target.write_text(json.dumps(bp,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
shutil.copyfile(target,snapshot/target.name)
shutil.copyfile(__file__,snapshot/'作者编译器.py')
shutil.copyfile(design_path,snapshot/'DesignDocument.json')
(base/'03-过程记录'/'构件分层.json').write_text(json.dumps(a.LAYERS,ensure_ascii=False,indent=2),encoding='utf-8')
record=dict(design_sha256=hashlib.sha256(raw).hexdigest(),wild_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            compiler=str(Path(__file__).relative_to(ROOT)), elements=len(a.E),components=len(a.C),
            signs=[dict(id=e['id'],text=e['label']['text']) for e in a.E if 'label' in e],
            real_lights=sum('lightSource' in e for e in a.E),method='DesignDocument -> deterministic author assembly -> WILD (not LangGraph)')
(base/'03-过程记录'/'编译记录.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
(base/'02-生成脚本'/'重建说明.md').write_text('读取 ../01-需求与设计/DesignDocument.json，运行公共脚本 编译命名建筑.py。\n\n公共脚本与构件作者工具均随仓库保存；设计参数与装配步骤可直接复查，不需要模型或Agent。\n',encoding='utf-8')
print(json.dumps(record,ensure_ascii=False,indent=2))
