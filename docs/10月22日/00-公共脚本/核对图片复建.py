"""核对设计落实、照片特征、楼梯/洞口，并制作只删遮挡项的逐层查看副本。"""
import copy
import hashlib
import json
import math
import sys
from pathlib import Path
from jsonschema.validators import validator_for

ROOT=Path(__file__).resolve().parents[3]
base=Path(sys.argv[1]).resolve();target=next(base.glob('*.wild'))
raw=target.read_bytes();bp=json.loads(raw);doc=json.loads((base/'01-需求与设计/DesignDocument.json').read_text(encoding='utf-8'))
p=doc['decisions']['authoring'];F=p['base'];H=p['height']
layers=json.loads((base/'03-过程记录/构件分层.json').read_text(encoding='utf-8'))
compile_record=json.loads((base/'03-过程记录/编译记录.json').read_text(encoding='utf-8'))
rows={e['id']:e for e in bp['geometry']['elements']+bp['geometry']['components']}
sha=hashlib.sha256(raw).hexdigest()
project=json.loads((base/'04-校验/最终项目校验.json').read_text(encoding='utf-8'))
render=json.loads((base/'05-效果图/render_manifest.json').read_text(encoding='utf-8'))
photo=json.loads((base/'05-效果图/参考视角/photo-render-manifest.json').read_text(encoding='utf-8'))
assert sha==compile_record['wild_sha256']==project['sha256']==render['inputSha256']==photo['inputSha256']
assert not project['schema_errors'] and not project['pipeline_error_steps']
assert render['compileErrors']==render['reconstructErrors']==render['unmappedMaterials']==0
assert not photo['runtimeErrors'] and not any(d['level']=='error' for d in photo['diagnostics'])
scene_size=[photo['boundingBox']['max'][k]-photo['boundingBox']['min'][k] for k in [0,2]]
assert all(abs(s-(32 if p['recipe']=='stone' else 16))<1e-5 for s in scene_size),scene_size

def rect(e):return [min(e['from'][0],e['to'][0]),min(e['from'][2],e['to'][2]),max(e['from'][0],e['to'][0]),max(e['from'][2],e['to'][2])]
def area(r):return (r[2]-r[0])*(r[3]-r[1])
def overlap(a,b):return max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))

floors=[e for e in bp['geometry']['elements'] if e['type']=='floor']
hole=compile_record['geometry_evidence']['stair_hole']
upper_floor_layer='floor_2' if p['recipe']=='stone' else 'floor_3'
upper_slabs=[e for e in floors if layers[e['id']]==upper_floor_layer]
assert all(overlap(rect(e),hole)<1e-8 for e in upper_slabs)
expected=(12.6*10.2 if p['recipe']=='stone' else 6.1*4.75)-area(hole)
actual=sum(area(rect(e)) for e in upper_slabs)
assert abs(expected-actual)<1e-7,(expected,actual)
samples=0;arrivals=[]
for stair in [e for e in bp['geometry']['elements'] if e['type']=='stair']:
    for key in ['from','to']:
        x,y,z=stair[key];half=stair['width']/2
        # 本稿均为Z方向直跑，支承面必须覆盖完整梯宽，而不是仅覆盖中心点。
        support=[e['id'] for e in floors if abs(e['from'][1]+e['thickness']-y)<1e-6 and
            min(e['from'][0],e['to'][0])<=x-half+1e-7 and max(e['from'][0],e['to'][0])>=x+half-1e-7 and
            min(e['from'][2],e['to'][2])-1e-7<=z<=max(e['from'][2],e['to'][2])+1e-7]
        assert support,(stair['id'],key,stair[key])
        arrivals.append(dict(stair=stair['id'],endpoint=key,position=stair[key],support=support))
    for j in range(1,stair['stepCount']):
        t=j/stair['stepCount'];x,y,z=[stair['from'][k]*(1-t)+stair['to'][k]*t for k in range(3)]
        tread=[x-stair['width']/2,z-.003,x+stair['width']/2,z+.003]
        assert not any(y+.03<e['from'][1]<y+2 and overlap(tread,rect(e))>1e-8 for e in floors),(stair['id'],t)
        samples+=1

sign=rows['building_name']['label']['text']
features={}
if p['recipe']=='stone':
    for n in range(2):
        ids=[e['id'] for e in bp['geometry']['components'] if e.get('parentWall')=='main'+str(n)+'_front']
        assert len(ids)==4,(n,ids)
        features['front_row_'+str(n+1)]=ids
    features['two_tall_east_windows']=[rows['east_upper'+str(j)]['id'] for j in range(2)]
    features['left_glass_terrace']=[e['id'] for e in bp['geometry']['elements'] if e['id'].startswith('wing_terrace_pane')]
    features['six_wide_steps']=[rows['entry_step'+str(j)]['id'] for j in range(6)]
    features['four_skylight_panes']=[rows['skylight_glass_'+s]['id'] for s in ['front','back','left','right']]
    sky=compile_record['geometry_evidence']['skylight_hole']
    assert all(overlap(rect(e),sky)<1e-8 for e in floors if layers[e['id']]=='roof_planting')
    # 天窗三角棱柱的平面投影底边/顶点由作者参数推导，框梁顶=主屋面底。
    for j in range(4):
        e=rows['roof_opening_header'+str(j)]
        assert abs(e['from'][1]+e['height']/2-compile_record['geometry_evidence']['roof_base'])<1e-6
    features['roof_opening_headers']=4
else:
    assert sign=='Forest\nCafe\nCafe'
    stair=rows['outside_stair'];land=rows['outside_landing'];door=rows['stair_arrival_door'];wall=rows[door['parentWall']]
    assert math.dist(stair['to'],compile_record['geometry_evidence']['exterior_arrival'])<1e-7
    assert stair['stepCount']==18
    a,b=wall['from'],wall['to'];length=math.hypot(b[0]-a[0],b[2]-a[2])
    start=door['from'][0];w=door['width']
    door_z=sorted([a[2]+(b[2]-a[2])*s/length for s in [start,start+w]])
    lr=rect(land)
    assert lr[1]<=door_z[0] and door_z[1]<=lr[3]
    # 检查露台桌椅均在实际外摆板内，防止前后向摆椅伸出栏杆。
    for prefix in ['terrace_table','terrace_chair_left','terrace_chair_right']:
        for e in bp['geometry']['elements']:
            if not e['id'].startswith(prefix):continue
            x,y,z=e['position'];w,h,d=e['dimensions'];angle=e.get('rotation',[0,0,0])[1]
            dx=(abs(math.cos(angle))*w+abs(math.sin(angle))*d)/2
            dz=(abs(math.sin(angle))*w+abs(math.cos(angle))*d)/2
            assert -8.6<=x-dx and x+dx<=-2.25 and z-dz>=0 and z+dz<=1.4,(e['id'],e)
    features=dict(three_occupied_floors=True,english_sign=sign,exterior_stair_steps=18,landing_depth=lr[3]-lr[1],
        arrival_door_z=door_z,terrace_furniture_inside_slab=True,
        vines=sum(e['id'].endswith('_stem') and 'vine' in e['id'] for e in bp['geometry']['elements']),
        dark_roof_louver_layers=6)
    cheek=rows['stair_solid_cheek95'];end_wall=rows['landing_outer_wall']
    joint_z=cheek['position'][2]+cheek['dimensions'][2]/2
    assert joint_z>=end_wall['from'][2] and abs(cheek['position'][0]-end_wall['from'][0])<1e-6
    guard_height=end_wall['to'][1]-(land['from'][1]+land['thickness'])
    assert abs(guard_height-.9)<1e-6
    features['outside_parapet_joint']=dict(cheek_end_z=joint_z,wall_start_z=end_wall['from'][2],overlap_m=joint_z-end_wall['from'][2],
        height_above_landing_m=guard_height,intent='露天楼梯防护矮墙，顶部不需要建筑屋顶')

schema=json.loads((ROOT/'wild-core/schema.json').read_text(encoding='utf-8'));validator=validator_for(schema)(schema)
cuts=[]
for level in range(1,p['floors']+1):
    name=['首层','二层','三层'][level-1];remove=set()
    for e in bp['geometry']['elements']:
        layer=layers[e['id']]
        # 只保留当前层壳体与家具；地面层额外保留场地。外楼梯在二层副本中保留。
        keep=layer in [f'floor_{level}',f'wall_{level}',f'facade_{level}',f'furniture_{level}',f'lighting_{level}']
        if level==1 and layer in ['site','foundation','court','entry_stair','landscape']:keep=True
        if level==1 and layer=='stair' and p['recipe']=='stone':keep=True
        if level==2 and layer in ['terrace_2','roof_wing']:keep=True
        if level==2 and p['recipe']=='forest' and layer in ['outside_stair','stair','edge_1']:keep=True
        if level==3 and layer in ['roof_garden','edge_2']:keep=True
        if layer=='planting':
            y=e.get('position',[0,0,0])[1]
            keep=F+(level-1)*H-.25<=y<F+level*H-.15
        if not keep:remove.add(e['id'])
    for e in bp['geometry']['components']:
        if e.get('parentWall') in remove:remove.add(e['id'])
        elif e['type']=='railing':
            y=e['path'][0][1]
            if not (F+(level-1)*H-.1<=y<F+level*H-.1):remove.add(e['id'])
    cut=copy.deepcopy(bp)
    for key in ['elements','components']:cut['geometry'][key]=[e for e in bp['geometry'][key] if e['id'] not in remove]
    assert not list(validator.iter_errors(cut))
    assert all(e==rows[e['id']] for e in cut['geometry']['elements']+cut['geometry']['components'])
    path=base/'06-剖切查看'/name/(p['name']+'-'+name+'.wild');path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes((json.dumps(cut,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    cuts.append(dict(path=path.relative_to(base).as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),source_sha256=sha,
        removed_ids=sorted(remove),retained_elements_unchanged=True))
report=dict(source_sha256=sha,design_sha256=hashlib.sha256((base/'01-需求与设计/DesignDocument.json').read_bytes()).hexdigest(),
    name=p['name'],site_size_m=scene_size,features=features,stair_hole=hole,upper_floor_area=actual,expected_upper_floor_area=expected,
    stair_endpoints=arrivals,headroom_samples=samples,minimum_floor_clearance_checked_m=2,
    project_error_steps=project['pipeline_error_steps'],project_warning_steps=project['pipeline_warning_steps'],
    renderer_warnings=[d for d in photo['diagnostics'] if d['level']=='warning'],runtime_errors=photo['runtimeErrors'],
    cuts=cuts,limits=['源图无尺寸，背面/室内为补全设计。','楼梯检查为水平板净空采样与端点承托，不是承载或规范认证。','人物、宠物、照片背景、密集林冠与镜头景深未复制；不把渲染图后期处理成参考照片。'])
(base/'04-校验/设计落实与交通复核.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ['cuts','stair_endpoints']},ensure_ascii=False,indent=2))
