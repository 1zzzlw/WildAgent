"""只读调用项目校验流水线，记录完整报告；不修正或回写输入。"""
import os
os.environ.setdefault('SystemRoot', r'C:\Windows')
os.environ.setdefault('WINDIR', r'C:\Windows')
os.environ['RAG__ENABLED'] = 'false'
os.environ['LANGSMITH_TRACING'] = 'false'
import sys
import json
import hashlib
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'wild-server'))
from app.services.agent_service import run_validation_pipeline
from jsonschema.validators import validator_for

target, output = map(Path, sys.argv[1:3])
raw = target.read_bytes()
bp = json.loads(raw)
schema = json.loads((ROOT/'wild-core'/'schema.json').read_text(encoding='utf-8'))
schema_errors = [dict(path=list(e.absolute_path), message=e.message)
                 for e in validator_for(schema)(schema).iter_errors(bp)]
steps = [asdict(s) for s in run_validation_pipeline(deepcopy(bp), log_steps=False, auto_fix=False)]
report = dict(input=str(target), sha256=hashlib.sha256(raw).hexdigest(), auto_fix=False,
              schema_errors=schema_errors, pipeline=steps,
              pipeline_error_steps=[s['name'] for s in steps if s['has_error']],
              pipeline_warning_steps=[s['name'] for s in steps if s['has_warning']],
              source_unchanged=raw == target.read_bytes())
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
sys.exit(1 if schema_errors or report['pipeline_error_steps'] else 0)
