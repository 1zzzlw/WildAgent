"""GitLab/Jenkins 共用的离线门禁；不调用真实模型或线上向量索引。"""
from pathlib import Path
import os
import subprocess
import sys
from tempfile import TemporaryDirectory

SERVER_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    with TemporaryDirectory(prefix="wild-agent-ci-") as storage:
        env = {**os.environ, "PYTHONPATH": str(SERVER_ROOT), "PYTHONDONTWRITEBYTECODE": "1",
               "CHAT__NAME": "ci-dummy-chat", "CHAT__API_KEY": "ci-placeholder",
               "CHAT__BASE_URL": "http://127.0.0.1:9/v1", "RAG__ALLOW_HASH_FALLBACK": "true",
               "RAG__AUTO_SYNC": "false", "RAG__PERSIST_DIR": storage,
               "RAG__TRACE__ROOT_DIR": str(Path(storage) / "rag_traces"),
               "LANGSMITH_TRACING": "false", "LANGCHAIN_TRACING_V2": "false",
               "EMBEDDING__API_KEY": "", "RERANK__API_KEY": "", "RAG__RERANK_ENABLED": "false"}
        commands = [
            ["-m", "pytest", "-q", "tests/design", "tests/plan", "tests/validators",
             "tests/network", "tests/repair", "tests/rag",
             "tests/components/test_architecture_plan.py", "tests/components/test_material_plan.py",
             "tests/agent/test_agent_graph_execution.py", "tests/agent/test_agent_graph_routing.py",
             "tests/agent/test_plan_graph.py", "tests/agent/test_agent_delivery.py"],
            ["scripts/rag/eval_retrieval.py", "--embedding", "hash", "--top-k", "5",
             "--json-output", "scripts/reports/ci_rag_eval.json",
             "--output", "scripts/reports/ci_rag_eval.md", "--no-log-output"],
            ["scripts/rag/check_rag_quality_gate.py", "scripts/reports/ci_rag_eval.json"],
        ]
        for arguments in commands:
            result = subprocess.run([sys.executable, *arguments], cwd=SERVER_ROOT, env=env)
            if result.returncode:
                return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
