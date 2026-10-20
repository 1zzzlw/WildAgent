"""从本轮修改前副本生成差异，避免把已有未提交工作算成本轮修改。"""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
baseline = json.loads((HERE/'00-修改前文件指纹.json').read_text(encoding='utf-8'))
changes, patches = [], []
for record in baseline:
    before = (HERE/'修改前'/record['path']).read_bytes()
    after = (REPO/record['path']).read_bytes()
    if before != after:
        diff = list(difflib.unified_diff(before.decode('utf-8').splitlines(), after.decode('utf-8').splitlines(),
                    fromfile='before/'+record['path'], tofile='after/'+record['path'], lineterm=''))
        patches.extend(diff)
        changes.append({'path': record['path'], 'added_lines': sum(s.startswith('+') and not s.startswith('+++') for s in diff),
                        'removed_lines': sum(s.startswith('-') and not s.startswith('---') for s in diff)})
(HERE/'11-本轮修改.patch').write_text(''.join(s+'\n' for s in patches), encoding='utf-8', newline='\n')
paths = [r['path'] for r in baseline] + [
    'wild-server/scripts/ci/test_design_execution.py', 'wild-core/schema.json',
    'wild-core/src/compiler/components/light.ts', 'wild-core/src/compiler/components/door.ts',
    'wild-core/src/compiler/components/window.ts', 'wild-server/app/agent/generation/component/registry.py',
    'wild-server/app/agent/generation/capability.py', 'wild-server/app/agent/graph.py',
    'wild-server/app/design/markers.py', 'wild-server/app/design/coordinates.py',
    'wild-server/app/agent/generation/architecture/design_workflow.py',
    'wild-server/app/agent/plan/workflow.py', 'wild-server/app/design/contracts.py',
    'wild-server/app/design/repository.py', 'wild-server/app/design/review_outcome.py',
    'wild-server/app/agent/design_flow/review.py', 'wild-server/app/agent/design_flow/compile.py',
    'wild-server/app/agent/validation/workflow.py', 'wild-server/app/rag/trace.py',
    'wild-web/scripts/validate-generated.mjs', 'wild-server/pyproject.toml',
    '.codex/skills/building-blueprint-diagnostics/SKILL.md',
    'docs/10月20日优化/03-Agent流程优化实施记录.md', 'docs/10月20日优化/README.md',
    'wild-server/storage/designs/session_1792455472462.design.json',
    'wild-server/storage/designs/session_1792455472462.resolved.json',
    'wild-server/storage/sessions/rag_traces/session_1792455472462/req_1792455476549_mpdt6ydcm.json',
    'wild-server/storage/scenes/2026-10-20/session_1792455472462_现代简约两层别墅.wild',
]
excluded = {'11-最终核对.json', '11-核对命令.json'}  # 当前核对命令结束后才写的日志不作循环哈希。
paths.extend(str(p.relative_to(REPO)).replace('\\', '/') for p in HERE.iterdir()
             if p.is_file() and p.name not in excluded)
files = []
for name in dict.fromkeys(paths):
    data = (REPO/name).read_bytes()
    files.append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
syntax = [r['path'] for r in changes if r['path'].endswith('.py')] + ['wild-server/scripts/ci/test_design_execution.py']
for name in syntax:
    ast.parse((REPO/name).read_text(encoding='utf-8'), filename=name)
check = subprocess.run(['git', 'diff', '--check', '--', *[r['path'] for r in changes]], cwd=REPO,
                       capture_output=True, encoding='utf-8')
status = subprocess.run(['git', 'status', '--porcelain=v1', '-z'], cwd=REPO, capture_output=True, encoding='utf-8')
result = {'changed_from_saved_baseline': changes, 'source_and_evidence_files': files, 'syntax_checked': syntax,
          'diff_check': {'exit_code': check.returncode, 'stdout': check.stdout, 'stderr': check.stderr},
          'git_status_porcelain_z': status.stdout, 'scope': 'selected source snapshots and recorded evidence, not whole-worktree content verification'}
(HERE/'11-最终核对.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'changed_files': changes, 'syntax_files': len(syntax), 'diff_check_exit': check.returncode}, ensure_ascii=False))
assert check.returncode == 0
