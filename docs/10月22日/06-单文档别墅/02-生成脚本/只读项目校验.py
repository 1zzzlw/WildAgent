"""只读调用当前项目验收工具，禁止修改或自动修复作者输出。"""
import hashlib
import json
import os
import sys
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

os.environ['RAG__ENABLED']='false'
os.environ['LANGSMITH_TRACING']='false'
base=Path(__file__).resolve().parents[1]
root=base.parents[2]
sys.path.insert(0,str(root/'wild-server'))
from jsonschema.validators import validator_for
from app.services.agent_service import run_validation_pipeline

target,output=map(Path,sys.argv[1:3])
raw=target.read_bytes()
bp=json.loads(raw)
schema=json.loads((root/'wild-core/schema.json').read_bytes())
errors=[dict(path=list(e.absolute_path),message=e.message)
        for e in validator_for(schema)(schema).iter_errors(bp)]
steps=[asdict(s) for s in run_validation_pipeline(deepcopy(bp),log_steps=False,auto_fix=False)]
report=dict(input=str(target),sha256=hashlib.sha256(raw).hexdigest(),auto_fix=False,
    schema_errors=errors,pipeline=steps,pipeline_error_steps=[s['name'] for s in steps if s['has_error']],
    pipeline_warning_steps=[s['name'] for s in steps if s['has_warning']],source_unchanged=target.read_bytes()==raw)
output.parent.mkdir(parents=True,exist_ok=True)
assert not output.exists(),output
output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
sys.exit(1 if errors or report['pipeline_error_steps'] else 0)
