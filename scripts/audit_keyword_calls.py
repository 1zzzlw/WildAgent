"""门禁：跨模块函数调用的关键字参数必须能绑定到被调函数的签名。

为什么需要它：`normalize_architecture_plan(raw, profile=...)` 这类错误只在
**运行到那一行**时抛 TypeError。全量导入扫描看不到（不是导入错误），
`build_generation_graph()` 看不到（只编译图、不跑节点），单元测试也看不到
（测试直接按位置参调用被调函数，从不经过真实调用点）。
结果是「测试全绿但线上整轮生成直接崩」。

用法（在 wild-server 目录下）：
    ./.venv/Scripts/python.exe ../scripts/audit_keyword_calls.py
退出码 0 = 无问题，1 = 存在无法绑定的关键字参数。
"""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "wild-server"
APP = ROOT / "app"
# 脚本从 scripts/ 运行，sys.path[0] 是 scripts/ 而不是 wild-server，
# 不显式插入就会 import 失败，然后被静默跳过 —— 门禁会假装"0 问题"通过。
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _imported_app_symbols(tree: ast.Module) -> dict[str, tuple[str, str]]:
    """收集 `from app.x import y [as z]` 建立 本地名 -> (模块, 属性)。"""

    symbols: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app."):
            for alias in node.names:
                symbols[alias.asname or alias.name] = (node.module, alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app."):
                    bound = alias.asname or alias.name.split(".")[0]
                    symbols[bound] = (alias.name, "")
    return symbols


def _bind_error(func: object, call: ast.Call) -> str | None:
    """用真实签名试绑一次实参。

    比手写规则可靠：`signature.bind()` 同时覆盖"未知关键字参数"（本次真实事故）、
    "位置参数过多"、"缺少必填参数"、"参数重复"。手写规则一度漏掉了后两类——
    门禁只查自己想到的那几类，等于给自己留盲区。
    """

    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return None
    try:
        signature.bind(*[None] * len(call.args), **{kw.arg: None for kw in call.keywords})
    except TypeError as exc:
        return " ".join(str(exc).split())
    return None


def _is_dynamic(call: ast.Call) -> bool:
    """带 *args / **kwargs 展开的调用无法静态判定，必须跳过并计数。"""

    if any(isinstance(arg, ast.Starred) for arg in call.args):
        return True
    return any(keyword.arg is None for keyword in call.keywords)


def main() -> int:
    findings: list[str] = []
    unresolved: list[str] = []
    dynamic = 0
    checked = 0
    for path in sorted(APP.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        symbols = _imported_app_symbols(tree)
        if not symbols:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            target = symbols.get(node.func.id)
            if target is None:
                continue
            module_name, attribute = target
            if not attribute:
                continue
            try:
                module = importlib.import_module(module_name)
                func = getattr(module, attribute)
            except Exception as exc:  # noqa: BLE001
                unresolved.append(f"{path.relative_to(ROOT)}:{node.lineno} {node.func.id} -> {exc}")
                continue
            if not callable(func) or inspect.isclass(func):
                continue
            if _is_dynamic(node):
                dynamic += 1
                continue
            checked += 1
            error = _bind_error(func, node)
            if error:
                findings.append(
                    f"{path.relative_to(ROOT)}:{node.lineno} {node.func.id}() -> {error}"
                )

    print(
        f"扫描调用点：{checked} 个，问题：{len(findings)} 个，"
        f"无法解析：{len(unresolved)} 个，动态展开跳过：{dynamic} 个"
    )
    for item in findings:
        print(" FAIL", item)
    for item in unresolved:
        print(" SKIP", item)
    if checked == 0:
        # 门禁扫到 0 个调用点说明路径解析坏了，绝不能当成"通过"。
        print(" FATAL 没有扫描到任何调用点，门禁自身失效")
        return 1
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
