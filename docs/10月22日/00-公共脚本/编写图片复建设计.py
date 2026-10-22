"""按本次对话两张参考图片写入独立设计；只保存设计，不生成WILD。"""
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'wild-server'))
from app.design.contracts import DesignDocument
from app.design.compilation import project_drawing

CATALOG={
 'stone':dict(folder='11-图片复建-石光庭院',name='林庭石光馆',kind='courtyard_gallery',site=[-16,-12,16,20],height=3.75,base=.8,floors=2,
    volumes=[dict(id='main',x=-2.5,z=0,width=12.6,depth=10.2,start_floor=1,end_floor=2),dict(id='wing',x=-9.5,z=-2.8,width=7,depth=8.8,start_floor=1,end_floor=1)],
    concept='按图一复建高低错落的暖石庭院建筑：右侧两层四组高窗，左侧前伸木饰单层翼与透明屋顶露台，主屋面绿化及方形天窗，前庭宽阶。',
    observed=['右高左低的两个正交体量，非对称正面','浅米色石材前立面与白色右侧墙','上下对应的四组狭长落地窗，中央有较宽实墙','左翼大窗、横向木饰及无粗立柱玻璃露台','主屋面低女儿墙、绿色地被与方形玻璃天窗','宽台阶、台阶侧短墙、两只矩形花盆和林地草坪'],
    inferred=['图中无标尺，层高3.75米、主楼12.6×10.2米、翼楼7×8.8米为比例推定','背面、室内和内楼梯不是照片事实，补为阅读、会客和服务空间','不复制人物、宠物、界面按钮、水印或摄影虚化；使用真实三维几何'],
    materials='暖石、白灰泥、木饰、细深铜框、清玻璃与屋面地被',
    camera=dict(position=[30,22,-31],target=[.5,3.2,2.2],fov=39),
    sign='林庭石光馆',stair=dict(x=-1.52,z=5.6,width=1.05,gap=.16,run=3,landing=1.1,rise=3.75,steps=12),
    skylight=[1.8,2.5,5.8,6.1]),
 'forest':dict(folder='12-图片复建-ForestCafe',name='Forest Cafe',kind='cafe',site=[-3,-4,13,12],height=3.2,base=.24,floors=3,
    volumes=[dict(id='left',x=0,z=0,width=2.25,depth=7.6,start_floor=1,end_floor=2),
             dict(id='ground',x=2.25,z=0,width=6.35,depth=7.6,start_floor=1,end_floor=1),
             dict(id='middle',x=2.25,z=1.4,width=6.35,depth=6.2,start_floor=2,end_floor=2),
             dict(id='upper',x=2.25,z=2.65,width=6.1,depth=4.75,start_floor=3,end_floor=3)],
    concept='按图二复建三层森林咖啡屋：左侧白色招牌塔、逐层退后的细框玻璃空间、右侧室外宽阶、露台黑色细栏杆、层层花池及垂坠藤蔓。',
    observed=['紧凑的三层建筑，白色实体边框和深铜细框玻璃','左侧较高白墙竖向排布Forest / Cafe / Cafe','二层前露台与黑色细栏杆，三层向后退进','右侧沿进深上行的室外直跑楼梯，外侧白色斜顶矮墙','顶层深色叠片檐口、屋顶植物及垂坠藤蔓','每层可见桌椅、吊灯、暖黄色室内光与入口小黑板'],
    inferred=['图中无标尺，按层高3.2米、主要宽度8.6米推定，地块16×16米','背面和第三层交通不可见，二至三层内楼梯布置在后侧并留洞','保留图中的英文标识；不把参考图作为纹理贴在空盒子上'],
    materials='白色细砂灰泥、深铜窗框、透明玻璃、暖木、黑铁栏杆与多层植物',
    camera=dict(position=[20.5,14.1,-22],target=[4.4,4.5,3.1],fov=34),
    sign='Forest\nCafe\nCafe',stair=dict(x=3.02,z=4,width=.95,gap=.16,run=2.2,landing=1.0,rise=3.2,steps=11),
    exterior_stair=dict(x=9.45,z=-.6,width=1.4,run=5.76,rise=3.2,steps=18,landing_end=7.6)),
}
p=CATALOG[sys.argv[1]]
base=ROOT/'docs/10月22日'/p['folder']
for sub in ['01-需求与设计','02-生成脚本','03-过程记录/命令记录','04-校验','05-效果图','06-剖切查看']:
    (base/sub).mkdir(parents=True,exist_ok=True)
p['mirror_x']=True
p['camera']['position'][0]*=-1;p['camera']['target'][0]*=-1
if sys.argv[1]=='stone':
    p['camera']['position']=[-24,15.7,-24]
    p['camera']['target']=[-.5,3.6,1.0]
else:
    p['camera']['position']=[-19,12.5,-19.5]
    p['camera']['target']=[-4.9,4.7,3.2]
vols=[{**v,'x':-v['x']-v['width']} for v in p['volumes']]
x0=min(v['x'] for v in vols);x1=max(v['x']+v['width'] for v in vols)
z0=min(v['z'] for v in vols);z1=max(v['z']+v['depth'] for v in vols)
facade=dict(bays=4,ground_pattern=['window','door','window','window'],upper_pattern=['window']*4)
old_path=base/'01-需求与设计/DesignDocument.json'
revision=1+json.loads(old_path.read_text(encoding='utf-8'))['revision'] if old_path.exists() else 1
if old_path.exists():
    (base/'01-需求与设计'/f'DesignDocument-r{revision-1}.json').write_bytes(old_path.read_bytes())
doc=DesignDocument.model_validate(dict(schema_version='design/1.0',design_id='photo-'+sys.argv[1]+'-20261022',session_id='codex-photo-reconstruction',revision=revision,status='draft',
    requirements=dict(source_request='根据用户本轮上传的第'+('一' if sys.argv[1]=='stone' else '二')+'张图片高仿，生成可导入WILD并记录实际流程。',building_type=p['kind'],profile='detailed',style_intent=[p['materials']]),
    decisions=dict(kind='architecture',concept=p['concept'],
        massing=dict(shape='asymmetric_stepped',width=x1-x0,depth=z1-z0,floors=p['floors'],modeled_floors=p['floors'],floor_height=p['height']),
        complexity=dict(level='detailed',min_volumes=len(vols),min_detail_packages=6,target_structural_elements=180,grid_bays=[4,3],reason='按照片轮廓、开间、边框深度、露台和绿化组织细节'),
        volumes=vols,structural_grid=dict(system='frame',x_bays=4,z_bays=3),envelope=dict(system='solid_wall'),
        facades={face:facade for face in ['front','back','left','right']},roof=dict(type='flat',overhang=.15),
        circulation=dict(vertical_strategy='stair'),detail_packages=['立面深框及收边','真实玻璃洞口','退台与栏杆','楼梯与楼板开口','种植与藤蔓','招牌与真实灯光'],
        floor_layouts=[dict(floor=i+1,level=p['base']+i*p['height'],rooms=[],walls=[]) for i in range(p['floors'])],
        design_rationale=p['observed'],authoring=dict(**p,recipe=sys.argv[1],coordinate_note='作者几何先在局部工作坐标装配，再整体镜像X；设计volumes已记录镜像后的世界坐标。文字保持正常阅读方向。',source='本轮对话附件；工具未提供原图的本地路径，未虚构原图副本')),
    constraints=[dict(id='photo_features',kind='user_hard',target='building',expression='正面体量、窗组、材质分工、露台和楼梯按参考特征逐项复核',check='manual')]))
(base/'01-需求与设计/DesignDocument.json').write_text(doc.model_dump_json(indent=2),encoding='utf-8')
(base/'01-需求与设计/主体投影.json').write_text(project_drawing(doc).model_dump_json(indent=2),encoding='utf-8')
text='# '+p['name']+' · 图片复建设计\n\n'+p['concept']+'\n\n## 图片可见事实\n\n'+'\n'.join('- '+v for v in p['observed'])+'\n\n## 推定与补全\n\n'+'\n'.join('- '+v for v in p['inferred'])+'\n\n## 创建与验收\n\n先保留当前DesignDocument，再由本次图片专用作者脚本装配详细WILD；不调用Agent或模型API，不修改引擎适配某栋建筑。运行Schema、后端流水线、Core重建，再查看实际WebGL的参考视角、四视图、日夜和剖切。高仿以可见建筑特征为准，不承诺摄影背景、树叶密度和景深达到原图的照片效果。\n'
(base/'01-需求与设计/图片拆解与设计.md').write_text(text,encoding='utf-8')
print(json.dumps(dict(design=str(base/'01-需求与设计/DesignDocument.json'),name=p['name'],site=p['site'],observed=p['observed']),ensure_ascii=False,indent=2))
