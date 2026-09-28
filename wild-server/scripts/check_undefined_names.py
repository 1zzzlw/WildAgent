"""扫描"读取了但从未定义"的裸名（pyflakes-lite），专抓重构残留。

为什么需要它：本仓库没有装 ruff/pyflakes，而 `python -c "import x"` 只能证明模块能 import，
**证明不了函数执行到某一行才炸**。实测踩到：计划层整体退场时删掉了 `plan_feedback = (...)`
的赋值，却留下了 `if plan_feedback:` —— 模块 import 完全正常、类型检查也不报，
只有真的跑到那一行（且恰好有 reasoning callback）才 NameError，用户看到的就是"意图分类之后直接报错"。

做法（纯 AST，不 import 目标模块，所以不会有副作用、也不需要依赖齐全）：
  逐个函数作用域，收集「参数 / 赋值目标 / for·with·except 绑定 / 导入 / 嵌套 def / global·nonlocal」
  → 再找 ctx=Load 的 `ast.Name` 里不在这份集合、也不在模块全局、也不在内建里的名字。
  属性访问是 `ast.Attribute` 不是 `ast.Name`，所以不会把 `obj.attr` 误判成未定义名。

用法：
    <任意 python3> wild-server/scripts/check_undefined_names.py <目录或文件...>
退出码 1 = 有未定义名。
"""
from __future__ import annotations

import ast
import builtins
import sys
from pathlib import Path

BUILTINS = set(dir(builtins)) | {
    # 由 import 机制注入的模块级 dunder，不在 dir(builtins) 里 —— 不加会被误报
    "__file__", "__name__", "__doc__", "__package__", "__spec__",
    "__loader__", "__builtins__", "__debug__", "__path__", "__dict__",
}


def _bound_names(node: ast.AST, into: set[str]) -> None:
    """把一段代码里所有"绑定名字"的位置收进 into（不递归进嵌套函数体）。"""
    for child in ast.walk(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            into.add(child.name)
            # def 的装饰器/默认值/注解属于外层作用域，继续走 walk 即可；
            # 但函数体是独立作用域，下面用 return 跳过。
            continue
        if isinstance(child, ast.Lambda):
            continue
        if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
            into.add(child.id)
        elif isinstance(child, ast.arg):
            into.add(child.arg)
        elif isinstance(child, (ast.Import, ast.ImportFrom)):
            for alias in child.names:
                into.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(child, ast.ExceptHandler) and child.name:
            into.add(child.name)
        elif isinstance(child, (ast.Global, ast.Nonlocal)):
            into.update(child.names)
        elif isinstance(child, ast.MatchAs) and child.name:
            into.add(child.name)
        elif isinstance(child, ast.MatchStar) and child.name:
            into.add(child.name)


def _scope_bound_names(scope: ast.AST) -> set[str]:
    """函数作用域内被绑定的名字（含参数），不进入更内层的函数/类作用域。"""
    bound: set[str] = set()
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        args = scope.args
        for group in (args.posonlyargs, args.args, args.kwonlyargs):
            for a in group:
                bound.add(a.arg)
        if args.vararg:
            bound.add(args.vararg.arg)
        if args.kwarg:
            bound.add(args.kwarg.arg)

    def visit(node: ast.AST, top: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                bound.add(getattr(child, "name", ""))
                if isinstance(child, ast.Lambda):
                    continue
                # 只取名字，不进入其函数体（独立作用域）
                continue
            if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
                bound.add(child.id)
            elif isinstance(child, (ast.Import, ast.ImportFrom)):
                for alias in child.names:
                    bound.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(child, ast.ExceptHandler) and child.name:
                bound.add(child.name)
            elif isinstance(child, (ast.Global, ast.Nonlocal)):
                bound.update(child.names)
            elif isinstance(child, ast.MatchAs) and child.name:
                bound.add(child.name)
            elif isinstance(child, ast.MatchStar) and child.name:
                bound.add(child.name)
            visit(child, False)

    if not isinstance(scope, ast.Lambda):
        for stmt in getattr(scope, "body", []):
            visit(stmt, True)
    bound.discard("")
    return bound


def check_module(path: Path) -> list[tuple[int, str, str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [(exc.lineno or 0, "<syntax>", str(exc))]

    module_names: set[str] = set()
    for stmt in tree.body:
        _bound_names(stmt, module_names)

    problems: list[tuple[int, str, str]] = []

    def walk(node: ast.AST, outer: list[set[str]]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                bound = _scope_bound_names(child)
                local = set(bound)
                available = set(module_names) | BUILTINS
                for frame in outer:
                    available |= frame
                # 参数默认值/装饰器在外层求值，先按外层作用域检查一遍
                for meta in list(child.decorator_list) + list(child.args.defaults) + [
                    d for d in child.args.kw_defaults if d is not None
                ]:
                    scan(meta, list(outer), problems)
                scan(child, outer + [local], problems)
                walk(child, outer + [local])
            elif isinstance(child, ast.ClassDef):
                cls_bound = _scope_bound_names(child)
                scan(child, outer + [cls_bound], problems)
                walk(child, outer + [cls_bound])
            else:
                walk(child, outer)

    def scan(node: ast.AST, scopes: list[set[str]], out: list[tuple[int, str, str]]) -> None:
        local = set()
        for frame in scopes:
            local |= frame
        available = local | BUILTINS
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                if sub.id not in available and sub.id not in module_names:
                    out.append((sub.lineno, sub.id, "读取了未定义的名字"))

    # 模块级语句（含模块级函数体）统一扫
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body_local = _scope_bound_names(stmt)
            scan(stmt, [body_local], problems)
        elif isinstance(stmt, ast.ClassDef):
            scan(stmt, [_scope_bound_names(stmt)], problems)
        else:
            scan(stmt, [module_names], problems)

    walk(tree, [])
    return sorted(set(problems))


def main(argv: list[str]) -> int:
    targets = argv[1:]
    if not targets:
        print(__doc__)
        return 2
    files: list[Path] = []
    for t in targets:
        p = Path(t)
        if p.is_dir():
            files.extend(sorted(p.rglob("*.py")))
        elif p.suffix == ".py":
            files.append(p)
    skip = {".venv", "__pycache__", "node_modules", "migrations", ".git"}
    files = [f for f in files if not (set(f.parts) & skip)]

    total = 0
    for f in files:
        for lineno, name, kind in check_module(f):
            print(f"{f}:{lineno}: {name} — {kind}")
            total += 1
    print(f"\n扫描 {len(files)} 个文件，未定义名 {total} 处")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
