"""调用当前配置的真实模型，仅执行 architecture；不编译、不渲染。

在 wild-server 下运行：.venv/Scripts/python.exe ../docs/10月20日优化/architecture最后修复/02-真实模型测试.py
可选参数：输入 JSON 文件路径、输出目录。默认使用原请求“生成一个别墅”。
"""
import asyncio
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "wild-server"))

from config import config
from app.agent.generation.architecture import design_workflow
from app.agent.generation.architecture.workflow import architecture_planner

OUTPUT = Path(sys.argv[2]) if len(sys.argv)>2 else Path(__file__).parent / "真实调用-1"
OUTPUT.mkdir(parents=True, exist_ok=True)
STATE = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")) if len(sys.argv)>1 else {
    "user_message":"生成一个别墅", "detail_level":"minimal", "intent_profile":"villa", "thinking_mode":True,
}


def save(name, value):
    (OUTPUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


async def main():
    save("input.json", STATE)
    save("model.json", {"name":config.chat.name, "provider":config.chat.provider,
        "thinking_budget":config.chat.thinking_budget, "timeout":config.chat.timeout,
        "started_at":datetime.now().astimezone().isoformat(), "scope":"architecture only"})
    original = design_workflow.invoke_llm
    calls = 0

    async def observed(llm, messages, **kwargs):
        nonlocal calls
        calls += 1
        save(f"call-{calls}-request.json", {"messages":messages,
            "tools":llm.kwargs.get("tools",[]),"started_at":datetime.now().astimezone().isoformat()})
        print(f"call {calls} started", flush=True)
        reply = await original(llm, messages, **kwargs)
        save(f"call-{calls}-response.json", asdict(reply))
        print(f"call {calls} returned: {[c['name'] for c in reply.tool_calls]}", flush=True)
        return reply

    design_workflow.invoke_llm = observed
    result = await architecture_planner(STATE)
    save("result.json", result)
    if result.get("design_document"):
        save("design.json", result["design_document"])
        save("resolved.json", result["resolved_design"])
    diag = result["architecture_diag"]
    print(json.dumps({"accepted":bool(result.get("design_document")), "calls":diag["model_calls"],
        "error":result.get("error"), "total_ms":diag["total_ms"], "token_usage":diag.get("token_usage")}, ensure_ascii=False), flush=True)


if __name__=="__main__":
    asyncio.run(main())
