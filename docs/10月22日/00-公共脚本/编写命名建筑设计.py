"""逐栋保存 DesignDocument；此步不产出 WILD，也不调用 Agent。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'wild-server'))
from app.design.contracts import DesignDocument
from app.design.compilation import project_drawing

CATALOG = {
    'library': dict(folder='07-图书馆', name='知序图书馆', size=32, floors=2, height=4.2,
        bounds=[-12, -8, 12, 12], style='暖石、赤陶与细金属遮阳的庭院图书馆',
        concept='中央开敞庭院贯通两层，环绕布置书架与阅览席；前庭台阶和细柱雨棚形成公共入口。',
        rooms=['入口咨询与新书展示', '首层开放书架与阅览席', '二层安静阅览', '贯通庭院', '双跑楼梯'],
        packages=['石材分缝与勒脚', '入口悬挑雨棚及承托', '赤陶遮阳片', '庭院环廊栏杆', '书架书脊与阅览家具', '可保存中文招牌', '真实灯光']),
    'villa': dict(folder='08-现代别墅', name='澄屿现代别墅', size=32, floors=2, height=3.6,
        bounds=[-10, -3, 10, 11], style='白石、清水混凝土与暖木的退台住宅',
        concept='首层横向起居体量向泳池开放，上层向北退台；西侧完整双跑楼梯，东侧长露台连接卧室。',
        rooms=['客厅与餐厅', '厨房与客用卫生间', '主卧及次卧', '楼上浴室', '双跑楼梯', '南向泳池与露台'],
        packages=['上下体量退台', '薄檐与金属滴水边', '木格栅与露台玻璃栏杆', '透明泳池与浅色池底', '室内家具', '可保存中文招牌', '真实灯光']),
    'cafe': dict(folder='09-咖啡厅', name='青屿咖啡', size=16, floors=1, height=3.8,
        bounds=[-5.8, -2.7, 5.8, 5.5], style='暖砖、橄榄绿金属与原木的街角咖啡厅',
        concept='不对称入口与通透转角窗，连续檐廊下设置外摆，室内吧台和长椅保持清楚的点单通道。',
        rooms=['入口与点单区', '咖啡吧台及后场', '室内座席', '檐廊外摆', '独立卫生间'],
        packages=['砖缝与窗套', '层叠薄檐', '遮棚承托', '咖啡机与杯具', '内外座席', '可保存中文招牌', '真实灯光']),
    'market': dict(folder='10-超市', name='邻里优选超市', size=16, floors=1, height=4.0,
        bounds=[-6.5, -3.5, 6.5, 6.5], style='浅色砖、森林绿檐口与暖木生鲜陈列的社区超市',
        concept='全宽入口遮棚和醒目招牌，室内三列货架、收银台、生鲜与冷藏柜围绕畅通的主通道布置。',
        rooms=['顾客入口', '收银与打包', '三列商品货架', '生鲜台', '冷藏陈列', '后场及卸货门'],
        packages=['檐口与有支撑遮棚', '连续橱窗', '商品分区陈列', '收银设备', '门外绿化与推车', '可保存中文招牌', '真实灯光']),
}

kind = sys.argv[1]
p = CATALOG[kind]
base = ROOT/'docs'/'10月22日'/p['folder']
for folder in ['01-需求与设计', '02-生成脚本', '03-过程记录', '04-校验', '05-效果图', '06-剖切查看']:
    (base/folder).mkdir(parents=True, exist_ok=True)
x0, z0, x1, z1 = p['bounds']
volumes = [dict(id='main', x=x0, z=z0, width=x1-x0, depth=z1-z0, start_floor=1, end_floor=p['floors'])]
if kind == 'villa':
    volumes[0]['end_floor'] = 1
    volumes.append(dict(id='upper', x=-10, z=1, width=18, depth=10, start_floor=2, end_floor=2))
facade = dict(bays=4, ground_pattern=['window', 'window', 'door', 'window'], upper_pattern=['window']*4)
document = DesignDocument.model_validate(dict(
    design_id=f'named-{kind}-20261022', session_id='codex-offline-named-buildings', revision=1, status='draft',
    requirements=dict(source_request=f"创建{p['size']}×{p['size']}米地块的{p['name']}，招牌写入WILD。", building_type=kind,
                      style_intent=[p['style']], profile='detailed'),
    decisions=dict(kind='architecture', concept=p['concept'],
        massing=dict(shape='terraced' if kind=='villa' else 'courtyard' if kind=='library' else 'rectangular',
                     width=x1-x0, depth=z1-z0, floors=p['floors'], modeled_floors=p['floors'], floor_height=p['height']),
        complexity=dict(level='detailed', min_volumes=len(volumes), min_detail_packages=len(p['packages']),
                        target_structural_elements=180, grid_bays=[4, 4], reason='以层次、收边、家具与真实灯光体现精细度'),
        volumes=volumes, structural_grid=dict(system='frame', x_bays=4, z_bays=4),
        envelope=dict(system='solid_wall'), facades={k:facade for k in ['front','back','left','right']},
        roof=dict(type='flat', overhang=.35), detail_packages=p['packages'], design_rationale=p['rooms'],
        floor_layouts=[dict(floor=n+1, level=.4+n*p['height'], rooms=[], walls=[]) for n in range(p['floors'])],
        authoring=dict(kind=kind, **p, sign_text=p['name'], size_scope='完整地块（含入口、庭院），单位米',
                       notes='详细构件由本目录确定性作者编译器装配；设计投影仅核对主壳，不冒充完整Agent编译。')),
    constraints=[dict(id='site', kind='user_hard', target='scene.boundingBox', expression='X和Z尺寸均等于地块尺寸', expected=p['size'], check='equals'),
                 dict(id='sign', kind='user_hard', target='primitive.label.text', expression='真实中文招牌等于建筑名称', expected=p['name'], check='equals')]))
(base/'01-需求与设计'/'DesignDocument.json').write_text(document.model_dump_json(indent=2), encoding='utf-8')
projection = project_drawing(document)
(base/'01-需求与设计'/'主体设计投影.json').write_text(projection.model_dump_json(indent=2), encoding='utf-8')
(base/'01-需求与设计'/'设计说明.md').write_text(f"# {p['name']}\n\n{p['concept']}\n\n地块：{p['size']}×{p['size']}米，含庭院与入口；主体边界{p['bounds']}。共{p['floors']}层，层高{p['height']}米，首层完成面0.4米。\n\n"+
    '\n'.join('- '+s for s in p['rooms'])+'\n\n精细化内容：'+ '、'.join(p['packages'])+'。\n\n招牌正面朝向街道（世界−Z），文字存于label.text。灯罩的emissive负责可见亮面，lightSource负责照亮周围。\n\n这是本次独立设计，未读取或复用旧三层别墅设计。作者编译不使用Agent、RAG或模型API；结构验证和审美验收分开记录。\n', encoding='utf-8')
print(json.dumps(dict(design=str(base/'01-需求与设计'/'DesignDocument.json'), name=p['name'], site=p['size'], projection='project_drawing'), ensure_ascii=False))
