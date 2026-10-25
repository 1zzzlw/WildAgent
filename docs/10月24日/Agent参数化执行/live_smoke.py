"""一次有界真实生成；仅本地验证会话跳过人工审核等待，不改变生产审核节点。"""
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

calls = 0
prepare = invocation.prepare_rag_llm_call


def counted_prepare(*args, **kwargs):
    global calls
    if calls >= 18:
        raise RuntimeError("本地功能验证达到 18 次模型调用上限")
    calls += 1
    print(f"model_call={calls}", flush=True)
    return prepare(*args, **kwargs)


invocation.prepare_rag_llm_call = counted_prepare

from app.agent.generation.architecture.workflow import architecture_planner
from app.agent.generation.material.workflow import material_planner
from app.agent.plan.workflow import plan_node, execute_node, replanner_node
from app.agent.design_flow.compile import compile_node
from app.agent.validation.workflow import validate_node
from app.agent.graph import _after_plan, _after_execute, _after_replanner
from app.rag.trace import rag_trace_scope

request = """设计并生成一栋单层现代庭院小别墅。两个矩形翼体组成L形围院，总体范围控制在14×12米内。
有明确入口、客厅与卧室的功能安排、面向内院的采光窗、屋顶和檐下层次；入口旁设计一组木格栅遮阳，体现重复细部。
以浅色墙面、木色格栅和深灰屋面形成协调材料构图。庭院可保留空地，不扩展道路、车辆、复杂植栽和家具套餐。
这次重点是完整且可落实的体量、开口和构造；构件不要互相重复。共享尺寸使用parameters，重复声明由程序展开，不能在裸JSON数字中写算式。
主体直墙和矩形楼板采用walls/slabs构造声明；特殊构造保持原生geometry。"""
session = "parametric_smoke_" + time.strftime("%Y%m%d_%H%M%S")
out = HERE / session
out.mkdir(exist_ok=False)
state = {"session_id": session, "request_id": session, "user_message": request, "intent": "generate",
         "intent_target_kind": "architecture", "intent_profile": "custom", "detail_level": "standard",
         "thinking_mode": False, "style_preference": [], "procedural_materials_enabled": False,
         "component_fragments": {}, "component_diagnostics": {}}
steps = []
started = time.monotonic()


def save():
    (out / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


async def step(name, function):
    print("stage=" + name, flush=True)
    updates = await function(state)
    for key, value in updates.items():
        if key in {"component_fragments", "component_diagnostics", "tool_trace"}:
            state.setdefault(key, {}).update(value)
        else:
            state[key] = value
    steps.append({"stage": name, "seconds": round(time.monotonic()-started, 2),
                  "status": state.get("status"), "error": state.get("error"), "model_calls": calls})
    save()


async def generate():
    await step("architecture", architecture_planner)
    if state.get("status") == "failed":
        return
    await step("material_plan", material_planner)
    if state.get("status") == "failed":
        return
    state["design_review_status"] = "approved"
    await step("plan", plan_node)
    route = _after_plan(state)
    for _ in range(80):
        if route == "execute":
            await step("execute", execute_node)
            route = _after_execute(state)
        elif route == "replanner":
            await step("replanner", replanner_node)
            route = _after_replanner(state)
        else:
            break
    await step("compile", compile_node)
    await step("final_validate", validate_node)


async def main():
    error = None
    with rag_trace_scope(session, session_id=session, persist=False) as trace:
        try:
            await asyncio.wait_for(generate(), timeout=360)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            state.update(status="failed", error=error)
        finally:
            save()
            trace.finish(status="completed" if state.get("status") == "complete" else "error")
            (out / "trace.json").write_text(json.dumps(trace.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            blueprint = state.get("final_blueprint") or state.get("merged_blueprint")
            if blueprint:
                (out / "building.wild").write_text(json.dumps(blueprint, ensure_ascii=False, indent=2), encoding="utf-8")
            summary = {"model": config.chat.name, "request": request, "status": state.get("status"),
                       "error": state.get("error") or error, "model_calls": calls, "call_limit": 18,
                       "seconds": round(time.monotonic()-started, 2), "steps": steps,
                       "review": "仅隔离本地验证会话确认图纸；未改变生产审核流程", "rendered": False}
            (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({k: summary[k] for k in ("status", "model_calls", "seconds", "error")}, ensure_ascii=False), flush=True)
            print("output=" + str(out), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
