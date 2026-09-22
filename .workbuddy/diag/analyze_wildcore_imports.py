import os, re, collections

ROOT = r'E:\AgentProject\WildAgent'
WW = os.path.join(ROOT, 'wild-web')

PAT = re.compile(r"""(?:from|import)\s*\(?\s*['"]([^'"]+)['"]""")
EXT = ('.ts', '.tsx', '.vue', '.mjs', '.js')

def collect(base, exclude_prefixes=()):
    """返回 [(绝对路径, 相对ROOT路径, 所有引用说明符)]"""
    out = []
    for dp, dn, fn in os.walk(base):
        dn[:] = [d for d in dn if d not in ('node_modules', 'dist', '.git', '__pycache__')]
        rel_dir = os.path.relpath(dp, ROOT)
        if any(rel_dir == p or rel_dir.startswith(p + os.sep) for p in exclude_prefixes):
            continue
        for f in fn:
            if not f.endswith(EXT):
                continue
            p = os.path.join(dp, f)
            try:
                txt = open(p, encoding='utf-8', errors='ignore').read()
            except OSError:
                continue
            specs = PAT.findall(txt)
            if specs:
                out.append((p, os.path.relpath(p, ROOT), specs))
    return out

def is_relative(spec):
    return spec.startswith('.')

# ---------- A. 包内（wild-core + wild-compiler）自检 ----------
print('=' * 70)
print('A. 包内 import 自检 —— 越界引用（非相对路径）')
print('=' * 70)
pkg_dirs = [
    os.path.join(WW, 'src', 'wild-core'),
    os.path.join(WW, 'src', 'wild-compiler'),
]
boundary = []
for base in pkg_dirs:
    for p, rel, specs in collect(base):
        for s in specs:
            if not is_relative(s):
                boundary.append((rel, s))
if boundary:
    for rel, s in sorted(set(boundary)):
        print(f'  {rel}\n      -> {s}')
else:
    print('  （无）')

print()
print('=' * 70)
print('B. wild-web 侧引用 wild-core / wild-compiler —— 去重计数')
print('=' * 70)
ext = collections.Counter()
detail = []
for p, rel, specs in collect(WW, exclude_prefixes=[
    os.path.join('wild-web', 'src', 'wild-core'),
    os.path.join('wild-web', 'src', 'wild-compiler'),
]):
    for s in specs:
        if 'wild-core' in s or 'wild-compiler' in s:
            ext[s] += 1
            detail.append((rel, s))
for s, n in ext.most_common():
    print(f'  {n:3d}  {s}')

print()
print('=' * 70)
print('C. 逐文件明细（用于批量改写）')
print('=' * 70)
byfile = collections.defaultdict(list)
for rel, s in detail:
    byfile[rel].append(s)
for rel in sorted(byfile):
    print(f'  {rel}')
    for s in sorted(set(byfile[rel])):
        print(f'      {s}')
print()
print(f'总计: {len(byfile)} 个文件, {len(detail)} 条引用')
