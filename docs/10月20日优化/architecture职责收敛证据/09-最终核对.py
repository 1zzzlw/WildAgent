"""只核对本轮选定文件，保留修改前副本与独立差异。"""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
baseline = json.loads((HERE/'00-修改前指纹.json').read_text(encoding='utf-8'))
changes, patches = [], []
for item in baseline:
    before = (HERE/'修改前'/item['path']).read_text(encoding='utf-8')
    after = (REPO/item['path']).read_text(encoding='utf-8')
    if before != after:
        diff = list(difflib.unified_diff(before.splitlines(), after.splitlines(),
                    fromfile='before/'+item['path'], tofile='after/'+item['path'], lineterm=''))
        patches.extend(diff)
        changes.append({'path': item['path'], 'before_lines': len(before.splitlines()), 'after_lines': len(after.splitlines()),
                        'added': sum(s.startswith('+') and not s.startswith('+++') for s in diff),
                        'removed': sum(s.startswith('-') and not s.startswith('---') for s in diff)})
(HERE/'09-本轮源码差异.patch').write_text(''.join(s+'\n' for s in patches), encoding='utf-8', newline='\n')
paths = [item['path'] for item in baseline] + ['wild-server/scripts/ci/test_architecture_design.py',
    'wild-server/scripts/ci/test_design_execution.py', 'docs/10月20日优化/04-architecture职责收敛.md',
    '.codex/skills/building-blueprint-diagnostics/SKILL.md',
    'wild-server/app/agent/plan/workflow.py', 'wild-server/app/agent/plan/implementation.py',
    'wild-server/app/design/normalization.py', 'wild-server/app/design/repository.py',
    'wild-server/app/agent/generation/architecture/design_blocks.py',
    'D:/Backup/Downloads/trace-01a15180-3ba3-7c71-8a4a-edcbc55a2485.json']
paths.extend(str(p.relative_to(REPO)).replace('\\', '/') for p in HERE.iterdir()
             if p.is_file() and p.name not in {'09-最终核对.json', '09-核对命令.json'})
files = []
for name in dict.fromkeys(paths):
    data = (REPO/name).read_bytes()
    files.append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
for name in [item['path'] for item in changes] + ['wild-server/scripts/ci/test_architecture_design.py']:
    if name.endswith('.py'):
        ast.parse((REPO/name).read_text(encoding='utf-8'), filename=name)
check = subprocess.run(['git', 'diff', '--check', '--', *[c['path'] for c in changes]],
                       cwd=REPO, capture_output=True, encoding='utf-8')
summary = {'changes': changes, 'production_net_lines': sum(c['added']-c['removed'] for c in changes),
           'syntax_check': 'passed', 'diff_check_exit': check.returncode, 'diff_check_output': check.stdout+check.stderr,
           'source_and_evidence_files': files,
           'scope': 'selected baseline snapshots; new regression test is listed separately; no whole-worktree content verification'}
(HERE/'09-最终核对.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k != 'source_and_evidence_files'}, ensure_ascii=False))
assert check.returncode == 0
