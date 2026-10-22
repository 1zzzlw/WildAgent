"""只读核对交付关系；剖切只删除遮挡构件，不移动或改写保留构件。"""
import copy
import hashlib
import json
import math
import sys
from pathlib import Path
from jsonschema.validators import validator_for

ROOT=Path(__file__).resolve().parents[3]
target=Path(sys.argv[1]).resolve()
base=target.parent
bp=json.loads(target.read_text(encoding='utf-8'))
design=json.loads((base/'01-需求与设计'/'DesignDocument.json').read_text(encoding='utf-8'))
p=design['decisions']['authoring']; upper=.4+p['height']
elements=bp['geometry']['elements']; components=bp['geometry']['components']
rows={e['id']:e for e in elements+components}
layers=json.loads((base/'03-过程记录'/'构件分层.json').read_text(encoding='utf-8'))
sha=hashlib.sha256(target.read_bytes()).hexdigest()
baseline=json.loads((base/'05-效果图'/'render_manifest.json').read_text(encoding='utf-8'))
world=json.loads((base/'05-效果图'/'世界环境'/'world-render-manifest.json').read_text(encoding='utf-8'))
project=json.loads((base/'04-校验'/'最终项目校验.json').read_text(encoding='utf-8'))
assert baseline['inputSha256']==world['inputSha256']==project['sha256']==sha
assert baseline['compileErrors']==baseline['reconstructErrors']==baseline['unmappedMaterials']==0
assert not world['runtimeErrors'] and not project['schema_errors'] and not project['pipeline_error_steps']
bb=world['boundingBox']; size=[bb['max'][k]-bb['min'][k] for k in [0,2]]
assert all(abs(n-p['size'])<1e-5 for n in size),size
sign=rows['building_name']
assert sign['label']['text']==bp['meta']['name']==p['sign_text']
assert sign['shape']=='box' and abs(math.cos(sign['rotation'][1])+1)<1e-8
lights=[e for e in elements if 'lightSource' in e]
assert lights and all(e['lightSource']['intensity']>0 and e['lightSource']['initiallyOn'] for e in lights)

def rect(e):
    return [min(e['from'][0],e['to'][0]),min(e['from'][2],e['to'][2]),max(e['from'][0],e['to'][0]),max(e['from'][2],e['to'][2])]

def overlap(a,b):
    return max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))

def area(r):return (r[2]-r[0])*(r[3]-r[1])

floors=[e for e in elements if layers[e['id']]=='upper_floor']
traffic=[]
if p['floors']==2:
    stair=[e for e in elements if e['type']=='stair']
    assert len(stair)==2
    a,b=stair
    assert abs(a['from'][1]-.4)<1e-7 and abs(a['to'][1]-b['from'][1])<1e-7 and abs(b['to'][1]-upper)<1e-7
    hole=[a['from'][0]-a['width']/2-.08,a['from'][2],b['from'][0]+b['width']/2+.08,a['to'][2]+1.33]
    assert all(overlap(rect(e),hole)<1e-8 for e in floors)
    support=[rect(e) for e in floors if abs(e['from'][1]+e['thickness']-upper)<1e-7]
    arrival=b['to']; half=b['width']/2
    assert any(r[0]<=arrival[0]-half and r[2]>=arrival[0]+half and r[1]-1e-7<=arrival[2]<=r[3]+1e-7 for r in support)
    if p['kind']=='library':
        expected=24*20-area(hole)-5.6*6.8
    else:
        expected=20*14-area(hole)
    actual=sum(area(rect(e)) for e in floors)
    assert abs(actual-expected)<1e-7,(actual,expected)
    # 采样每跑踏步的宽度与板的交集，核对上方2m范围无实体水平板。
    samples=0
    horizontal=[(rect(e),e['from'][1]) for e in elements if e['type']=='floor']
    horizontal += [([e['position'][0]-e['span']/2,e['position'][2]-e['depth']/2,e['position'][0]+e['span']/2,e['position'][2]+e['depth']/2],e['position'][1]) for e in elements if e['type']=='roof']
    for flight in stair:
        for j in range(1,flight['stepCount']):
            t=j/flight['stepCount']
            x,y,z=[flight['from'][k]*(1-t)+flight['to'][k]*t for k in range(3)]
            tread=[x-flight['width']/2,z-.005,x+flight['width']/2,z+.005]
            assert not any(y+.03<bottom<y+2 and overlap(r,tread)>1e-8 for r,bottom in horizontal),(flight['id'],t)
            samples+=1
    traffic.append(dict(hole=hole,upper_floor_area=actual,expected_area=expected,headroom_samples=samples,minimum_checked_clearance_m=2,arrival_supported=True))
pool=None
if p['kind']=='villa':
    water=[e for e in elements if e.get('material')=='water']
    assert len(water)==1
    footprint=rect(water[0]);ground=[e for e in elements if layers[e['id']]=='site' and e['id'].startswith('site_')]
    assert ground and all(overlap(rect(e),footprint)<1e-8 for e in ground)
    bottom=next(e for e in elements if e['id'].startswith('pool_bottom'))
    depth=water[0]['from'][1]+water[0]['thickness']-bottom['from'][1]-bottom['thickness']
    assert depth>1 and bp['materials']['water']['ior']==1.333 and bp['materials']['water']['transmission']>=.9
    pool=dict(water_depth_m=depth,ground_slab_excavated=True,footprint=footprint)

roof_supports=[]
for roof in [e for e in elements if e['type']=='roof']:
    x,y,z=roof['position']
    footprint=[x-roof['span']/2,z-roof['depth']/2,x+roof['span']/2,z+roof['depth']/2]
    contacts=[]
    for e in elements:
        if e['type']=='wall' and abs(e['to'][1]-y)<1e-6:
            r=rect(e);t=e['thickness']/2
            r=[r[0]-t,r[1]-t,r[2]+t,r[3]+t]
        elif e['type']=='primitive' and e['shape']=='box' and layers[e['id']] in ['structure','roof_detail']:
            cx,cy,cz=e['position'];w,h,d=e['dimensions']
            if abs(cy+h/2-y)>1e-6:continue
            r=[cx-w/2,cz-d/2,cx+w/2,cz+d/2]
        else:continue
        if overlap(r,footprint)>1e-8:contacts.append(e['id'])
    assert len(contacts)>=2,(roof['id'],contacts)
    roof_supports.append(dict(roof=roof['id'],base_y=y,contacts_at_same_height=contacts,check='declared rectangular footprints and top elevations'))

schema=json.loads((ROOT/'wild-core'/'schema.json').read_text(encoding='utf-8'))
validator=validator_for(schema)(schema)
cuts=[]
for cut_name in (['首层','二层'] if p['floors']==2 else ['室内']):
    remove=set()
    for e in elements:
        layer=layers[e['id']]
        if layer in ['roof','roof_detail']:
            remove.add(e['id']);continue
        y=e.get('position',[0,e.get('from',[0,0,0])[1],0])[1]
        if cut_name=='首层' and (layer in ['wall_upper','upper_floor','upper_detail'] or layer in ['furniture','lighting'] and y>=upper-.05):
            remove.add(e['id'])
        elif cut_name=='二层' and (layer in ['site','landscape','signage','water','canopy','wall_ground','floor','stair','structure','facade'] or layer in ['furniture','lighting'] and y<upper-.05):
            remove.add(e['id'])
    for e in components:
        if e.get('parentWall') in remove:
            remove.add(e['id'])
        elif e['type']=='railing':
            y=e['path'][0][1]
            if cut_name=='首层' and y>=upper-.1 or cut_name=='二层' and y<upper-.1:remove.add(e['id'])
    cut=copy.deepcopy(bp)
    cut['geometry']['elements']=[e for e in elements if e['id'] not in remove]
    cut['geometry']['components']=[e for e in components if e['id'] not in remove]
    assert not list(validator.iter_errors(cut))
    assert all(e==rows[e['id']] for e in cut['geometry']['elements']+cut['geometry']['components'])
    dest=base/'06-剖切查看'/cut_name/(p['name']+'-'+cut_name+'.wild')
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(cut,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    cuts.append(dict(path=str(dest.relative_to(base)),source_sha256=sha,sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
                     removed_ids=sorted(remove),retained_elements_unchanged=True,schema_errors=0))
report=dict(wild_sha256=sha,design_sha256=hashlib.sha256((base/'01-需求与设计'/'DesignDocument.json').read_bytes()).hexdigest(),
    name=p['name'],site_size_m=size,size_scope=p['size_scope'],main_sign=sign['label']['text'],real_lights=len(lights),
    project_error_steps=project['pipeline_error_steps'],project_warning_steps=project['pipeline_warning_steps'],
    reconstruction_warnings=[d for d in world['diagnostics'] if d['level']=='warning'],traffic=traffic,pool=pool,roof_supports=roof_supports,cuts=cuts,
    baseline_context=baseline['contextSha256'],render_hashes_match=True,runtime_errors=world['runtimeErrors'],
    limits=['剖切是查看副本，保留构件坐标不变；不把去顶后的屋面缺失警告当成完整建筑结论。','净空复核检查水平板与楼梯踏步采样；不是建筑结构承载、安全或规范认证。','审美质量依据真实渲染查看，最终仍由用户评价。'])
(base/'04-校验'/'交付关系核对.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='cuts'},ensure_ascii=False,indent=2))
