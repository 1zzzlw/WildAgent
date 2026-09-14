"""Agent 目录边界回归测试。"""

import ast
from pathlib import Path


SERVER_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = SERVER_ROOT / "app" / "agent"


def test_agent_root_only_contains_workflow_entry_modules():
    root_modules = {path.name for path in AGENT_ROOT.glob("*.py")}

    assert root_modules == {"graph.py", "routing.py", "runtime.py", "state.py"}


def test_nodes_do_not_import_other_nodes():
    violations: list[str] = []
    for path in (AGENT_ROOT / "nodes").glob("*.py"):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("app.agent.nodes")
            ):
                violations.append(f"{path.name}:{node.lineno}:{node.module}")

    assert violations == []


def test_node_entry_modules_stay_small():
    """节点入口一旦重新长胖，就要求把实现下沉到所属领域。"""
    oversized = {
        path.name: len(path.read_text(encoding="utf-8").splitlines())
        for path in (AGENT_ROOT / "nodes").glob("*.py")
        if path.name != "__init__.py"
        and len(path.read_text(encoding="utf-8").splitlines()) > 100
    }

    assert oversized == {}


def test_domain_modules_do_not_depend_on_node_entries():
    violations: list[str] = []
    for package in ("planning", "generation", "knowledge", "validation", "repair", "prompts"):
        for path in (AGENT_ROOT / package).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                module = getattr(node, "module", "")
                if isinstance(node, ast.ImportFrom) and module.startswith("app.agent.nodes"):
                    violations.append(f"{path.relative_to(AGENT_ROOT)}:{node.lineno}:{module}")
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("app.agent.nodes"):
                            violations.append(
                                f"{path.relative_to(AGENT_ROOT)}:{node.lineno}:{alias.name}"
                            )

    assert violations == []


def test_python_sources_do_not_reference_retired_agent_modules():
    retired_modules = {
        "app.agent.architecture_plan",
        "app.agent.component_registry",
        "app.agent.execution_plan",
        "app.agent.graph_state",
        "app.agent.intent_classifier",
        "app.agent.llm_invocation",
        "app.agent.model_client",
        "app.agent.rag_trace",
        "app.agent.runtime_context",
    }
    violations: list[str] = []
    for source_root in (SERVER_ROOT / "app", SERVER_ROOT / "tests"):
        for path in source_root.rglob("*.py"):
            if "__pycache__" in path.parts or path == Path(__file__):
                continue
            content = path.read_text(encoding="utf-8")
            for module in retired_modules:
                if module in content:
                    violations.append(f"{path.relative_to(SERVER_ROOT)}:{module}")

    assert violations == []
