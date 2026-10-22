"""独立图片复建作者：读取设计，装配几何并保留每轮输入、源码和WILD。"""
import hashlib
import importlib.util
import json
import math
import random
import shutil
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'wild-server'))
from app.design.contracts import DesignDocument
spec=importlib.util.spec_from_file_location('photo_parts',HERE/'构件作者工具.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
design_path=Path(sys.argv[1]).resolve();design_raw=design_path.read_bytes()
doc=DesignDocument.model_validate_json(design_raw);p=doc.decisions.model_extra['authoring']
BASE=design_path.parents[1];F=p['base'];H=p['height'];rng=random.Random(221122 if p['recipe']=='stone' else 221222)

for n,c in {
 'stone':[.77,.71,.60], 'plaster':[.87,.865,.82], 'concrete':[.56,.57,.53], 'paving':[.76,.76,.70],
 'oak':[.53,.36,.21], 'walnut':[.31,.18,.10], 'bronze':[.15,.12,.08], 'dark_wood':[.065,.06,.047],
 'black':[.022,.028,.025], 'linen':[.86,.80,.67], 'sage_fabric':[.39,.43,.32], 'soil':[.14,.115,.075],
 'grass':[.28,.36,.18], 'moss':[.35,.40,.20], 'leaf':[.16,.28,.105], 'leaf_light':[.32,.41,.16],
 'leaf_gold':[.44,.44,.19], 'bark':[.26,.19,.11], 'porcelain':[.92,.87,.73], 'clay':[.49,.22,.13],
 'blue':[.17,.29,.34], 'paper':[.80,.75,.61], 'coffee':[.06,.025,.012],
}.items():
    a.material(n,c,.40 if n in ['bronze','porcelain'] else .88,.6 if n=='bronze' else 0)
a.material('glass',[.94,.97,.94],.045,materialClass='glass',transmission=.96,ior=1.5,thickness=.012,side='double')
a.material('roof_glass',[.89,.95,.96],.07,materialClass='glass',transmission=.88,ior=1.5,thickness=.018,side='double')
a.material('warm_glow',[1,.80,.43],.40,emissive=[1,.66,.28],emissiveIntensity=1.2)

def box(*args,**kw):return a.box(*args,**kw)
def get(i):return next(e for e in a.E+a.C if e['id']==i)
def slab(i,b,y,mat='paving',t=.20,layer='floor_1'):
    return a.slab(i,*b,y,t,mat,layer)

def plate(i,b,y,holes=(),mat='oak',t=.22,layer='floor_2',roof=False):
    x0,z0,x1,z1=b
    xs=sorted({x0,x1,*[v for h in holes for v in (h[0],h[2])]})
    for j,(xa,xb) in enumerate(zip(xs,xs[1:])):
        start=z0;blocked=sorted((h[1],h[3]) for h in holes if h[0]<(xa+xb)/2<h[2])
        for k,(za,zb) in enumerate(blocked+[(z1,z1)]):
            if za>start+1e-8:
                if roof:
                    a.add(dict(type='roof',id=f'{i}_{j}_{k}',roofType='flat',span=xb-xa,depth=za-start,
                        position=[(xa+xb)/2,y,(start+za)/2],height=t,thickness=t,material=mat),layer)
                else:slab(f'{i}_{j}_{k}',[xa,start,xb,za],y,mat,t,layer)
            start=max(start,zb)

def walls(i,b,y,h,front='plaster',skip=(),layer='wall_1'):
    x0,z0,x1,z1=b
    faces=dict(front=(x0,z0,x1,z0),right=(x1,z0,x1,z1),back=(x1,z1,x0,z1),left=(x0,z1,x0,z0))
    return {k:a.wall(i+'_'+k,*v,y,y+h,.28,front if k=='front' else 'plaster',layer) for k,v in faces.items() if k not in skip}

def window(i,host,start,y,w,h,vm=0):
    a.window(i,host,start,y,w,h,vm)
    get(i).update(frameWidth=.038,frameDepth=.13,frameMaterial='bronze',glassDepth=.012,mullionWidth=.025)

def door(i,host,start,y,w=1.2,h=2.65,glass=True):
    a.door(i,host,start,y,w,h,glass)
    get(i).update(frameMaterial='bronze',frameDepth=.15,frameWidth=.045)

def rod(i,pa,pb,w,d,mat='bronze',layer='detail'):
    # box长轴沿局部Y，明确三维旋转；不依赖梁的自动吸附。
    dx,dy,dz=[pb[k]-pa[k] for k in range(3)];length=math.sqrt(dx*dx+dy*dy+dz*dz)
    assert length>.0001
    rotation=[math.atan2(dz,dy),0,-math.asin(max(-1,min(1,dx/length)))]
    box(i,*[(pa[k]+pb[k])/2 for k in range(3)],w,length,d,mat,layer,rotation)

def sign(i,text,x,y,z,w,h,mat='plaster',color=None,serif=True):
    box(i,x,y,z,w,h,.045,mat,'signage',[0,math.pi,0])
    get(i)['label']=dict(text=text,color=color or [.13,.09,.055],fontFamily='serif' if serif else 'sans-serif')

def foliage(i,x,y,z,r=.18,scale=None,mat=None,layer='planting'):
    a.add(dict(type='primitive',id=i,shape='sphere',position=[x,y,z],radius=r,segments=10,heightSegments=6,
        scale=scale or [1,.65,1],rotation=[rng.uniform(-.4,.4),rng.uniform(0,6.28),rng.uniform(-.3,.3)],
        material=mat or rng.choice(['leaf','leaf_light','moss'])) ,layer)

def plant(i,x,y,z,s=1,pot=True,layer='planting'):
    if pot:
        box(i+'_pot',x,y+.21*s,z,.55*s,.42*s,.55*s,'concrete',layer)
        box(i+'_soil',x,y+.424*s,z,.46*s,.024*s,.46*s,'soil',layer)
        y+=.43*s
    for j in range(13):
        t=j*2.399;length=s*(.30+rng.random()*.35)
        tip=[x+math.sin(t)*length*.65,y+length,z+math.cos(t)*length*.65]
        a.sweep(i+f'_stem{j}',[[x,y,z],tip],.009*s,'leaf',layer,5)
        foliage(i+f'_leaf{j}',*tip,.10*s,[.5,2.2,.65],layer=layer)

def tree(i,x,z,y=0,s=1,layer='landscape'):
    trunk=[[x,y,z],[x+.12*s,y+1.6*s,z+.03*s],[x-.10*s,y+3.3*s,z+.14*s],[x+.12*s,y+5*s,z]]
    a.sweep(i+'_trunk',trunk,.075*s,'bark',layer,10)
    for j in range(9):
        angle=j*2.399;reach=(.8+rng.random()*.65)*s;height=(3.5+rng.random()*1.8)*s
        tip=[x+math.sin(angle)*reach,y+height,z+math.cos(angle)*reach]
        a.sweep(i+f'_branch{j}',[[x,y+2.2*s,z],[(x+tip[0])/2,y+height*.8,(z+tip[2])/2],tip],.026*s,'bark',layer,6)
        for k in range(10):
            foliage(i+f'_crown{j}_{k}',tip[0]+rng.uniform(-.45,.45)*s,tip[1]+rng.uniform(-.18,.55)*s,
                tip[2]+rng.uniform(-.45,.45)*s,(.20+rng.random()*.15)*s,[1,.85,1.15],layer=layer)

def vine(i,x,y,z,length=2,axis='front',layer='planting'):
    points=[];n=max(6,round(length/.17))
    for j in range(n+1):
        t=j/n;xx=x+math.sin(t*7)*.07;zz=z+math.cos(t*6)*.045
        points.append([xx,y-length*t,zz])
        for k in range(3):
            foliage(f'{i}_leaf{j}_{k}',xx+(k-1)*.09,y-length*t+rng.uniform(-.04,.04),zz+(-.07 if axis=='front' else .03),
                .07,[1.1,.75,.55],layer=layer)
    a.sweep(i+'_stem',points,.009,'leaf',layer,5)

def light(i,x,y,z,power=16,pendant=False,layer='lighting_1'):
    if pendant:
        a.sweep(i+'_wire',[[x,y+.08,z],[x,y+.68,z]],.008,'bronze',layer,6)
        a.add(dict(type='primitive',id=i+'_shade',shape='cylinder',position=[x,y+.08,z],radiusTop=.07,radiusBottom=.26,height=.12,segments=24,material='bronze'),layer)
    else:box(i+'_back',x,y,z+.045,.15,.15,.08,'bronze',layer)
    a.add(dict(type='primitive',id=i+'_bulb',shape='sphere',position=[x,y-.025,z],radius=.065,segments=16,material='warm_glow',
        lightSource=dict(lightType='point',color=[1,.73,.40],intensity=power,distance=5,initiallyOn=True,offset=[0,-.04,-.06])),layer)

def chair(i,x,z,y=F,angle=0,layer='furniture_1'):
    first=len(a.E);a.chair(i,x,z,y,0)
    for e in a.E[first:]:
        a.LAYERS[e['id']]=layer
        dx=e['position'][0]-x;dz=e['position'][2]-z
        e['position'][0]=x+math.cos(angle)*dx+math.sin(angle)*dz
        e['position'][2]=z-math.sin(angle)*dx+math.cos(angle)*dz
        if angle:e['rotation']=[0,angle,0]

def table(i,x,z,y=F,w=1.5,d=.75,layer='furniture_1',round_top=False):
    if round_top:
        a.add(dict(type='primitive',id=i+'_top',shape='cylinder',position=[x,y+.74,z],radius=w/2,height=.065,segments=32,material='oak'),layer)
        box(i+'_base',x,y+.36,z,.11,.72,.11,'bronze',layer)
        box(i+'_foot',x,y+.04,z,.56,.06,.56,'bronze',layer)
    else:
        first=len(a.E);a.table(i,x,z,w,d,y)
        for e in a.E[first:]:a.LAYERS[e['id']]=layer
    chair(i+'_chaira',x,z+.85,y,0,layer);chair(i+'_chairb',x,z-.85,y,math.pi,layer)
    a.add(dict(type='primitive',id=i+'_cup',shape='cylinder',position=[x+.15,y+.84,z],radius=.045,height=.12,segments=14,material='porcelain'),layer)
    box(i+'_book',x-.15,y+.79,z,.22,.025,.28,'paper',layer)

def shelf(i,x,z,y=F,w=2.0,layer='furniture_1'):
    box(i+'_back',x,y+1.05,z,w,2.1,.07,'oak',layer)
    for k in range(5):
        yy=y+.12+k*.44
        box(i+f'_shelf{k}',x,yy,z-.18,w,.045,.40,'oak',layer)
        if k<4:
            for j in range(10):
                h=.22+.04*(j%3)
                box(i+f'_book{k}_{j}',x-w/2+.13+j*(w-.26)/9,yy+.025+h/2,z-.18,.09,h,.19,['paper','clay','sage_fabric','blue'][j%4],layer)

def stair_pair(i,y,params):
    x,z,w,run,rise,steps=[params[k] for k in ['x','z','width','run','rise','steps']]
    gap=params['gap'];landing=params['landing'];mid=y+rise/2
    for suffix,cx,za,zb,ya,yb in [('a',x,z,z+run,y,mid),('b',x+w+gap,z+run,z,mid,y+rise)]:
        a.add(dict(type='stair',id=i+suffix,**{'from':[cx,ya,za]},to=[cx,yb,zb],width=w,
            stepCount=steps,stepHeight=rise/(2*steps),stepDepth=run/steps,material='oak'),'stair')
        a.guard(i+suffix+'_guard',[[cx-w/2,ya+.08,za],[cx-w/2,yb+.08,zb]],.95)
    slab(i+'_landing',[x-w/2,z+run,x+w*1.5+gap,z+run+landing],mid,'oak',.18,'stair')
    a.guard(i+'_back_guard',[[x-w/2,mid,z+run+landing],[x+w*1.5+gap,mid,z+run+landing]],1.0)
    return [x-w/2-.06,z,x+w*1.5+gap+.06,z+run+landing+.06]

def glass_guard(i,path,y,h=1.02,layer='detail'):
    # 无粗立柱的玻璃露台：细顶槽、低底槽和分段玻璃，保留图片的轻薄轮廓。
    for j,(pa,pb) in enumerate(zip(path,path[1:])):
        xa,za=pa;xb,zb=pb;length=math.hypot(xb-xa,zb-za);n=math.ceil(length/1.6)
        for k in range(n):
            t=(k+.5)/n;xx=xa+(xb-xa)*t;zz=za+(zb-za)*t
            box(f'{i}_pane{j}_{k}',xx,y+h*.5,zz,length/n-.012,h-.05,.014,'glass',layer,[0,math.atan2(-(zb-za),xb-xa),0])
        rod(f'{i}_top{j}',[xa,y+h,za],[xb,y+h,zb],.026,.026,'bronze',layer)
        rod(f'{i}_base{j}',[xa,y+.025,za],[xb,y+.025,zb],.035,.035,'bronze',layer)

def stone():
    b=[-2.5,0,10.1,10.2];wing=[-9.5,-2.8,-2.5,6]
    slab('site',p['site'],.015,'grass',.20,'site')
    slab('main_plinth',[-2.68,-.18,10.28,10.38],F-.12,'concrete',.55,'foundation')
    slab('wing_plinth',[-9.68,-2.98,-2.48,6.18],F-.12,'concrete',.55,'foundation')
    slab('main_ground',b,F,'oak',.22,'floor_1');slab('wing_ground',wing,F,'oak',.22,'floor_1')
    hole=stair_pair('inside_stair',F,p['stair'])
    plate('main_upper',b,F+H,[hole],layer='floor_2')
    for level in range(2):
        y=F+level*H;lay='wall_'+str(level+1)
        s=walls('main'+str(level),b,y,H,'stone',layer=lay)
        for j,(start,w) in enumerate([(.42,2.15),(3.08,2.3),(6.62,1.75),(8.95,3.15)]):
            if level==0 and j==1:door('entry',s['front'],start,y,w,3.23)
            else:window(f'front_{level}_{j}',s['front'],start,y+.12,w,3.23,1 if j==3 else 0)
            xx=b[0]+start+w/2
            for k,dx in enumerate([-w/2-.10,w/2+.10]):box(f'reveal_{level}_{j}_{k}',xx+dx,y+1.75,-.23,.18,3.48,.28,'stone','facade_'+str(level+1))
            box(f'lintel_{level}_{j}',xx,y+3.48,-.23,w+.38,.20,.28,'stone','facade_'+str(level+1))
        if level==1:
            for j,start in enumerate([2.4,6.0]):window('east_upper'+str(j),s['right'],start,y+.6,1.25,2.65)
            door('terrace_access',s['left'],6.6,y,1.4,2.8)
            a.guard('inside_void',[[hole[0],y,hole[1]],[hole[0],y,hole[3]],[hole[2],y,hole[3]],[hole[2],y,hole[1]]],1.02,True)
        else:door('wing_connection',s['left'],6.6,y,1.4,2.7)
        for j,start in enumerate([.8,4.8,8.2]):window(f'back_{level}_{j}',s['back'],start,y+.75,2.3,2.3,1)
        # 正面水平石梁与外侧收边。
        box('front_band'+str(level),3.8,y+H-.04,-.24,13,.28,.32,'stone','facade_'+str(level+1))
    ws=walls('wing',wing,F,H-.24,'stone',skip=['right'],layer='wall_1')
    for j in range(4):window('wing_window'+str(j),ws['front'],.25+j*1.71,F+.12,1.42,2.95)
    exposed=a.wall('wing_wood_side',-2.5,-2.8,-2.5,0,F,F+H-.24,.28,'oak','wall_1')
    for j in range(16):
        box('wood_course'+str(j),-2.345,F+.12+j*.205,-1.4,.03,.184,2.78,'oak','facade_1')
    # 左翼平屋顶完成面恰好与主楼二层相接。
    plate('wing_roof',[-9.65,-2.95,-2.5,6.15],F+H-.24,mat='plaster',t=.24,layer='roof_wing',roof=True)
    glass_guard('wing_terrace',[[-2.5,-2.95],[-9.65,-2.95],[-9.65,6.15],[-2.5,6.15]],F+H,1.02,'terrace_2')
    glass_guard('wing_short_guard',[[-2.5,-2.95],[-2.5,0]],F+H,1.02,'terrace_2')
    plate('main_roof',[-2.65,-.15,10.25,10.35],F+2*H,[p['skylight']],mat='plaster',t=.24,layer='roof',roof=True)
    plate('green_roof',[-2.4,.1,10,10.1],F+2*H+.34,[p['skylight']],mat='moss',t=.10,layer='roof_planting')
    for j,(x,z,w,d) in enumerate([(3.8,0,13,.17),(3.8,10.2,13,.17),(-2.5,5.1,.17,10.2),(10.1,5.1,.17,10.2)]):
        box('roof_parapet'+str(j),x,F+2*H+.40,z,w,.40,d,'plaster','roof_detail')
    sky=p['skylight'];cx=(sky[0]+sky[2])/2;cz=(sky[1]+sky[3])/2;sy=F+2*H+.46
    for j,(x,z,w,d) in enumerate([(cx,sky[1],4.15,.10),(cx,sky[3],4.15,.10),(sky[0],cz,.10,3.6),(sky[2],cz,.10,3.6)]):
        box('skylight_curb'+str(j),x,sy-.12,z,w,.24,d,'plaster','roof_detail')
        box('skylight_frame'+str(j),x,sy+.02,z,w,.055,d,'bronze','roof_detail')
    a.add(dict(type='roof',id='skylight_glass',roofType='hip',span=4,depth=3.6,height=.48,thickness=.014,position=[cx,sy,cz],material='roof_glass'),'roof_detail')
    for j,(x,z) in enumerate([(sky[0],sky[1]),(sky[2],sky[1]),(sky[2],sky[3]),(sky[0],sky[3])]):
        rx=cx+(-.2 if x<cx else .2)
        rod('skylight_hip'+str(j),[x,sy+.035,z],[rx,sy+.51,cz],.035,.035,'bronze','roof_detail')
    for j in range(165):
        x=rng.uniform(-2.15,9.75);z=rng.uniform(.35,9.85)
        if sky[0]-.12<x<sky[2]+.12 and sky[1]-.12<z<sky[3]+.12:continue
        foliage('sedum'+str(j),x,F+2*H+.36,z,.13+rng.random()*.12,[1,.28,1],mat=rng.choice(['moss','leaf_light','leaf_gold']),layer='roof_planting')
    # 前庭、完整六级宽阶与低矮阶梯侧墙。
    slab('front_court',[-2.7,-4.0,10.45,0],F,'paving',.25,'court')
    slab('wing_court',[-9.8,-4.0,-2.7,-2.8],F,'paving',.25,'court')
    for j in range(6):
        top=(j+1)*F/6;z=-6.4+j*.4
        slab('entry_step'+str(j),[-.3,z,10.45,-4.0],top,'paving',F/6,'entry_stair')
        for k,x in enumerate([-.4,10.55]):box(f'stair_cheek{j}_{k}',x,top/2+.17,z+.2,.18,top+.34,.40,'plaster','entry_stair')
    for j,x in enumerate([.8,8.2]):plant('front_planter'+str(j),x,F,-2.1,1.1)
    for j,z in enumerate([-3.5,-2.2,-.9]):plant('entrance_green'+str(j),-2.9,F,z,.65,False)
    # 暗侧补室内阅读/会客，不改变可见四组正面高窗。
    for n,y in enumerate([F,F+H]):
        layer='furniture_'+str(n+1)
        table('reading'+str(n),6.9,2.5,y,2.0,.9,layer)
        table('side_table'+str(n),3.8,7.4,y,1.7,.8,layer)
        shelf('books'+str(n),7.5,9.65,y,2.8,layer)
        for j,(x,z) in enumerate([(1.4,2.8),(6.7,3),(6.4,7.2)]):light(f'ceiling_{n}_{j}',x,y+2.8,z,14,True,'lighting_'+str(n+1))
    table('wing_meeting',-6.2,1.2,F,3.2,1.2)
    light('wing_pendant',-6.2,F+2.8,1.2,17,True)
    sign('building_name',p['sign'],-2.31,2.1,-.10,.23,1.0,color=[.27,.23,.16])
    # 名牌位于入口侧的窄牌上，图片主体仍保持无大字招牌的外观。
    get('building_name')['label']['text']='林庭\n石光馆'
    for j,(x,z,s) in enumerate([(-12.5,8,1.25),(-12.7,15.8,1.15),(-5.8,15.7,1.35),(3.5,16.7,1.2),(13.2,15.5,1.3),(13.6,6.2,1.05)]):tree('forest'+str(j),x,z,.02,s)
    for j,(x,z) in enumerate([(-11.4,2.5),(-10.6,-5),(12.2,1),(11.6,12)]):
        for k in range(7):foliage(f'ground_shrub{j}_{k}',x+rng.uniform(-.7,.7),.3+rng.random()*.35,z+rng.uniform(-.6,.6),.38,[1,.6,1],layer='landscape')
    return dict(stair_hole=hole,skylight_hole=sky,roof_base=F+2*H)

def forest():
    b=[0,0,8.6,7.6];mid=[2.25,1.4,8.6,7.6];up=[2.25,2.65,8.35,7.4]
    slab('site',p['site'],.02,'paving',.20,'site')
    for j in range(26):box('paving_joint'+str(j),5,.024,-3.8+j*.60,15.9,.006,.012,'concrete','landscape')
    slab('ground_floor',b,F,'oak',.22,'floor_1')
    slab('second_floor',[0,0,8.6,7.6],F+H,'oak',.24,'floor_2')
    hole=stair_pair('upper_stair',F+H,p['stair'])
    plate('third_floor',up,F+2*H,[hole],layer='floor_3')
    # 左侧标识塔只作实体/服务体量；二至三层楼梯实际在主楼后侧。
    left=walls('left_tower',[0,0,2.25,7.6],F,2*H,'plaster',skip=['right'],layer='wall_1')
    for j in range(2):window('tower_side'+str(j),left['left'],.7+j*3.2,F+.1,2.4,2.95,1)
    window('tower_front_window',left['front'],.27,F+.1,1.38,2.8)
    box('tower_face_extension',1.125,F+2*H+.77,-.10,2.25,1.54,.20,'plaster','tower')
    # 首层：白墙包边与接近转角的落地玻璃。
    s=walls('ground_shop',[2.25,0,8.6,7.6],F,H,'plaster',skip=['left'],layer='wall_1')
    door('main_entry',s['front'],.28,F,1.7,2.82)
    window('ground_front_glass',s['front'],2.14,F+.1,3.91,2.74,2)
    window('ground_east_glass',s['right'],.20,F+.1,6.95,2.74,3)
    door('rear_service',s['back'],.5,F,1.1,2.6,False)
    # 二层室内与向前退让的露台。
    s=walls('middle_shop',mid,F+H,H,'plaster',skip=['left'],layer='wall_2')
    door('middle_terrace_door',s['front'],.18,F+H,1.35,2.8)
    window('middle_front_glass',s['front'],1.68,F+H+.1,4.42,2.75,2)
    window('middle_east_glass',s['right'],.2,F+H+.1,3.9,2.75,1)
    door('stair_arrival_door',s['right'],4.75,F+H,1.1,2.8)
    # 左侧与塔的连接用带门内墙，避免与塔已有实体重叠。
    host=a.wall('middle_left',2.25,7.6,2.25,1.4,F+H,F+2*H,.14,'plaster','wall_2')
    door('middle_left_access',host,2.7,F+H,1,2.5,False)
    for level,bounds in [(1,b),(2,[2.1,1.25,8.75,7.75])]:
        x0,z0,x1,z1=bounds;y=F+level*H
        box('front_fascia'+str(level),(x0+x1)/2,y-.04,z0-.05,x1-x0+.12,.32,.22,'plaster','edge_'+str(level))
        box('east_fascia'+str(level),x1+.03,y-.04,(z0+z1)/2,.22,.32,z1-z0+.1,'plaster','edge_'+str(level))
    a.guard('middle_terrace_guard',[[2.25,F+H,-.02],[8.6,F+H,-.02],[8.6,F+H,1.4]],.98)
    # 室外直跑楼梯落在首层小平台，顶端设足够转身的平台和可进入的门。
    e=p['exterior_stair'];x=e['x'];z=e['z'];end=z+e['run']
    slab('stair_start',[x-e['width']/2,z-.8,x+e['width']/2,z],F,'paving',.22,'outside_stair')
    a.add(dict(type='stair',id='outside_stair',**{'from':[x,F,z]},to=[x,F+H,end],width=e['width'],
        stepCount=e['steps'],stepHeight=H/e['steps'],stepDepth=e['run']/e['steps'],material='plaster'),'outside_stair')
    slab('outside_landing',[8.6,end,10.32,e['landing_end']],F+H,'paving',.22,'outside_stair')
    # 外侧白墙使用小截面连续盒体填实体，斜顶由一条平滑实心压顶覆盖。
    for j in range(96):
        zz=z+(j+.5)*e['run']/96;top=F+.9+H*(j+.5)/96
        box('stair_solid_cheek'+str(j),10.28,(top+.04)/2,zz,.20,top-.04,e['run']/96+.002,'plaster','outside_stair')
    rod('stair_sloping_coping',[10.28,F+.9,z],[10.28,F+H+.9,end],.24,.13,'plaster','outside_stair')
    outer=a.wall('landing_outer_wall',10.28,end,10.28,7.6,.04,F+H+.9,.20,'plaster','outside_stair')
    window('understair_window',outer,.52,F+.25,.75,1.65,0)
    a.wall('landing_back_wall',10.28,7.6,8.6,7.6,.04,F+H+.9,.20,'plaster','outside_stair')
    # 三层透明小屋与深色水平叠片檐口。
    s=walls('top_shop',up,F+2*H,H-.15,'plaster',layer='wall_3')
    window('top_front_glass',s['front'],.18,F+2*H+.1,5.74,2.60,2)
    window('top_right_glass',s['right'],.18,F+2*H+.1,4.36,2.60,2)
    window('top_left_window',s['left'],3.1,F+2*H+.55,1.1,1.8)
    window('top_rear_glass',s['back'],.4,F+2*H+.55,4.9,2.15,2)
    a.guard('top_stair_void',[[hole[0],F+2*H,hole[1]],[hole[0],F+2*H,hole[3]],[hole[2],F+2*H,hole[3]],[hole[2],F+2*H,hole[1]]],1.02)
    plate('top_roof',[2.05,2.45,8.55,7.6],F+3*H-.15,mat='dark_wood',t=.20,layer='roof',roof=True)
    for j in range(6):
        y=F+3*H-.14+j*.07
        box('top_roof_louver_front'+str(j),5.3,y,2.37,6.75,.035,.16,'bronze','roof_detail')
        box('top_roof_louver_east'+str(j),8.64,y,5.02,.16,.035,5.45,'bronze','roof_detail')
    plate('tower_roof',[-.08,-.08,2.3,7.68],F+2*H+1.54,mat='plaster',t=.15,layer='tower_roof',roof=True)
    # 上层室内以外的二层屋面是真实种植带，避免空中悬花盆。
    plate('middle_roof_garden',[2.1,1.25,8.75,7.75],F+2*H+.03,[up],mat='soil',t=.16,layer='roof_garden')
    box('garden_front_curb',5.4,F+2*H+.18,1.22,6.7,.38,.18,'plaster','roof_garden')
    for j,x in enumerate([2.7,4.1,5.8,7.6]):
        plant('roof_front_plant'+str(j),x,F+2*H+.08,1.9,.7,False,'roof_garden')
        vine('front_vine'+str(j),x,F+2*H+.32,1.10,1.2+j*.27,layer='roof_garden')
    for j,zv in enumerate([3.2,4.0,5.0,6.0,7.0]):
        plant('roof_side_plant'+str(j),8.58,F+2*H+.10,zv,.58,False,'roof_garden')
        vine('right_vine'+str(j),8.84,F+3*H-.02,zv,2.8+j*.45,'right','roof_garden')
    for j in range(22):
        foliage('top_sedum'+str(j),rng.uniform(2.4,8.2),F+3*H+.15,rng.uniform(2.8,7.2),.20,[1,.35,1],layer='roof_planting')
    tree('terrace_tree',3.1,2.0,F+2*H+.08,.55,'roof_garden')
    # 与图一致的三行英文，留白墙厚度与塔面齐平。
    sign('building_name',p['sign'],1.125,6.65,-.218,1.90,2.25,color=[.14,.055,.025])
    # 白色腰线下的墙灯，以及玻璃空间内的暖色吊灯。
    for j,xv in enumerate([.5,2.1,6.9]):light('front_sconce'+str(j),xv,F+H-.35,-.21,5,False,'lighting_1')
    for level in range(3):
        y=F+level*H;layer='furniture_'+str(level+1)
        positions=[(4.1,2.4),(6.8,4.1)] if level==0 else [(4.3,3.0),(6.9,5.5)] if level==1 else [(6.7,3.65),(6.6,6.15)]
        for j,(xx,zz) in enumerate(positions):
            table(f'cafe_table{level}_{j}',xx,zz,y,1.1,.65,layer,True)
            light(f'pendant{level}_{j}',xx,y+2.45,zz,17,True,'lighting_'+str(level+1))
    # 吧台、咖啡机、杯具、后墙书架和一层服务间。
    box('bar_base',5.6,F+.48,6.6,4.7,.96,.8,'oak','furniture_1')
    box('bar_top',5.6,F+1.00,6.6,4.85,.08,.90,'paving','furniture_1')
    box('coffee_machine',4.2,F+1.32,6.7,1.0,.58,.53,'bronze','furniture_1')
    box('coffee_machine_front',4.2,F+1.30,6.42,.84,.35,.028,'black','furniture_1')
    for j in range(7):a.add(dict(type='primitive',id='bar_cup'+str(j),shape='cylinder',position=[5.1+j*.22,F+1.11,6.55],radius=.05,height=.13,segments=14,material='porcelain'),'furniture_1')
    shelf('bar_shelves',6.3,7.32,F,3.2)
    for level in [1,2]:shelf('floor_books'+str(level),6.65,7.12,F+level*H,2.3,'furniture_'+str(level+1))
    host=a.wall('service_front',0,4.0,2.25,4.0,F,F+H,.14,'plaster','wall_1')
    door('service_door',host,.65,F,.9,2.4,False)
    a.wall('service_side',2.25,4.0,2.25,7.6,F,F+H,.14,'plaster','wall_1')
    box('wc',1,F+.3,6.8,.45,.6,.62,'porcelain','furniture_1')
    table('terrace_table',5.2,.55,F+H,1.2,.6,'furniture_2',False)
    for j,(xx,zz,s) in enumerate([(2.6,.40,.70),(8.1,.6,.65),(8.1,2.2,.7),(.45,-.5,.9),(8.4,-.65,.9),(10.8,8,.9)]):
        plant('garden_pot'+str(j),xx,F if j<3 else .03,zz,s,True,'planting')
    sign('menu','Today\nCoffee & Bread\nOPEN',6.7,.73,-1.05,.65,.95,'dark_wood',[.85,.83,.69],False)
    for j,xx in enumerate([6.45,6.95]):box('menu_foot'+str(j),xx,.24,-1.0,.05,.48,.08,'oak','signage')
    tree('back_tree',-.9,9.5,.02,.85);tree('right_tree',10.4,9.4,.02,.78)
    return dict(stair_hole=hole,exterior_arrival=[x,F+H,end],levels=[F,F+H,F+2*H],roof_base=F+3*H-.15)

evidence={'stone':stone,'forest':forest}[p['recipe']]()
bp=dict(meta=dict(version='1.1',type='building',name=p['name'],author='Codex',description=p['concept'],style=p['materials']),
    geometry=dict(elements=a.E,components=a.C),materials=a.M,assets={})
target=BASE/(p['name']+'.wild')
data=(json.dumps(bp,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
if '--check' in sys.argv:
    assert target.read_bytes()==data,'重放与正式WILD不一致'
    print(json.dumps(dict(replay_identical=True,sha256=hashlib.sha256(data).hexdigest()),ensure_ascii=False));sys.exit(0)
rev=1+len(list((BASE/'03-过程记录').glob('r[0-9]*')))
snapshot=BASE/'03-过程记录'/f'r{rev}';snapshot.mkdir(parents=True)
if target.exists():
    shutil.copyfile(target,snapshot/'修订前.wild')
    if (BASE/'05-效果图/render_manifest.json').exists():shutil.copytree(BASE/'05-效果图',snapshot/'修订前效果图')
    if (BASE/'04-校验/最终项目校验.json').exists():shutil.copyfile(BASE/'04-校验/最终项目校验.json',snapshot/'修订前项目校验.json')
target.write_bytes(data)
shutil.copyfile(target,snapshot/target.name);shutil.copyfile(__file__,snapshot/'作者编译器.py')
shutil.copyfile(HERE/'构件作者工具.py',snapshot/'构件作者工具.py');shutil.copyfile(design_path,snapshot/'DesignDocument.json')
(BASE/'03-过程记录/构件分层.json').write_text(json.dumps(a.LAYERS,ensure_ascii=False,indent=2),encoding='utf-8')
record=dict(revision=rev,design_sha256=hashlib.sha256(design_raw).hexdigest(),wild_sha256=hashlib.sha256(data).hexdigest(),
    elements=len(a.E),components=len(a.C),materials=len(a.M),recipe=p['recipe'],geometry_evidence=evidence,
    lights=sum('lightSource' in e for e in a.E),method='User image -> DesignDocument -> deterministic assembly -> WILD; no Agent/model API')
(snapshot/'编译记录.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
(BASE/'03-过程记录/编译记录.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(record,ensure_ascii=False,indent=2))
