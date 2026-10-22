"""执行建筑创作命令，保留原始输出；不改动应用或被校验文件。"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
base, label, *command = sys.argv[1:]
base = Path(base).resolve()
root = Path(__file__).resolve().parents[3]
tz = timezone(timedelta(hours=8))
started = datetime.now(tz).isoformat()
result = subprocess.run(command, cwd=root, capture_output=True, encoding='utf-8',
                        errors='replace', env={**os.environ, 'PYTHONIOENCODING': 'utf-8',
                        'SystemRoot': r'C:\Windows', 'WINDIR': r'C:\Windows'})
record = dict(command=command, cwd=str(root), started_at=started,
              ended_at=datetime.now(tz).isoformat(), exit_code=result.returncode,
              stdout=result.stdout, stderr=result.stderr)
out = base/'03-过程记录'/'命令记录'
out.mkdir(parents=True, exist_ok=True)
(out/(label+'.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
print(result.stdout, end='')
print(result.stderr, end='', file=sys.stderr)
sys.exit(result.returncode)
