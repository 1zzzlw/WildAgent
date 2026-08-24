r"""对一条“问题-回答-参考资料”执行可复现 LLM-as-Judge。

输入 JSON：{"question":"...","answer":"...","contexts":["..."]}
运行：
  $env:PYTHONPATH="."
  .\.venv\Scripts\python.exe scripts\rag\judge_rag_answer.py input.json --output report.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[2]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.agent.model_client import create_llm
from app.agent.rag_quality import judge_rag_answer
from config import config


async def _run(input_path: Path, output_path: Path) -> None:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    contexts = payload.get("contexts")
    if not isinstance(contexts, list) or not contexts:
        raise SystemExit("输入 JSON 的 contexts 必须是非空数组")
    result = await judge_rag_answer(
        create_llm(enable_thinking=False, streaming=False),
        question=str(payload.get("question") or ""),
        answer=str(payload.get("answer") or ""),
        contexts=[str(item) for item in contexts],
        model_name=config.chat.name,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Judge 报告已生成: {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="运行单条 RAG LLM-as-Judge")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("scripts/reports/rag_judge.json"))
    args = parser.parse_args()
    asyncio.run(_run(args.input.resolve(), args.output.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
