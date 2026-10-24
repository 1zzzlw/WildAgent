"""检查原始文件、设计关系与平面连通；另存只删遮挡物的剖切副本。"""
import hashlib
import json
import math
from collections import deque
from pathlib import Path
from jsonschema import Draft202012Validator

BASE=Path(__file__).resolve().parents[1]
ROOT=BASE.parents[2]
DESIGN=BASE/'01-设计/DesignDocument.json'
d=json.loads(DESIGN.read_text('utf-8'))['decisions']['authoring']
path=BASE/(d['name']+'.wild')
raw=path.read_bytes()
b=json.loads(raw,parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
es=b['geometry']['elements']; cs=b['geometry']['components']; rows=es+cs
ids={x['id']:x for x in rows}
schema=json.loads((ROOT/'wild-core/schema.json').read_text('utf-8'))
errors=[f'{list(e.path)}: {e.message}' for e in Draft202012Validator(schema).iter_errors(b)]
assert len(ids)==len(rows), 'ID重复'
for e in rows:
    for k,v in e.items():
        if (k=='material' or k.endswith('Material')) and isinstance(v,str) and v not in b['materials']:
            errors.append(f'{e["id"]}: 未定义材质{v}')
    if e.get('parentWall'):
        w=ids.get(e['parentWall']); assert w and w['type']=='wall'
        length=math.dist(w['from'][::2],w['to'][::2])
        a,y,_=e['from']
        if a<0 or a+e['width']>length+1e-6 or y<w['from'][1]-1e-6 or y+e['height']>w['to'][1]+1e-6:
            errors.append(e['id']+': 开口超出宿主')
for i,a in enumerate(cs):
    for c in cs[i+1:]:
        if a.get('parentWall')!=c.get('parentWall'): continue
        if min(a['from'][0]+a['width'],c['from'][0]+c['width'])>max(a['from'][0],c['from'][0])+1e-6:
            if min(a['from'][1]+a['height'],c['from'][1]+c['height'])>max(a['from'][1],c['from'][1])+1e-6:
                errors.append(f'重叠开口: {a["id"]}/{c["id"]}')

# 在最终落盘数字上核对孔洞、檐底和柱顶，不依据脚本变量宣布通过。
pool=d['pool']
expected=[[pool[0],pool[1]],[pool[2],pool[1]],[pool[2],pool[3]],[pool[0],pool[3]]]
for name in ['site','terrace']:
    e=ids[name]; origin=e['from']
    actual=[[round(p[0]+origin[0],6),round(p[1]+origin[2],6)] for p in e['holes'][0]]
    assert actual==expected, name+'池口不一致'
for side in ['west','east']:
    roof=ids['roof_'+side]; soffit=ids['soffit_'+side]
    assert abs(soffit['from'][1]-d['wall_top'])<1e-6
    assert abs(soffit['from'][1]+soffit['thickness']-(roof['position'][1]-roof['thickness']))<1e-6
for e in es:
    if e['id'].startswith(('post_west_','post_east_','hall_post_')):
        assert abs(e['position'][1]+e['dimensions'][1]/2-d['wall_top'])<1e-6

# 2D 连通性：0.2m 网格、0.2m 身体半径；门按可开启净洞口计算。
# 不把窗口当门，不把门扇关闭画面当永远不可通行。检查家具/柜体足迹，但不模拟开门扫掠。
step=.2; radius=.2
walls=[e for e in es if e['type']=='wall']
doors=[e for e in cs if e['type']=='door']
obstacles=[]
for e in es:
    if e['type']=='furniture':
        x,_,z=e['position']; sz=e['dimensions']; w,h=sz['width'],sz['depth']; a=e.get('rotation',[0,0,0])[1]
        obstacles.append((x,z,w/2,h/2,a,e['id']))
    elif e['type']=='primitive' and e['shape']=='box' and e['id'] in ['kitchen_base','kitchen_island','bath_vanity','shower_screen']:
        x,_,z=e['position']; w,_,h=e['dimensions']; obstacles.append((x,z,w/2,h/2,0,e['id']))

def free(x,z):
    if not (-11.8<=x<=11.8 and -5.8<=z<=7.8): return False
    if pool[0]-.38<x<pool[2]+.38 and pool[1]-.38<z<pool[3]+.38: return False
    for w in walls:
        ax,_,az=w['from']; bx,_,bz=w['to']; dx,dz=bx-ax,bz-az; length=math.hypot(dx,dz)
        along=((x-ax)*dx+(z-az)*dz)/length
        distance=abs((x-ax)*dz-(z-az)*dx)/length
        if -radius<=along<=length+radius and distance<w['thickness']/2+radius:
            passages=[c for c in doors if c['parentWall']==w['id'] and c['from'][1]<=d['ffl']+.02]
            if not any(c['from'][0]+c['frameWidth']+radius<=along<=c['from'][0]+c['width']-c['frameWidth']-radius for c in passages):
                return False
    for ox,oz,hw,hd,a,_ in obstacles:
        dx,dz=x-ox,z-oz; lx=dx*math.cos(a)-dz*math.sin(a); lz=dx*math.sin(a)+dz*math.cos(a)
        if abs(lx)<hw+radius and abs(lz)<hd+radius: return False
    return True

def cell(p): return tuple(round(v/step) for v in p)
start=cell([0,-5.6]); queue=deque([start]); seen={start}
while queue:
    ix,iz=queue.popleft()
    for p in [(ix-1,iz),(ix+1,iz),(ix,iz-1),(ix,iz+1)]:
        if p not in seen and free(p[0]*step,p[1]*step): seen.add(p);queue.append(p)
targets=dict(living=[-7,-3.8],dining=[-6.2,1.7],kitchen=[-6,5.1],hall=[0,4.4],
             corridor=[5.8,0],master=[7.2,-1.5],guest=[7.2,2.9],study=[6.0,4.5],bath=[9.6,5.2])
routes={name:dict(point=p,reachable=cell(p) in seen) for name,p in targets.items()}
errors += [f'通路不连通: {name}' for name,v in routes.items() if not v['reachable']]

report=dict(ok=not errors,input_sha256=hashlib.sha256(raw).hexdigest(),errors=errors,
    count=dict(elements=len(es),components=len(cs),materials=len(b['materials'])),
    checks=['当前原始Schema','ID与材料引用','宿主类型及洞口范围','同墙开口不重叠','池口各层一致','檐口标高接触','柱顶抵达檐底'],
    circulation=dict(step=step,body_radius=radius,reachable_cells=len(seen),rooms=routes,
                     limits='平面近似，门视为可打开；未模拟门扇扫掠、人体碰撞、法规或结构安全。'),
    scope='结构化检查不是全碰撞检测，Core与真实渲染另行执行。')
(BASE/'03-验证/静态与空间检查.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

cutdir=BASE/'05-剖切';cutdir.mkdir(exist_ok=True)
prefixes=('roof_','soffit_','fascia_','hall_canopy','hall_soffit_rib_','palm_','interior_light_','eave_light_')
cut=json.loads(raw);cut['meta']['name']+='-移除屋面查看'
cut['geometry']['elements']=[e for e in es if not e['id'].startswith(prefixes)]
remaining={e['id'] for e in cut['geometry']['elements']}
cut['geometry']['components']=[c for c in cs if not c.get('parentWall') or c['parentWall'] in remaining]
cutraw=(json.dumps(cut,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8')
(cutdir/'室内剖切.wild').write_bytes(cutraw)
(cutdir/'来源.json').write_text(json.dumps(dict(source_sha256=report['input_sha256'],cut_sha256=hashlib.sha256(cutraw).hexdigest(),
    removed_ids=[e['id'] for e in es if e['id'] not in remaining],retained_objects_unchanged=all(e==ids[e['id']] for e in cut['geometry']['elements']),
    note='只删除屋面/檐底/遮挡灯及棕榈；未移动、缩短或重建保留构件。此副本不是正式交付。'),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
raise SystemExit(0 if report['ok'] else 1)
