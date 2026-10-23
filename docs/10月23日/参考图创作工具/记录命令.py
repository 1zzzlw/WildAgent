"""记录本批真实生成/出图命令及输出；不会替代检查结果或自动宣称通过。"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--case',required=True)
parser.add_argument('--stage',required=True)
parser.add_argument('command',nargs=argparse.REMAINDER)
args=parser.parse_args()
command=args.command[1:] if args.command[:1]==['--'] else args.command
folder=next(p for p in ROOT.iterdir() if p.is_dir() and p.name.startswith(args.case+'-'))
out=folder/'03-过程记录/命令记录.json'
start=datetime.now(timezone.utc).isoformat()
environment=os.environ.copy()
environment.setdefault('SystemRoot','C:/Windows')
environment.setdefault('WINDIR',environment['SystemRoot'])
result=subprocess.run(command,cwd=Path.cwd(),env=environment,capture_output=True,text=True,encoding='utf-8',errors='replace')
record=dict(stage=args.stage,command=command,cwd=str(Path.cwd()),started_at=start,finished_at=datetime.now(timezone.utc).isoformat(),exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr)
records=json.loads(out.read_text(encoding='utf-8')) if out.exists() else []
records.append(record)
out.write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(stage=args.stage,exit_code=result.returncode,record=str(out)),ensure_ascii=False))
if result.returncode: print(result.stdout[-2000:])
if result.stderr: print(result.stderr[-5000:],file=sys.stderr)
raise SystemExit(result.returncode)
