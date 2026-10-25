"""一次真实构造深化；其余几何沿用保存片段，经当前验收重新装配。"""
import asyncio
from copy import deepcopy
from contextlib import nullcontext
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
REPLAY = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
os.chdir(ROOT / "wild-server")
sys.path.insert(0, str(ROOT / "wild-server"))
from config import config
config.rag.auto_sync = False
config.chat.max_retries = 0
config.chat.timeout = 90
from app.llm import invocation
from app.agent.generation.architecture.design_workflow import refine_construction
from app.design.contracts import DesignDocument
from app.design.compilation import project_drawing
from app.design.construction_systems import construction_spec
from app.agent.plan.workflow import plan_node
from app.agent.plan.contracts import PlanDocument
from app.agent.plan.implementation import _accept_group, run_marker_generate, implementation_blueprint
from app.agent.design_flow.compile import compile_node
from app.rag.trace import rag_trace_scope

SOURCE = ROOT / "docs/10月24日/Agent参数化执行/parametric_smoke_20261024_092741/state.json"
saved = json.loads(SOURCE.read_text(encoding="utf-8"))
session = ("refinement_replay_" if REPLAY else "refinement_smoke_") + time.strftime("%Y%m%d_%H%M%S")
out = HERE / session
out.mkdir(exist_ok=False)
calls = 0
prepare = invocation.prepare_rag_llm_call


def counted_prepare(*args, **kwargs):
    global calls
    if REPLAY or calls >= 1:
        raise RuntimeError("本次仅验证一次构造深化，不调用执行或编译修复模型")
    calls += 1
    return prepare(*args, **kwargs)


invocation.prepare_rag_llm_call = counted_prepare


def write(name, value):
    (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


async def main():
    started = time.monotonic()
    summary = {"model": config.chat.name, "source": str(SOURCE), "scope": "一次真实深化，其余沿用保存片段；非整栋重新生成"}
    if REPLAY:
        summary.update(scope="原始真实深化回复的离线回放；未新增模型调用", replay_source=str(REPLAY))
    state = {}
    with rag_trace_scope(session, session_id=session, persist=False) as trace:
        try:
            source_document = DesignDocument.model_validate(saved["design_document"])
            original = source_document.decisions.model_dump(mode="json")

            def validate(candidate):
                project_drawing(DesignDocument.model_validate({**saved["design_document"], "decisions": candidate}))

            async def original_reply(*args, **kwargs):
                recorded = json.loads(REPLAY.read_text(encoding="utf-8"))
                return SimpleNamespace(content=recorded["output"], token_usage=recorded["token_usage"], call_id=recorded["call_id"], finish_reason="stop")

            with patch("app.agent.generation.architecture.design_workflow.invoke_llm", side_effect=original_reply) if REPLAY else nullcontext():
                revised, diag = await asyncio.wait_for(refine_construction(original,
                    user_request="在既有图纸基础上深化入口、檐口和窗框分格，保持原尺寸、位置和材料构图；采用适用的可执行构造。",
                    diagram_hosts=project_drawing(source_document).projection_elements, validate=validate), timeout=100)
            write("refinement.json", diag)
            if diag["status"] not in {"accepted", "partial"}:
                raise ValueError(diag.get("error", "深化未采用"))
            document = DesignDocument.model_validate({**saved["design_document"], "revision": source_document.revision+1, "decisions": revised})
            write("design.json", document.model_dump(mode="json"))
            state = {"session_id": session, "user_message": "隔离本地构造深化验证", "thinking_mode": False,
                     "design_document": document.model_dump(mode="json"), "resolved_design": project_drawing(document).model_dump(mode="json"),
                     "design_review_status": "approved", "component_fragments": {}, "component_diagnostics": {}}
            state.update(await plan_node(state))
            markers = {m["id"]: m for m in state["resolved_design"]["component_markers"]}
            originals = {mid: (d, r) for d in saved["component_diagnostics"].values() for mid, r in d["implementations"].items()}
            entities = {e["id"]: e for values in saved["component_fragments"].values() for e in values}
            for item in PlanDocument.model_validate(state["plan"]).items:
                base = implementation_blueprint(state)
                records, fragments = {}, []
                buckets = {"elements": [], "components": []}
                for mid in item.target["marker_ids"]:
                    if construction_spec(markers[mid]["design"]) is not None:
                        continue
                    old, record = originals[mid]
                    row = {"id": mid, "geometry": {k: [deepcopy(entities[i]) for i in record["entity_ids"] if i in old[k]] for k in buckets},
                           "materials": old.get("materials", {}), "assets": old.get("assets", {})}
                    base, accepted, records[mid] = _accept_group(base, row, markers[mid])
                    fragments.extend(accepted)
                    for k in buckets:
                        buckets[k].extend(e["id"] for e in row["geometry"][k])
                state["component_fragments"][item.id] = fragments
                state["component_diagnostics"][item.id] = {"implementations": records, **buckets,
                    "materials": base["materials"], "assets": base.get("assets", {}),
                    "trace": [{"tool": "reuse_saved_fragments", "source": str(SOURCE), "marker_ids": list(records), "model_calls": 0}]}
                updates, status, _, message, _ = await run_marker_generate(state, item)
                for key in ("component_fragments", "component_diagnostics"):
                    state[key].update(updates[key])
                if status != "succeeded":
                    raise ValueError(message)
            compiled = await compile_node(state)
            write("compile.json", compiled)
            write("building.wild", compiled["merged_blueprint"])
            summary.update(status=compiled["status"], error=compiled["error"], design_complete=compiled["compile_report"]["design_complete"],
                selected=[d["id"] for d in diag["decisions"] if d["selected"]],
                rejected=diag["rejected"],
                construction_executions=sum(t.get("tool") == "construct_system" for d in state["component_diagnostics"].values() for t in d["trace"]))
        except Exception as exc:
            summary.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        finally:
            write("state.json", state)
            trace.finish(status="completed" if summary.get("status") == "complete" else "error")
            write("trace.json", trace.to_dict())
            summary.update(model_calls=calls, seconds=round(time.monotonic()-started, 3))
            write("summary.json", summary)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
            print("output="+str(out), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
