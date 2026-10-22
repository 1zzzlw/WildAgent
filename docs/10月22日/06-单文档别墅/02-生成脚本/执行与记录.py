"""本次单文档尝试独立记录器，只使用标准库。"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
base=Path(__file__).resolve().parents[1]
root=base.parents[2]
label,*command=sys.argv[1:]
tz=timezone(timedelta(hours=8))
started=datetime.now(tz).isoformat()
result=subprocess.run(command,cwd=root,capture_output=True,encoding='utf-8',errors='replace',
    env={**os.environ,'PYTHONIOENCODING':'utf-8','SystemRoot':r'C:\Windows','WINDIR':r'C:\Windows'})
record=dict(command=command,cwd=str(root),started_at=started,ended_at=datetime.now(tz).isoformat(),
    exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr)
folder=base/'03-过程记录/命令记录'
folder.mkdir(parents=True,exist_ok=True)
target=folder/(label+'.json')
assert not target.exists(),target
target.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(result.stdout,end='')
print(result.stderr,end='',file=sys.stderr)
sys.exit(result.returncode)
