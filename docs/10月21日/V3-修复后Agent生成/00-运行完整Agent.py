"""真实调用项目 LangGraph；只记录运行，不代写设计、plan 或构件几何。"""
import os

# 工具子进程缺省环境可能没有 Windows 系统目录；仅补当前子进程。
os.environ.setdefault("SystemRoot", r"C:\Windows")
os.environ.setdefault("WINDIR", os.environ["SystemRoot"])

import argparse
import asyncio
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import shutil
import sys
import traceback

OUT = Path(__file__).resolve().parent
ROOT = next(p for p in OUT.parents if (p / "wild-server" / "config.py").is_file())
SERVER = ROOT / "wild-server"
sys.path.insert(0, str(SERVER))
os.chdir(SERVER)
sys.stdout.reconfigure(encoding="utf-8")


def save(name, value):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str, allow_nan=False), encoding="utf-8")


def append(name, value):
    with (OUT / name).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, default=str) + "\n")


def now():
    return datetime.now(timezone.utc).isoformat()


async def main(resume=False):
    from loguru import logger
    logger.remove()
    logger.add(str(OUT / "运行日志.log"), encoding="utf-8", level="INFO")
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from langgraph.types import Command
    from app.rag.trace import rag_trace_scope

    input_path = OUT / "01-运行输入.json"
    if resume:
        run = json.loads(input_path.read_text(encoding="utf-8"))
    else:
        if input_path.exists():
            raise FileExistsError("该版本已有运行记录；恢复请用 --resume，新实验请新建版本目录")
        baseline = json.loads((OUT.parent / "V1-优化前手工基线" / "01-栖庭别墅-设计图纸.json").read_text(encoding="utf-8"))
        stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d_%H%M%S")
        run = {"started_at": now(), "session_id": "villa_v3_" + stamp, "request_id": "villa_v3_" + stamp,
               "user_message": baseline["requirements"]["source_request"],
               "building_type": "villa", "detail_level": baseline["decisions"]["complexity"]["level"],
               "thinking_mode": True, "current_blueprint": None, "workflow_state": "idle",
               "comparison_note": "沿用V1自然语言需求与detailed档位；V1为人工设计实现，V2为修复前失败记录，V3由修复后的真实项目Agent完成。",
               "review_policy": "用户授权本次端到端对比生成；脚本在项目审核中断处确认继续，保留原图纸，不表示人工看图通过。"}
        save(input_path.name, run)

    with rag_trace_scope(run["request_id"], session_id=run["session_id"]) as trace:
        try:
            # 导入的就是项目入口，没有重写节点、注入手工图纸或替换模型。
            from app.agent.graph import build_generation_graph, plan_recursion_limit
            from app.agent.runtime import bind_reasoning_callback, reset_reasoning_callback, runtime_fingerprint
            from app.services.agent_service import agent_service
            from config import config

            save("02-运行版本.json", {**runtime_fingerprint(), "model": config.chat.name,
                 "provider": config.chat.provider, "thinking_budget": config.chat.thinking_budget,
                 "rag_enabled": config.rag.enabled, "rag_auto_sync": config.rag.auto_sync,
                 "embedding_model": config.embedding.name, "loader": type(agent_service.spec_loader).__name__})
            loader = agent_service.spec_loader
            thread = getattr(loader, "_sync_thread", None)
            print("已加载项目模型与知识配置，等待既有后台知识同步", flush=True)
            while thread is not None and thread.is_alive():
                save("02-知识同步.json", getattr(loader, "sync_status", {}))
                await asyncio.sleep(2)
            save("02-知识同步.json", {"status": getattr(loader, "sync_status", {}),
                 "stats": getattr(loader, "last_sync_stats", None)})

            async def progress(channel, content):
                append("运行进度.jsonl", {"time": now(), "channel": channel, "content": content})
                if channel == "architecture:progress" and "图纸需要修订" in content:
                    save("10-模型与检索追踪-运行中.json", trace.to_dict())
                if channel.endswith(":progress"):
                    print(channel + " " + content.strip(), flush=True)

            token = bind_reasoning_callback(progress)
            try:
                async with AsyncSqliteSaver.from_conn_string(str(OUT / "02-运行检查点.sqlite")) as checkpointer:
                    graph = build_generation_graph(checkpointer=checkpointer)
                    cfg = {"configurable": {"thread_id": run["session_id"]}, "recursion_limit": plan_recursion_limit(0)}
                    saved = await graph.aget_state(cfg)
                    payload = None if saved.values else {k: run[k] for k in (
                        "session_id", "request_id", "user_message", "building_type", "detail_level",
                        "thinking_mode", "current_blueprint", "workflow_state")}
                    seen_reviews = set()
                    sequence = len(list((OUT / "节点输出").glob("*.json")))
                    while True:
                        async for update in graph.astream(payload, config=cfg, stream_mode="updates"):
                            for node, output in update.items():
                                sequence += 1
                                save(f"节点输出/{sequence:04d}-{node}.json", output)
                                append("节点顺序.jsonl", {"time": now(), "sequence": sequence, "node": node})
                                if node == "__interrupt__":
                                    continue
                                if isinstance(output, dict):
                                    for key, file in {"design_document": "03-设计图纸.json", "resolved_design": "03-设计投影.json",
                                          "plan": "04-plan.json", "plan_diag": "04-plan诊断.json", "component_fragments": "05-构件片段-增量.json",
                                          "compile_report": "06-编译报告.json", "validation_snapshot": "07-验收快照.json"}.items():
                                        if key in output:
                                            save(file, output[key])
                                    print("节点完成: " + node + " " + str(output.get("status", "")), flush=True)
                        snapshot = await graph.aget_state(cfg)
                        state = dict(snapshot.values)
                        save("08-完整State.json", state)
                        count = len((state.get("resolved_design") or {}).get("component_markers", []))
                        cfg["recursion_limit"] = plan_recursion_limit(count)
                        interrupts = [i for task in snapshot.tasks for i in task.interrupts]
                        if not interrupts:
                            break
                        for item in interrupts:
                            value = item.value
                            if not isinstance(value, dict) or value.get("type") != "design_review":
                                raise RuntimeError("遇到未知中断，不自动跳过")
                            key = (value["document"]["design_id"], value["document"]["revision"])
                            if not value.get("can_confirm") or key in seen_reviews:
                                raise RuntimeError("图纸不可确认或相同审核重复中断；保留检查点")
                            seen_reviews.add(key)
                            save(f"审核记录/r{key[1]}-审核中断.json", value)
                            append("审核记录/确认.jsonl", {"time": now(), "actor": "Codex runner",
                                 "basis": run["review_policy"], "action": "confirm", "design_id": key[0], "revision": key[1]})
                        payload = Command(resume={"action": "confirm"})

                    for key, file in {"design_document": "03-设计图纸.json", "resolved_design": "03-设计投影.json",
                         "plan": "04-plan.json", "component_fragments": "05-构件片段.json",
                         "component_diagnostics": "05-构件诊断.json", "compile_report": "06-编译报告.json",
                         "validation_snapshot": "07-验收快照.json", "design_fulfillment": "07-履约报告.json"}.items():
                        if key in state:
                            save(file, state[key])
                    final = state.get("final_blueprint") or state.get("merged_blueprint")
                    if final:
                        save("新中式别墅-V3.wild", final)
                    from app.design.repository import design_repository
                    for source, target in ((design_repository.svg_path(run["session_id"]), "03-设计图.svg"),):
                        if source.is_file():
                            shutil.copyfile(source, OUT / target)
                    save("09-运行结果.json", {"finished_at": now(), "status": state.get("status"),
                        "error": state.get("error"), "terminal_model_error": state.get("terminal_model_error"),
                        "has_final_blueprint": bool(final), "plan_node_executed": any(
                            p.name.endswith("-plan.json") for p in (OUT / "节点输出").glob("*.json")),
                        "validation_error_count": state.get("validation_error_count"),
                        "validation_warning_count": state.get("validation_warning_count")})
                    print("运行结束: " + str(state.get("status")), flush=True)
            finally:
                reset_reasoning_callback(token)
        except BaseException as exc:
            failure = {"time": now(), "type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
            save("运行异常.json", failure)
            save("异常记录/" + datetime.now().strftime("%Y%m%d_%H%M%S") + "-" + type(exc).__name__ + ".json", failure)
            print("运行异常: " + type(exc).__name__ + ": " + str(exc), flush=True)
            raise
        finally:
            save("10-模型与检索追踪.json", trace.to_dict())
    # scope 退出后才有最终追踪状态；运行中的快照不能冒充结束状态。
    save("10-模型与检索追踪.json", trace.to_dict())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true", help="恢复同一检查点，不重新生成已完成节点")
    args = parser.parse_args()
    asyncio.run(main(args.resume))
