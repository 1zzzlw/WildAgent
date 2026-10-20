"""只调用当前项目的纯空间检查；最小适配设计字段，不模拟或启动 Agent 图。"""
import sys
import json
import hashlib
from pathlib import Path

here=Path(__file__).resolve().parent
sys.path.insert(0,str(here.parents[2]/'wild-server'))
from app.design.spatial_review import review_spatial_use

design=json.loads((here/'01-设计事实.json').read_text(encoding='utf-8'))
adapted={
    'massing': {'floor_height':3.42,'floors':2},
    'floor_layouts': [{'floor':1,'level':design['levels']['ground']},
                      {'floor':2,'level':design['levels']['upper']}],
    'circulation': {'paths': [dict(id=p['id'],floor=1 if p['points'][0][1]<1 else 2,
                                  points=[[q[0],q[2]] for q in p['points']],width=p['width'],
                                  height=design['use_clearances']['route_headroom']) for p in design['routes']]}
}
rows=[]
for label,target in [('initial',here/'03-初稿.wild'),('final',here.parent/'汀院别墅-Codex.wild')]:
    bp=json.loads(target.read_text(encoding='utf-8'))
    result=review_spatial_use(bp,adapted)
    rows.append(dict(label=label,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),result=result))
out={'adapter_scope':'仅给 review_spatial_use 提供标高和六条路线；不是完整 DesignDocument 或全图运行',
     'function':'app.design.spatial_review.review_spatial_use','design_input':adapted,'runs':rows}
(here/'11-项目空间复核结果.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
for r in rows:
    value=r['result']
    print(json.dumps(dict(label=r['label'],errors=len(value['errors']),observations=len(value['observations']),
                          checks=[{'id':c['path_id'],'status':c['status'],'blockers':c['actual']['blocking_entity_ids']} for c in value['checks']],
                          unverified_entities=len(value['unverified_entity_ids'])),ensure_ascii=False))
