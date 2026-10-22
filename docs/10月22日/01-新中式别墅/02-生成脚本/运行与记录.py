"""执行一条命令并原样保存 stdout/stderr、起止时间、退出码。"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
TZ = timezone(timedelta(hours=8))
label, *command = sys.argv[1:]
started = datetime.now(TZ).isoformat()
result = subprocess.run(command, cwd=ROOT, env={**os.environ, 'PYTHONIOENCODING': 'utf-8',
                        'SystemRoot': r'C:\Windows', 'WINDIR': r'C:\Windows'},
                        capture_output=True, encoding='utf-8', errors='replace')
record = dict(label=label, command=command, cwd=str(ROOT), started_at=started,
              ended_at=datetime.now(TZ).isoformat(), exit_code=result.returncode,
              stdout=result.stdout, stderr=result.stderr)
folder = HERE/'03-过程记录'/'命令记录'
folder.mkdir(parents=True, exist_ok=True)
(folder/(label+'.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
print(result.stdout, end='')
if result.stderr:
    print(result.stderr, file=sys.stderr, end='')
sys.exit(result.returncode)
