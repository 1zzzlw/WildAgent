"""仅重做已有图纸的屋顶任务，验证真实模型使用原生字段补齐；最多两次调用。"""
import asyncio
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
os.chdir(ROOT / "wild-server")
sys.path.insert(0, str(ROOT / "wild-server"))
from config import config
config.rag.auto_sync = False
config.chat.max_retries = 0
config.chat.timeout = 90
from app.llm import invocation
from app.agent.plan.contracts import PlanDocument
from app.agent.plan.implementation import run_marker_generate
from app.agent.design_flow.compile import compile_node
from app.agent.validation.candidate import evaluate_candidate
from app.rag.trace import rag_trace_scope


async def main():
    state = json.loads((HERE / "parametric_smoke_20261024_092741/state.json").read_text(encoding="utf-8"))
    item = next(i for i in PlanDocument.model_validate(state["plan"]).items if i.kind == "roof")
    state["component_diagnostics"].pop(item.id)
    state["component_fragments"].pop(item.id)
    session = "native_smoke_" + time.strftime("%Y%m%d_%H%M%S")
    state.update(session_id=session, request_id=session, thinking_mode=False)
    output = HERE / session
    output.mkdir()
    calls = 0
    prepare = invocation.prepare_rag_llm_call

    def counted(*args, **kwargs):
        nonlocal calls
        if calls >= 2:
            raise RuntimeError("屋顶任务功能验证达到两次调用上限")
        calls += 1
        return prepare(*args, **kwargs)

    started = time.monotonic()
    summary = {"model": config.chat.name, "scope": "同一批准图纸仅屋顶任务，非完整新生成或模型对照", "call_limit": 2}
    with rag_trace_scope(session, session_id=session, persist=False) as trace:
        invocation.prepare_rag_llm_call = counted
        try:
            updates, status, ids, message, _ = await asyncio.wait_for(run_marker_generate(state, item), timeout=180)
            for key in ("component_diagnostics", "component_fragments"):
                state[key].update(updates.get(key, {}))
            compiled = await compile_node(state)
            state.update(compiled)
            blueprint = compiled["merged_blueprint"]
            evaluation = evaluate_candidate(blueprint, design_document=state["design_document"],
                                            design_brief=state["design_brief"], source="native_completion_smoke")
            diag = state["component_diagnostics"].get(item.id, {})
            completed = {mid: evidence.get("completed_fields", []) for attempt in diag.get("trace", [])
                         for mid, evidence in attempt.get("construction", {}).items()}
            summary.update(status=status, message=message, entity_ids=ids, completed_fields=completed,
                           compile_status=compiled["status"], errors=[e.output for e in evaluation["errors"]],
                           validation=evaluation["snapshot"])
            (output / "candidate.wild").write_text(json.dumps(blueprint, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            summary.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        finally:
            invocation.prepare_rag_llm_call = prepare
            trace.finish(status="completed" if summary.get("status") == "succeeded"
                         and summary.get("compile_status") == "complete" and not summary.get("errors") else "error")
            summary.update(model_calls=calls, seconds=round(time.monotonic()-started, 2))
            for name, value in (("state", state), ("trace", trace.to_dict()), ("summary", summary)):
                (output / (name+".json")).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({k: summary.get(k) for k in ("status", "model_calls", "seconds", "completed_fields", "errors", "error")}, ensure_ascii=False))
            print("output=" + str(output))


if __name__ == "__main__":
    asyncio.run(main())
