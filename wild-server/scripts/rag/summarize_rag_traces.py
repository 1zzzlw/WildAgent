"""汇总 storage/sessions/rag_traces 中的请求级指标。

运行：
    cd E:\\AgentProject\\WildAgent\\wild-server
    .\\.venv\\Scripts\\python.exe scripts\\rag\\summarize_rag_traces.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SERVER_ROOT = Path(__file__).resolve().parents[2]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.agent.rag_reporting import summarize_rag_traces


def main() -> int:
    parser = argparse.ArgumentParser(description="汇总 RAGTrace 运行指标")
    parser.add_argument("--root", type=Path, default=None, help="Trace 根目录")
    parser.add_argument("--output", type=Path, help="可选 JSON 输出文件")
    parser.add_argument("--input-cost-per-million", type=float)
    parser.add_argument("--output-cost-per-million", type=float)
    args = parser.parse_args()

    report = summarize_rag_traces(
        (args.root or SERVER_ROOT / "storage/sessions/rag_traces").resolve(),
        input_cost_per_million=args.input_cost_per_million,
        output_cost_per_million=args.output_cost_per_million,
    )
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"RAGTrace 汇总已生成: {args.output.resolve()}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
