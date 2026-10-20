"""只读旧 trace，以新设计输入回放参数推导，不重跑完整建筑生成。"""
from copy import deepcopy
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
SERVER = HERE.parents[2] / 'wild-server'
sys.path.insert(0, str(SERVER))
from app.agent.generation.architecture.workflow import build_design_document_or_error
from app.design.coordinates import stair_span_conflicts
from app.design.resolver import resolve_design

source = Path('D:/Backup/Downloads/trace-01a15180-3ba3-7c71-8a4a-edcbc55a2485.json')
trace = json.loads(source.read_text(encoding='utf-8'))
run = next(r for r in trace['runs'] if r['langsmith']['name'] == 'architecture')
output = run['outputs']
legacy = deepcopy(output['architecture_diag']['raw_plan'])
old_stair = next(c for c in legacy['components'] if c['id'] == 'stair_1')
old_stair['form']['rises'] = 16
old_issue = stair_span_conflicts(legacy)
assert any('6.4m' in issue for issue in old_issue)
draft = deepcopy(legacy)
for key in ('width', 'depth', 'modeled_floors'):
    draft['massing'].pop(key, None)
for group in [draft['facades'], *[v.get('facades', {}) for v in draft['volumes']]]:
    for facade in group.values():
        ground, upper = facade.pop('ground_pattern'), facade.pop('upper_pattern')
        assert len(ground) == len(upper)
        facade.pop('bays')
        facade['layout'] = [{'ground': a, 'upper': b} for a, b in zip(ground, upper)]
stair = next(c for c in draft['components'] if c['id'] == 'stair_1')
stair['step_design'] = {'flights': stair['form'].pop('flights'),
                        'max_riser_height': stair['form'].pop('riser_height')}
stair['form'].pop('rises')
stair['size'].pop('height')
document = build_design_document_or_error(draft, session_id='architecture_trace_replay',
    source_request='生成一个别墅', building_type='villa', style_intent=[], previous=None)
resolved = resolve_design(document)
marker = next(m for m in resolved.component_markers if m['id'] == 'stair_1')
form = marker['design']['form']
assert form['rises'] == 8
assert abs(form['riser_height'] * form['flights'] * form['rises'] - 3.2) < 1e-9
summary = {'source': str(source), 'original_architecture_calls': output['architecture_diag']['model_calls'],
           'old_stair_issue': old_issue, 'new_derived_height': marker['design']['size']['height'],
           'new_derived_steps_per_flight': form['rises'], 'new_derived_riser_height': form['riser_height'],
           'new_massing': document.decisions.massing.model_dump(mode='json'), 'model_calls_in_this_replay': 0,
           'scope': 'facade choices from the final historical design; only representation and stair arithmetic replayed, not first-draft or whole-building success'}
for name, value in [('05-新模型输入.json', draft), ('05-派生设计文档.json', document.model_dump(mode='json')),
                    ('05-派生解析结果.json', resolved.model_dump(mode='json')), ('05-回放摘要.json', summary)]:
    (HERE/name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False))
