"""只对本次已输出几何复算装配；副本仅删除遮挡物。"""
import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path

base=Path(__file__).resolve().parents[1]
source=base/'栖光别墅-单文档生成.wild'
raw=source.read_bytes()
bp=json.loads(raw)
rows={e['id']:e for k in ['elements','components'] for e in bp['geometry'][k]}
layers=json.loads((base/'03-过程记录/构件分层.json').read_bytes())
revision=__import__('sys').argv[1]
fingerprint=hashlib.sha256(raw).hexdigest()
def rect(e):
    return [min(e['from'][0],e['to'][0]),max(e['from'][0],e['to'][0]),
            min(e['from'][2],e['to'][2]),max(e['from'][2],e['to'][2])]
def overlap(a,b):
    return max(0,min(a[1],b[1])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[2],b[2]))
def contains(e,x,z):
    a,b,c,d=rect(e)
    return a-1e-7<=x<=b+1e-7 and c-1e-7<=z<=d+1e-7
def top(e): return e['from'][1]+e['thickness']

# 实际板片的洞口面积、无重叠与上下皮。
floors=[e for e in bp['geometry']['elements'] if e['type']=='floor']
upper=[e for e in floors if layers[e['id']]=='floor_l2']
hole=[.45,3.55,6.8,11.1]
for j,e in enumerate(upper):
    assert abs(top(e)-3.74)<1e-7
    assert overlap(rect(e),hole)<1e-7
    for other in upper[j+1:]: assert overlap(rect(e),rect(other))<1e-7
area=sum((rect(e)[1]-rect(e)[0])*(rect(e)[3]-rect(e)[2]) for e in upper)
expected=11.06*9.26+10.26*4+5.2*.26-(3.55-.45)*(11.1-6.8)
assert abs(area-expected)<1e-6,(area,expected)

stairs=[e for e in bp['geometry']['elements'] if e['type']=='stair']
headroom_samples=0
for stair in stairs:
    n=stair['stepCount'];p=stair['from'];q=stair['to']
    assert abs(q[1]-p[1]-n*stair['stepHeight'])<1e-7
    distance=math.hypot(q[0]-p[0],q[2]-p[2])
    assert abs(distance-n*stair['stepDepth'])<1e-7
    ux,uz=(q[0]-p[0])/distance,(q[2]-p[2])/distance
    for step in range(n):
        for width_fraction in [-.48,0,.48]:
            t=(step+.5)/n
            x=p[0]+(q[0]-p[0])*t-uz*stair['width']*width_fraction
            z=p[2]+(q[2]-p[2])*t+ux*stair['width']*width_fraction
            y=p[1]+(step+1)*stair['stepHeight']
            for floor in floors:
                if contains(floor,x,z) and floor['from'][1]>y+1e-7:
                    assert floor['from'][1]-y>=2.0-1e-7,(stair['id'],step,floor['id'])
            headroom_samples+=1
a,b=rows['stair_a'],rows['stair_b']
mid=rows['stair_mid']
assert abs(a['to'][1]-top(mid))<1e-7 and abs(b['from'][1]-top(mid))<1e-7
assert a['to'][2]==mid['from'][2]==b['from'][2]
assert abs(b['to'][1]-3.74)<1e-7 and b['to'][2]==hole[2]
platform_depth=hole[2]-rows['l1_wall_study_back']['from'][2]-.08
assert platform_depth>=1.3

# 门窗宿主、同墙洞口间距；从实际对象投影还原中心。
openings=[e for e in bp['geometry']['components'] if e['type'] in {'door','window'}]
opening_groups={}
for e in openings:
    host=rows[e['parentWall']];p=host['from'];q=host['to'];s,y,o=e['from']
    length=math.hypot(q[0]-p[0],q[2]-p[2]);ux,uz=(q[0]-p[0])/length,(q[2]-p[2])/length
    assert s>=0 and s+e['width']<=length+1e-7
    assert y>=p[1]-1e-7 and y+e['height']<=q[1]+1e-7
    assert e['frameDepth']<=host['thickness']+.12+1e-7
    opening_groups.setdefault(host['id'],[]).append(e)
for host,items in opening_groups.items():
    for j,e in enumerate(items):
        for other in items[j+1:]:
            ea=[e['from'][0],e['from'][0]+e['width'],e['from'][1],e['from'][1]+e['height']]
            eb=[other['from'][0],other['from'][0]+other['width'],other['from'][1],other['from'][1]+other['height']]
            assert overlap(ea,eb)<1e-7,(e['id'],other['id'])

# 交通点在真实楼面上：入口、楼梯到达后向东穿门、上层走道至两卧室/卫浴。
routes={
    '二层到达转向并出梯间':[(2.85,6.60),(3.3,5.92),(4.12,5.92),(5.2,5.92)],
    '二层到主卧及露台门内':[(5.2,5.92),(5.7,5.0),(6.65,5.0),(8.5,4.0),(8.5,3.3)],
    '二层到次卧':[(5.2,5.92),(5.2,8.86),(6.7,8.86),(8.2,8.86)],
    '二层到卫生间':[(5.2,5.92),(5.25,9.30),(5.25,9.55)],
}
for name,points in routes.items():
    for x,z in points:
        assert any(contains(f,x,z) for f in upper),(name,x,z)
guard=rows['terrace_guard']['path']
assert guard[0]==[6.0,3.74,3] and guard[-1]==[10.8,3.74,3.02]
report=dict(source_sha256=fingerprint,revision=revision,passed=True,
    upper_slab_parts=len(upper),upper_slab_area=area,expected_area=expected,
    hole_clear=True,slab_parts_do_not_overlap=True,stair_count=len(stairs),
    tread_headroom_samples=headroom_samples,headroom_checked_across_tread_width=True,
    front_platform_net_depth=platform_depth,opening_count=len(openings),opening_ranges_and_overlap_passed=True,
    floor_route_points=routes,terrace_end_returns_present=True,
    limitation='离散点和轴对齐板关系复核，不是完整人员导航或施工审查。墙门关系另由后端检查和实际剖切看图。')
out=base/'04-校验'/(revision+'空间复核.json')
assert not out.exists()
out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

cuts=[]
for name,remove_layers in [
    ('首层',{'floor_l2','walls_l2','components_l2','facade_l2','furniture_l2','lighting_l2',
             'roof','roof_detail','terrace'}),
    ('二层',{'roof','roof_detail'})]:
    cut=deepcopy(bp);removed=[]
    for kind in ['elements','components']:
        kept=[]
        for e in cut['geometry'][kind]:
            remove=layers[e['id']] in remove_layers
            if name=='首层' and layers[e['id']]=='landscape' and e.get('position',[0,0,0])[1]>3.5:
                remove=True
            if remove: removed.append(e['id'])
            else: kept.append(e)
        cut['geometry'][kind]=kept
    wallids={e['id'] for e in cut['geometry']['elements'] if e['type']=='wall'}
    kept=[]
    for e in cut['geometry']['components']:
        if e.get('parentWall') and e['parentWall'] not in wallids:removed.append(e['id'])
        else:kept.append(e)
    cut['geometry']['components']=kept
    cut['meta']['name']+=' · '+name+'查看副本'
    data=(json.dumps(cut,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8')
    folder=base/'06-剖切查看'/revision/name
    folder.mkdir(parents=True,exist_ok=False)
    (folder/'剖切.wild').write_bytes(data)
    origin=dict(source_sha256=fingerprint,copy_sha256=hashlib.sha256(data).hexdigest(),
        removed_ids=removed,kept_geometry_unchanged=True)
    (folder/'来源.json').write_text(json.dumps(origin,ensure_ascii=False,indent=2),encoding='utf-8')
    cuts.append(dict(name=name,kept=sum(len(cut['geometry'][k]) for k in ['elements','components']),removed=len(removed)))
print(json.dumps(dict(spatial_passed=True,front_platform_net_depth=platform_depth,
    headroom_samples=headroom_samples,cuts=cuts),ensure_ascii=False,indent=2))
