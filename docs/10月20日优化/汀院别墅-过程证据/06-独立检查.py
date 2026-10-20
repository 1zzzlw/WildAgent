"""重新读盘检查本次模型；有界的空间抽样检查，不替代完整导航/网格碰撞或工程规范。"""
import json
import math
import hashlib
import sys
from pathlib import Path
from collections import Counter
from jsonschema import Draft202012Validator

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
TARGET=Path(sys.argv[1]) if len(sys.argv)>1 else HERE.parent/'汀院别墅-Codex.wild'
REPORT=Path(sys.argv[2]) if len(sys.argv)>2 else HERE/'06-独立检查结果.json'
bp=json.loads(TARGET.read_text(encoding='utf-8'))
design=json.loads((HERE/'01-设计事实.json').read_text(encoding='utf-8'))
schema=json.loads((ROOT/'wild-core/schema.json').read_text(encoding='utf-8'))
els=bp['geometry']['elements']; comps=bp['geometry']['components']
byid={e['id']:e for e in els+comps}
checks=[]


def check(name, errors, **evidence):
    checks.append(dict(name=name,passed=not errors,errors=errors,**evidence))


def rect(e):
    if e['type']=='floor':
        a,b=e['from'],e['to']; return [min(a[0],b[0]),max(a[0],b[0]),min(a[2],b[2]),max(a[2],b[2])]
    if e['type']=='roof':
        x,y,z=e['position']; return [x-e['span']/2,x+e['span']/2,z-e['depth']/2,z+e['depth']/2]
    if e['type']=='furniture':
        x,y,z=e['position']; d=e['dimensions']; a=e.get('rotation',[0,0,0])[1]
        w=abs(d['width']*math.cos(a))+abs(d['depth']*math.sin(a))
        dep=abs(d['width']*math.sin(a))+abs(d['depth']*math.cos(a))
        return [x-w/2,x+w/2,z-dep/2,z+dep/2]
    if e['type']=='primitive' and e['shape']=='box':
        x,y,z=e['position']; w,h,d=e['dimensions']; return [x-w/2,x+w/2,z-d/2,z+d/2]
    return None


def inside(x,z,r,tol=1e-5):
    return r[0]-tol<=x<=r[1]+tol and r[2]-tol<=z<=r[3]+tol


def top(e):
    return e['from'][1]+e.get('thickness',0) if e['type']=='floor' else e['position'][1]+e['thickness']


surfaces=[e for e in els if e['type'] in ['floor','roof']]


def supported(x,z,y):
    return any(abs(top(e)-y)<0.02 and inside(x,z,rect(e)) for e in surfaces)


check('JSON Schema', [f"{'/'.join(map(str,e.path))}: {e.message}" for e in Draft202012Validator(schema).iter_errors(bp)])
check('全局 ID 唯一', [i for i,n in Counter(e['id'] for e in els+comps).items() if n>1])
refs=[]
for e in els+comps:
    for k,v in e.items():
        if (k=='material' or k.endswith('Material')) and isinstance(v,str) and v not in bp['materials']:
            refs.append(f"{e['id']}.{k}={v}")
    for part in e.get('body',[]):
        if part.get('material') not in bp['materials']: refs.append(e['id']+'.body.material')
check('显式材料引用',refs)
positive=[]
for e in els:
    if e['type']=='primitive' and e['shape']=='box' and any(x<=0 for x in e['dimensions']): positive.append(e['id'])
check('box 正尺寸',positive)

openings=[]; host_errors=[]; overlaps=[]
for c in comps:
    if c['type'] not in ['door','window']: continue
    w=byid.get(c['parentWall'])
    if not w or w['type']!='wall': host_errors.append(c['id']); continue
    length=math.hypot(w['to'][0]-w['from'][0],w['to'][2]-w['from'][2])
    a,y,_=c['from']; width,height=c['width'],c['height']
    if a<0 or a+width>length+1e-5 or y<w['from'][1]-1e-5 or y+height>w['to'][1]+1e-5:
        host_errors.append(c['id'])
    openings.append(c)
for i,a in enumerate(openings):
    for b in openings[i+1:]:
        if a['parentWall']!=b['parentWall']: continue
        if min(a['from'][0]+a['width'],b['from'][0]+b['width'])>max(a['from'][0],b['from'][0])+1e-5 and min(a['from'][1]+a['height'],b['from'][1]+b['height'])>max(a['from'][1],b['from'][1])+1e-5:
            overlaps.append([a['id'],b['id']])
check('门窗宿主和边界',host_errors,count=len(openings))
check('同墙开口不重叠',overlaps)

stairs=[e for e in els if e['type']=='stair']; stair_errors=[]
for e in stairs:
    if abs((e['to'][1]-e['from'][1])-e['stepCount']*e['stepHeight'])>1e-4: stair_errors.append(e['id']+'升高')
    if abs(math.hypot(e['to'][0]-e['from'][0],e['to'][2]-e['from'][2])-e['stepCount']*e['stepDepth'])>1e-4: stair_errors.append(e['id']+'行程')
    for p in [e['from'],e['to']]:
        if not supported(p[0],p[2],p[1]): stair_errors.append(e['id']+'端点无支承')
half=byid['stair_half_landing']; landing=rect(half)
for e in stairs:
    end=e['to'] if e['id']=='stair_first' else e['from']
    if not inside(end[0]-e['width']/2,end[2],landing) or not inside(end[0]+e['width']/2,end[2],landing): stair_errors.append(e['id']+'平台宽度')
check('梯段升高/行程/端点/平台',stair_errors,
      step_height=stairs[0]['stepHeight'],step_depth=stairs[0]['stepDepth'],landing_top=top(half))
void_errors=[]
upper=[e for e in surfaces if e['type']=='floor' and abs(top(e)-design['levels']['upper'])<1e-5]
for v in design['voids']:
    for e in upper:
        a,b=v['rect'],rect(e)
        if min(a[1],b[1])-max(a[0],b[0])>1e-5 and min(a[3],b[3])-max(a[2],b[2])>1e-5: void_errors.append([v['id'],e['id']])
check('挑空与梯井没有二层楼板覆盖',void_errors)
roof=byid['main_roof']; living=design['voids'][0]['rect']
check('挑空上方有真实屋面',[] if inside(living[0],living[2],rect(roof)) and inside(living[1],living[3],rect(roof)) else ['缺少覆盖'])
terrace=byid['library_terrace_roof']; d=byid['terrace_connection']
check('露台门底与屋面板顶齐平',[] if abs(top(terrace)-d['from'][1])<1e-5 else ['门底不齐'],door_bottom=d['from'][1],terrace_top=top(terrace))

support_errors=[]
for e in els:
    if e['type']!='furniture': continue
    r=rect(e); y=e['position'][1]
    if not all(supported(x,z,y) for x in [r[0],r[1]] for z in [r[2],r[3]]): support_errors.append(e['id'])
check('家具名义占地四角有楼面支承',support_errors,scope='不包含原生家具突出名义尺寸的细部；不代表任意网格碰撞通过')

# 把各路线按 0.15m 步长、横向五点抽样。墙体只在真实门洞内放行。
# 此处假设可交互门已打开，不把封闭玻璃窗当作通路。
walls=[e for e in els if e['type']=='wall']
solids=[e for e in els if e['type']=='furniture' or (e['type']=='primitive' and e['shape']=='box')]
doors=[c for c in comps if c['type']=='door']


def wall_blocks(w,x,z,y,head):
    ax,ay,az=w['from']; bx,by,bz=w['to']; dx,dz=bx-ax,bz-az; length=math.hypot(dx,dz)
    along=((x-ax)*dx+(z-az)*dz)/length
    normal=abs((x-ax)*dz-(z-az)*dx)/length
    if not (0<=along<=length and normal<w['thickness']/2-1e-5 and by>y+0.05 and ay<y+head): return False
    return not any(c['parentWall']==w['id'] and c['from'][0]+c['frameWidth']<=along<=c['from'][0]+c['width']-c['frameWidth'] and c['from'][1]<=y+0.06 and c['from'][1]+c['height']-c['frameWidth']>=y+head for c in doors)


route_reports=[]
for route in design['routes']:
    blocked=set(); unsupported=0; samples=0
    for a,b in zip(route['points'],route['points'][1:]):
        dx,dz=b[0]-a[0],b[2]-a[2]; length=math.hypot(dx,dz); count=max(1,math.ceil(length/0.15))
        for i in range(count+1):
            for fraction in [-0.5,-0.25,0,0.25,0.5]:
                off=route['width']*fraction
                x=a[0]+dx*i/count-dz/length*off; z=a[2]+dz*i/count+dx/length*off
                y=a[1]; head=design['use_clearances']['route_headroom']; samples+=1
                if not supported(x,z,y): unsupported+=1
                for w in walls:
                    if wall_blocks(w,x,z,y,head): blocked.add(w['id'])
                for e in solids:
                    if not inside(x,z,rect(e),-1e-5): continue
                    if e['type']=='furniture': bottom=e['position'][1]; upper_y=bottom+e['dimensions']['height']
                    else: bottom=e['position'][1]-e['dimensions'][1]/2; upper_y=bottom+e['dimensions'][1]
                    if upper_y>y+0.05 and bottom<y+head: blocked.add(e['id'])
    route_reports.append(dict(id=route['id'],samples=samples,blocked_by=sorted(blocked),unsupported_samples=unsupported))
check('声明路线的净宽/净高/支承抽样', [r for r in route_reports if r['blocked_by'] or r['unsupported_samples']],
      routes=route_reports,scope='六条指定折线路线、直墙和名义家具/box；不含转角扫掠、任意构件、门开启扫掠及完整导航网格')

report=dict(file=str(TARGET),sha256=hashlib.sha256(TARGET.read_bytes()).hexdigest(),
            elements=len(els),components=len(comps),materials=len(bp['materials']),checks=checks,
            passed=all(c['passed'] for c in checks),
            limits=['不是完整碰撞/结构/消防验收','路线抽样不是全建筑可达性证明','栏杆完整性和家具实际细部另看剖切图'])
REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(passed=report['passed'],checks=len(checks),failed=[c for c in checks if not c['passed']]),ensure_ascii=False))
sys.exit(0 if report['passed'] else 1)
