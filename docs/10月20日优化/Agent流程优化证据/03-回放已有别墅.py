"""只读回放 08:17 的真实图纸与已采用主体；不把错误图纸重新批准为成功建筑。"""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

HERE = Path(__file__).resolve().parent
SERVER = HERE.parents[2] / 'wild-server'
sys.path.insert(0, str(SERVER))
from app.design.compilation import project_drawing, compile_native_marker
from app.design.contracts import DesignDocument
from app.agent.plan.contracts import PlanItem
from app.agent.plan.implementation import run_marker_generate
from app.agent.generation.capability import load_engine_schema

sid = 'session_1792455472462'
document = DesignDocument.model_validate_json((SERVER / f'storage/designs/{sid}.design.json').read_text(encoding='utf-8'))
resolved = json.loads((SERVER / f'storage/designs/{sid}.resolved.json').read_text(encoding='utf-8'))
original = json.loads(next((SERVER/'storage/scenes').rglob(f'{sid}*.wild')).read_text(encoding='utf-8'))
try:
    project_drawing(document)
except ValueError as exc:
    design_errors = str(exc)
else:
    raise AssertionError('历史图纸中的入口矛盾仍未提前发现')

base = deepcopy(original)
base['geometry']['components'] = []
roles = {r.role: r.materialId for r in document.decisions.materials.resolved_plan.roles}
candidates = [m for m in resolved['component_markers'] if m['type'] in {'door', 'window'}
              and all((m['design'].get('size') or {}).get(k) for k in ('width', 'height'))]
selected = [m for m in candidates if compile_native_marker(m, base, roles, load_engine_schema()) is not None]
needs_model = [m['id'] for m in candidates if m not in selected]
state = {'resolved_design': {'design_hash': resolved['design_hash'], 'component_markers': selected},
         'design_document': document.model_dump(mode='json'), 'skeleton_blueprint': base,
         'drawing_hosts': [e for e in base['geometry']['elements'] if e['type']=='wall'],
         'component_fragments': {}, 'component_diagnostics': {}}
item = PlanItem(id='native_replay', op='generate', kind='window', label='历史已明确门窗',
                target={'marker_ids': [m['id'] for m in selected]},
                params={'design_hash': resolved['design_hash'], 'design_markers': True})
with patch('app.agent.plan.knowledge_tool.search_knowledge_result', side_effect=AssertionError('不应重新检索')), \
     patch('app.llm.invocation.invoke_llm', new=AsyncMock(side_effect=AssertionError('不应重新调用模型'))):
    updates, status, ids, evidence, trace = asyncio.run(run_marker_generate(state, item))
model_calls = sum(t.get('model_calls', 0) for t in trace)
result = {'source_session': sid, 'old_design_rejected_before_execution': True, 'design_errors': design_errors,
          'native_markers': [m['id'] for m in selected], 'status': status, 'model_calls': model_calls,
          'needs_model_for_missing_parameters': needs_model,
          'implementation_summary': updates['component_diagnostics'][item.id]['implementation_summary'],
          'scope': 'historical resolved marker execution replay; no design approval and no whole-building acceptance',
          'updates': updates, 'trace': trace}
(HERE/'03-本地别墅回放结果.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in {'updates','trace','design_errors'}},ensure_ascii=False))
print(design_errors)
assert status == 'succeeded', json.dumps(updates['component_diagnostics'][item.id]['failures'], ensure_ascii=False)
assert model_calls == 0
assert len(ids) == len(selected)
candidate = deepcopy(base)
candidate['geometry']['components'].extend(updates['component_fragments'][item.id])
(HERE/'07-原生窗局部回放候选.wild').write_text(json.dumps(candidate, ensure_ascii=False, indent=2), encoding='utf-8')
