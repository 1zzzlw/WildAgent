"""读取已保存设计，确定性展开本次别墅；不是通用建筑生成器。"""
import hashlib
import json
import math
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
doc = json.loads((BASE/'01-设计/DesignDocument.json').read_text(encoding='utf-8'))
d = doc['decisions']['authoring']
F, TOP = d['ffl'], d['wall_top']
E, C, M = [], [], {}

def mat(id, color, rough=.75, metal=0, **kw):
    M[id] = dict(baseColor=color, roughness=rough, metallic=metal, albedo=.75, lightingCondition='D65_noon', **kw)

mat('plaster',[.86,.83,.74],.88)
mat('stone',[.61,.57,.47],.86,surfacePattern='quartz')
mat('paving',[.77,.73,.63],.88,surfacePattern='quartz')
mat('wood',[.35,.18,.075],.73,surfacePattern='planks')
mat('roof',[.075,.095,.087],.64,.2)
mat('frame',[.065,.075,.067],.5,.4)
mat('glass',[.63,.80,.79],.12,opacity=.32,materialClass='glass',transmission=.6,ior=1.45,thickness=.025)
mat('frosted',[.72,.81,.78],.6,opacity=.75,materialClass='glass',transmission=.15)
mat('fabric',[.83,.78,.65],.95,materialClass='fabric')
mat('linen',[.54,.60,.51],.95,materialClass='fabric')
mat('ceramic',[.88,.88,.81],.25)
mat('water',[.08,.45,.50],.12,opacity=.72)
mat('pool_tile',[.21,.46,.46],.32)
mat('lawn',[.25,.34,.19],.96)
mat('leaf',[.16,.30,.12],.88)
mat('leaf_light',[.32,.43,.19],.88)
mat('soil',[.21,.17,.11],1)
mat('gravel',[.48,.47,.39],1)
mat('lamp',[1,.73,.37],.3,emissive=[1,.58,.20],emissiveIntensity=1.8)

def box(id,p,size,material='wood',rotation=None,**kw):
    e=dict(type='primitive',id=id,shape='box',position=p,dimensions=size,material=material,**kw)
    if rotation: e['rotation']=rotation
    E.append(e)
    return e

def sphere(id,p,r,material,scale=None,rotation=None):
    e=dict(type='primitive',id=id,shape='sphere',position=p,radius=r,segments=12,material=material)
    if scale: e['scale']=scale
    if rotation: e['rotation']=rotation
    E.append(e)

def cylinder(id,p,r,h,material,r_top=None):
    E.append(dict(type='primitive',id=id,shape='cylinder',position=p,radiusTop=r if r_top is None else r_top,
                  radiusBottom=r,height=h,segments=12,material=material))

def slab(id,rect,bottom,thick,material,holes=None):
    x0,z0,x1,z1=rect
    e=dict(type='floor',id=id,from_=[x0,bottom,z0],thickness=thick,material=material)
    e['from']=e.pop('from_')
    if holes:
        e.update(shape='polygon',polygon=[[0,0],[x1-x0,0],[x1-x0,z1-z0],[0,z1-z0]],
                 holes=[[[h[0]-x0,h[1]-z0],[h[2]-x0,h[1]-z0],[h[2]-x0,h[3]-z0],[h[0]-x0,h[3]-z0]] for h in holes])
    else: e.update(shape='rect',to=[x1,bottom,z1])
    E.append(e)

def furniture(id,kind,x,z,w,depth,h,material='wood',angle=0):
    E.append(dict(type='furniture',id=id,subtype=kind,position=[x,F,z],
                  dimensions=dict(width=w,depth=depth,height=h),rotation=[0,angle,0],material=material))

def light(id,x,y,z,power=2.8,distance=5):
    box(id+'_back',[x,y+.055,z],[.19,.09,.19],'frame')
    box(id,[x,y,z],[.13,.035,.13],'lamp',lightSource=dict(lightType='point',color=[1,.76,.43],
        intensity=power,distance=distance,initiallyOn=True))

# 所有覆盖泳池的水平层都留同一孔；避免用透明面遮住实心地面。
pool=d['pool']
slab('site',d['site'],-.22,.22,'lawn',[pool])
slab('terrace',[-12,-6,12,8],-.02,.18,'paving',[pool])
for v in doc['decisions']['volumes']:
    slab('finish_'+v['id'],[v['x'],v['z'],v['x']+v['width'],v['z']+v['depth']],.16,.02,'paving')
slab('pool_bottom',pool,d['pool_bottom']-.16,.16,'pool_tile')
for id,p,s in [
    ('west',[-2.10,-.50,-1],[.20,1.24,4.4]),('east',[2.10,-.50,-1],[.20,1.24,4.4]),
    ('south',[0,-.50,-3.1],[4,1.24,.20]),('north',[0,-.50,1.1],[4,1.24,.20])]:
    box('pool_wall_'+id,p,s,'pool_tile')
slab('pool_water',[-1.99,-2.99,1.99,.99],d['water_level']-.025,.025,'water')
for id,p,s in [('w',[-2.16,.17,-1],[.32,.06,4.64]),('e',[2.16,.17,-1],[.32,.06,4.64]),
               ('s',[0,.17,-3.16],[4,.06,.32]),('n',[0,.17,1.16],[4,.06,.32])]:
    box('pool_coping_'+id,p,s,'stone')
for i in range(3):
    # 宽浅水中踏步靠北侧，最高面仍低于水面。
    box('pool_step_'+str(i),[1.25,-.96+i*.28,.78-i*.31],[1.25,.28,.32],'pool_tile')

# U 形围合仅一套真实外墙，三体量共享口直接连通。
walls={}
for w in d['walls']:
    e=dict(type='wall',id=w['id'],thickness=w['thickness'],material=w['material'],
           **{'from':[w['a'][0],F,w['a'][1]],'to':[w['b'][0],TOP,w['b'][1]]})
    E.append(e); walls[w['id']]=e
for id,kind,host,along,width,sill,height,finish in d['openings']:
    c=dict(type=kind,id=id,parentWall=host,width=width,height=height,
           frameWidth=.055,frameDepth=walls[host]['thickness']+.02,frameMaterial='frame',
           **{'from':[along,F+sill,0]})
    if kind=='window':
        c.update(glassMaterial=finish,glassDepth=.025,verticalMullions=max(0,round(width/1.35)-1),horizontalMullions=0,mullionWidth=.035)
    else:
        c.update(leafMaterial=finish,leafDepth=.035,doorStyle='double' if width>1.5 else 'single',leafRows=1)
        c['interaction']=dict(mode='swing',initiallyOpen=False,openAngle=90)
    C.append(c)

# 完整天花/深檐：墙顶3.50，檐底板底3.50，板顶3.57=坡顶最低3.75−0.18。
for side,x in [('west',-8),('east',8)]:
    slab('soffit_'+side,[x-4,-6,x+4,8],TOP,.07,'wood')
    E.append(dict(type='roof',id='roof_'+side,roofType='hip',position=[x,d['roof_eave'],1],
                  span=8,depth=14,height=d['roof_rise'],thickness=d['roof_thickness'],material='roof'))
    for tag,p,s in [('front',[x,3.60,-6],[8,.18,.11]),('back',[x,3.60,8],[8,.18,.11]),
                    ('outer',[x+(-4 if x<0 else 4),3.60,1],[.11,.18,14])]:
        box('fascia_'+side+'_'+tag,p,s,'frame')
    # 正面百叶只占实墙侧的窄段，不横挡门与落地窗。
    screen_x=x+(-2.8 if x<0 else -2.55)
    for i in range(5):
        box('screen_'+side+'_'+str(i),[screen_x+i*.15,1.86,-5.28],[.07,3.14,.12],'wood')
    # 面向内院的屋下木柱落在露台上，柱顶抵檐底。
    inner=x+(3.85 if x<0 else -3.85)
    for j,z in enumerate([-5.65,1.9]):
        box('post_'+side+'_'+str(j),[inner,(.16+TOP)/2,z],[.16,TOP-.16,.16],'wood')
        box('post_base_'+side+'_'+str(j),[inner,.235,z],[.28,.15,.28],'stone')
slab('hall_canopy',[-4.05,1.65,4.05,8],TOP,.20,'roof')
box('hall_canopy_front',[0,3.55,1.65],[8.1,.22,.15],'wood')
for x in [-3.8,3.8]:
    box('hall_post_'+str(int(x*10)),[x,(.16+TOP)/2,1.78],[.18,TOP-.16,.18],'wood')
for i,x in enumerate([-3.2,-2.4,-1.6,-.8,0,.8,1.6,2.4,3.2]):
    box('hall_soffit_rib_'+str(i),[x,3.46,2.32],[.045,.08,1.33],'wood')

# 到达与前庭：三段宽踏步，左右通道绕池进入门厅。
for i,(z,top) in enumerate([(-6.9,.06),(-6.55,.12),(-6.2,.16)]):
    slab('arrival_step_'+str(i),[-1.4,z-.2,1.4,z+.2],0,top,'paving')
slab('approach',[-1.4,-9.9,1.4,-7.1],0,.025,'stone')
for i in range(7):
    slab('path_joint_'+str(i),[-1.4,-9.8+i*.38,1.4,-9.785+i*.38],.025,.002,'gravel')
box('entry_marker',[-2.5,.66,-6.6],[1.1,1.32,.25],'stone')
box('entry_name',[-2.5,.95,-6.74],[.92,.34,.04],'frame',rotation=[0,math.pi,0],
    label=dict(text='棕影水院',color=[.92,.83,.64]))

# 起居、餐厨；家具外缘避让后厅连接与庭院门。
furniture('living_sofa','sofa',-9.7,-2.1,2.8,1.05,.82,'fabric',math.pi/2)
furniture('living_table','table',-8,-2.05,1.5,.8,.42,'wood')
furniture('living_chair','chair',-6.45,-.8,.74,.8,.82,'linen',-math.pi/2)
box('rug',[-8.3,F+.008,-2.1],[4.1,.016,3.3],'linen')
furniture('tv_low_cabinet','tv_cabinet',-5.45,.1,1.8,.45,.5,'wood',math.pi/2)
furniture('dining_table','table',-8,1.75,2.25,1.05,.76,'wood')
for i,(x,z,a) in enumerate([(-8.75,.85,0),(-7.3,.85,0),(-8.75,2.65,math.pi),(-7.3,2.65,math.pi)]):
    furniture('dining_chair_'+str(i),'chair',x,z,.52,.55,.85,'wood',a)
box('kitchen_base',[-8, .60,6.35],[5.2,.84,.65],'wood')
box('kitchen_counter',[-8,1.045,6.35],[5.25,.07,.72],'stone')
box('sink_bowl',[-9.25,1.088,6.35],[.62,.018,.40],'frame')
box('hob',[-6.8,1.087,6.35],[.65,.018,.48],'frame')
for i in range(7):
    box('cabinet_joint_'+str(i),[-10.55+i*.76,.60,5.999],[.012,.78,.008],'frame')
box('kitchen_island',[-8, .62,4.6],[2.5,.88,.85],'wood')
box('island_top',[-8,1.09,4.6],[2.65,.06,.98],'stone')

# 两间独立卧室、书桌和卫浴实体，不用房间名称代替功能。
for tag,z in [('master',-2.7),('guest',1.35)]:
    furniture(tag+'_bed','bed',9.25,z,1.8,2.05,.55,'fabric')
    box(tag+'_headboard',[9.25,.81,z+.99],[2.0,1.26,.12],'wood')
    furniture(tag+'_nightstand','nightstand',7.95,z+.65,.45,.45,.5,'wood')
    furniture(tag+'_wardrobe','wardrobe',10.48,z-1.55,.60,1.3,2.25,'wood',math.pi/2)
furniture('study_desk','table',6.8,6.25,2.0,.65,.75,'wood')
furniture('study_chair','chair',6.8,5.4,.55,.60,.86,'linen')
box('bath_vanity',[9.55,.60,6.42],[1.1,.84,.60],'wood')
box('bath_basin',[9.55,1.05,6.42],[.7,.16,.43],'ceramic')
box('bath_mirror',[9.55,1.85,6.83],[.85,.95,.035],'glass')
box('wc_tank',[10.50,.72,5.25],[.4,.75,.24],'ceramic')
sphere('wc_bowl',[10.5,.48,4.95],.24,'ceramic',[1,1,1.4])
slab('shower_tray',[9.1,3.85,10.75,4.55],F,.025,'stone')
box('shower_screen',[9.1,1.18,4.15],[.025,2,.64],'glass')

# 院内休憩家具与绿化；棕榈为自足参数化示意，不依赖外部模型。
for i,z in enumerate([-2.8,-.4]):
    box('lounger_'+str(i),[3.35,.45,z],[.72,.2,1.85],'wood')
    box('lounger_pad_'+str(i),[3.35,.59,z-.2],[.68,.08,1.45],'fabric')
    box('lounger_back_'+str(i),[3.35,.79,z+.7],[.68,.08,.72],'fabric',rotation=[-.5,0,0])
furniture('terrace_side_table','table',3.25,-1.65,.45,.45,.50,'wood')
for i,(x,z,h) in enumerate([(-11.6,-7.3,4.8),(11.6,-7.5,5.5),(-11.6,9.2,4.2),(11.6,9.2,4.7)]):
    slab('palm_bed_'+str(i),[x-.72,z-.72,x+.72,z+.72],0,.08,'soil')
    cylinder('palm_trunk_'+str(i),[x,h/2,z],.16,h,'wood',.11)
    sphere('palm_crown_'+str(i),[x,h,z],.28,'leaf')
    for j in range(9):
        a=j*math.tau/9+.2*i
        sphere(f'palm_{i}_frond_{j}',[x+math.cos(a)*.9,h-.10,z+math.sin(a)*.9],1,'leaf' if j%2 else 'leaf_light',
               [1.25,.09,.22],[0,-a,.14])
for side,x in [('w',-12.9),('e',12.9)]:
    slab('border_'+side,[x-.35,-4.8,x+.35,6.8],0,.06,'soil')
    for i in range(12):
        sphere('border_'+side+'_'+str(i),[x,.35,-4.5+i*.95],.36,'leaf',[1,.8,1])

for i,(x,z) in enumerate([(-8,-2),(-8,1.75),(-8,5.1),(0,4.8),(8.7,-2.7),(8.7,1.3)]):
    light('interior_light_'+str(i),x,3.40,z,4.5,6)
for i,(x,z) in enumerate([(-4.45,-4.5),(-4.45,.6),(4.45,-4.5),(4.45,.6),(-2.7,2.2),(2.7,2.2)]):
    light('eave_light_'+str(i),x,3.39,z,4,6)
for i,x in enumerate([-2.65,2.65]):
    box('path_lamp_post_'+str(i),[x,.31,-5.3],[.1,.62,.1],'frame')
    light('path_light_'+str(i),x,.62,-5.3,1.8,3)

def quantize(v):
    if isinstance(v,float): return round(v,6)
    if isinstance(v,list): return [quantize(x) for x in v]
    if isinstance(v,dict): return {k:quantize(x) for k,x in v.items()}
    return v

bp=quantize(dict(meta=dict(version='1.1',type='building',name=d['name'],style='现代热带',seed=d['seed']),
                 geometry=dict(elements=E,components=C),materials=M))
output=BASE/(d['name']+'.wild')
raw=(json.dumps(bp,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n').encode('utf-8')
output.write_bytes(raw)
(BASE/'02-生成/生成记录.json').write_text(json.dumps(dict(
    design_sha256=hashlib.sha256((BASE/'01-设计/DesignDocument.json').read_bytes()).hexdigest(),
    wild_sha256=hashlib.sha256(raw).hexdigest(),file=output.name,bytes=len(raw),elements=len(E),components=len(C),materials=len(M),
    method='本方案作者脚本展开；随后由项目当前Core编译/重建。无skill、无模型API、无后端Agent。'),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(file=str(output),bytes=len(raw),elements=len(E),components=len(C)),ensure_ascii=False))
