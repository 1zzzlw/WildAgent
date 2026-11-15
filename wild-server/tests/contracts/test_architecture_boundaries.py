"""目录依赖与启动资源边界；仅解析源文件，不初始化业务模块。"""
import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"


def imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            yield node.module
        elif isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)


def test_domain_does_not_depend_on_workflows_transport_or_storage():
    forbidden = ("app.agent", "app.api", "app.application", "app.bootstrap", "app.infrastructure", "fastapi", "sqlalchemy")
    violations = [(str(path.relative_to(APP)), name)
                  for path in (APP / "domain").rglob("*.py")
                  for name in imports(path) if name.startswith(forbidden)]
    assert violations == []


def test_agent_does_not_import_transport_or_application_use_cases():
    violations = [(str(path.relative_to(APP)), name)
                  for path in (APP / "agent").rglob("*.py")
                  for name in imports(path)
                  if name.startswith(("app.api", "app.application", "app.bootstrap"))]
    assert violations == []


def test_application_has_no_fastapi_dependency():
    assert [(str(path.relative_to(APP)), name)
            for path in (APP / "application").rglob("*.py")
            for name in imports(path) if name.startswith("fastapi")] == []


def test_agent_runtime_does_not_create_external_resources_during_import():
    tree = ast.parse((APP / "agent/runtime.py").read_text(encoding="utf-8"))
    calls = [node.func.id for statement in tree.body
             if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.Expr))
             for node in ast.walk(statement)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
    assert not {"create_llm", "create_spec_loader", "AgentResources"}.intersection(calls)
