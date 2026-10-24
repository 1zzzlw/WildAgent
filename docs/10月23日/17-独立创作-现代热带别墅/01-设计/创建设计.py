"""固定本次设计事实并按项目当前 DesignDocument 验证，不调用生成 skill。"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'wild-server'))
from app.design.contracts import DesignDocument

def wall(id, a, b, material='plaster', thickness=.24):
    return dict(id=id, a=a, b=b, material=material, thickness=thickness)

walls = [
    wall('west_front', [-11,-5], [-5,-5]),
    wall('west_outer', [-11,7], [-11,-5]),
    wall('west_back', [-5,7], [-11,7]),
    wall('west_court', [-5,-5], [-5,3]),
    wall('east_front', [5,-5], [11,-5]),
    wall('east_outer', [11,-5], [11,7]),
    wall('east_back', [11,7], [5,7]),
    wall('east_court', [5,3], [5,-5]),
    wall('hall_back', [5,7], [-5,7]),
    wall('hall_court', [-5,3], [5,3]),
    wall('bedroom_corridor', [6.6,-5], [6.6,3.6], thickness=.16),
    wall('bedrooms_divider', [6.6,-.6], [11,-.6], thickness=.16),
    wall('bedrooms_back', [6.6,3.6], [11,3.6], thickness=.16),
    wall('bathroom_side', [8.8,3.6], [8.8,7], thickness=.16),
]

# id, type, host, along-wall start, width, bottom above FFL, height, finish
openings = [
    ['living_front','window','west_front',.8,4.4,.45,2.35,'glass'],
    ['living_outer','window','west_outer',7.0,3.8,.8,1.8,'glass'],
    ['kitchen_outer','window','west_outer',.7,3.3,1.15,1.45,'glass'],
    ['kitchen_back','window','west_back',1.0,4.0,1.15,1.45,'glass'],
    ['living_court','door','west_court',.65,3.0,0,2.65,'glass'],
    ['dining_court','window','west_court',4.8,2.5,.45,2.2,'glass'],
    ['master_front','window','east_front',2.2,3.0,.75,1.9,'glass'],
    ['master_outer','window','east_outer',.9,2.8,.85,1.8,'glass'],
    ['guest_outer','window','east_outer',5.2,2.8,.85,1.8,'glass'],
    ['bath_outer','window','east_outer',9.4,1.6,1.7,.75,'frosted'],
    ['study_back','window','east_back',2.7,2.5,.8,1.85,'glass'],
    ['corridor_court','window','east_court',.7,3.0,.65,2.0,'glass'],
    ['corridor_entry','door','east_court',5.5,1.25,0,2.5,'glass'],
    ['main_entry','door','hall_court',3.8,2.4,0,2.65,'wood'],
    ['hall_left','window','hall_court',.8,2.2,.55,2.1,'glass'],
    ['hall_right','window','hall_court',7.0,2.2,.55,2.1,'glass'],
    ['hall_back_window','window','hall_back',2.0,6.0,.65,2.0,'glass'],
    ['master_door','door','bedroom_corridor',2.8,.95,0,2.25,'wood'],
    ['guest_door','door','bedroom_corridor',6.9,.95,0,2.25,'wood'],
    ['bath_door','door','bathroom_side',1.1,.9,0,2.25,'wood'],
]
facade = dict(bays=1, entrance_bay=None, ground_pattern=['empty'], upper_pattern=['empty'])
volumes = [
    dict(id='west', role='客餐厨', x=-11,z=-5,width=6,depth=12,start_floor=1,end_floor=1),
    dict(id='east', role='两卧卫浴书桌区', x=5,z=-5,width=6,depth=12,start_floor=1,end_floor=1),
    dict(id='hall', role='横向门厅连接体', x=-5,z=3,width=10,depth=4,start_floor=1,end_floor=1),
]
rooms = [
    dict(id='living', name='起居', bounds=[-10.88,-4.88,-5.12,.1]),
    dict(id='dining', name='餐厅', bounds=[-10.88,.1,-5.12,3.4]),
    dict(id='kitchen', name='开放厨房', bounds=[-10.88,3.4,-5.12,6.88]),
    dict(id='hall', name='门厅及连接通道', bounds=[-5,3.12,5,6.88]),
    dict(id='corridor', name='卧室走廊', bounds=[5.12,-4.88,6.52,3.6]),
    dict(id='master', name='主卧', bounds=[6.68,-4.88,10.88,-.68]),
    dict(id='guest', name='客卧', bounds=[6.68,-.52,10.88,3.52]),
    dict(id='study', name='书桌区', bounds=[5,3.68,8.72,6.88]),
    dict(id='bath', name='卫浴', bounds=[8.88,3.68,10.88,6.88]),
]
data = dict(
    schema_version='design/1.0', design_id='palm-court-161231', session_id='independent-20261023',
    revision=2, status='draft',
    requirements=dict(source_request='随机一种别墅；不用创建蓝图skill完成可渲染WILD，完成后更新项目skill，记录全部流程。',
                      building_type='villa', profile='custom', style_intent=['现代热带别墅']),
    decisions=dict(
        kind='architecture', concept='棕影水院：低矮双翼、深檐与中央泳池的热带庭院住宅',
        massing=dict(shape='U',width=22,depth=12,floors=1,modeled_floors=1,floor_height=3.32,symmetry=False),
        complexity=dict(level='detailed',min_volumes=3,min_detail_packages=4,target_structural_elements=30,
                        grid_bays=[3,3],reason='用围庭、阴影层次、门窗收口和可用空间体现精细度'),
        volumes=volumes, structural_grid=dict(system='墙体与檐下柱组合',x_bays=3,z_bays=3),
        envelope=dict(system='solid_wall'),facades={f:facade for f in ['front','back','left','right']},
        roof=dict(type='hip',overhang=1.0,ridge_axis='z',volumes=[dict(volume='hall',type='flat',overhang=1.0)]),
        circulation=dict(vertical_strategy='single_level',route='前庭台阶→泳池西侧通路→中央门厅→客餐厨或卧室走廊'),
        materials=dict(keywords=['暖白灰泥','深色金属坡顶','柚木','浅色石材','青蓝池水']),
        detail_packages=['连续檐底及封边','入口格栅','池壁池底及石材压边','家具与照明'],
        design_intent=dict(goals=['可直接渲染','完整两卧住宅','深遮阴与围庭'],assumptions=['单层','28×22米地块','入口朝负Z'],
                           spatial_strategy='西公共、东私密、北连通、南围庭',composition='两座四坡顶翼楼加低平顶横厅',
                           material_strategy='灰泥主墙、木檐底、石材基座、深色框与屋面',selected_systems=['wall','floor','hip roof','door/window']),
        # 作者展开器的设计输入，不宣称后端通用编译器会消费这些扩展字段。
        authoring=dict(name='棕影水院-现代热带别墅',seed=161231,site=[-14,-10,14,12],
                       ffl=.18,wall_top=3.5,roof_eave=3.75,roof_thickness=.18,roof_rise=1.5,
                       courtyard=[-5,-5,5,3],pool=[-2,-3,2,1],pool_bottom=-1.12,water_level=.04,
                       rooms=rooms,walls=walls,openings=openings),
        floor_layouts=[dict(floor=1,level=.18,rooms=[],walls=[])],
        design_rationale=['共用界面不重复建墙，三体量室内在后厅连通','东侧走廊净宽1.4m，卧室分别设门','坡顶下设完整天花与檐底，不声明可用阁楼']),
)
document = DesignDocument.model_validate(data)
HERE.mkdir(parents=True, exist_ok=True)
(HERE/'DesignDocument.json').write_text(document.model_dump_json(indent=2), encoding='utf-8')
(HERE/'设计校验.json').write_text(json.dumps(dict(ok=True,contract='app.design.contracts.DesignDocument',
    note='Pydantic契约通过；详细平面在decisions.authoring中，由本案例展开器消费；未运行后端Agent编译。'),ensure_ascii=False,indent=2),encoding='utf-8')
print('DesignDocument validated and saved')
