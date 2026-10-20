"""隔离会话运行原生产图；诊断脚本自动确认设计，不代表人工审美验收。"""
import asyncio
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
SERVER = HERE.parents[2] / 'wild-server'
sys.path.insert(0, str(SERVER))
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from app.agent.graph import build_generation_graph, plan_recursion_limit
from app.rag.trace import rag_trace_scope


def save(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


async def main():
    session = f'codex_flow_check_{int(time.time())}'
    graph = build_generation_graph(checkpointer=InMemorySaver())
    config = {'configurable': {'thread_id': session}, 'recursion_limit': plan_recursion_limit(50)}
    inputs = {'session_id': session, 'request_id': session + '_request', 'user_message': '生成一个别墅',
              'building_type': 'villa', 'detail_level': 'standard', 'thinking_mode': False,
              'procedural_materials_enabled': False}
    save('06-输入与边界.json', {'input': inputs, 'timeout_seconds': 600,
         'approval': 'diagnostic auto-confirm via real interrupt, not human approval',
         'checkpoint': 'isolated InMemorySaver; production checkpoint database not used',
         'scope': 'single standard-level end-to-end trial, not aesthetic equivalence proof'})
    events = []
    started = time.monotonic()
    trace = None
    error = None
    approvals = 0

    async def run():
        nonlocal approvals
        invocation = inputs
        while True:
            interrupted = False
            async for update in graph.astream(invocation, config, stream_mode='updates'):
                event = {'elapsed_seconds': round(time.monotonic() - started, 3), 'update': update}
                events.append(event)
                save('06-节点更新.json', events)
                print(json.dumps({'elapsed_seconds': event['elapsed_seconds'], 'nodes': list(update)}, ensure_ascii=False), flush=True)
                if '__interrupt__' in update:
                    interrupted = True
            if not interrupted:
                return
            if approvals >= 1:
                raise RuntimeError('诊断仅自动确认一次，不自动批准之后的设计修订')
            snapshot = await graph.aget_state(config)
            save('06-确认前设计状态.json', snapshot.values)
            approvals += 1
            invocation = Command(resume={'action': 'confirm'})

    with rag_trace_scope(inputs['request_id'], session_id=session, persist=False) as trace:
        try:
            await asyncio.wait_for(run(), timeout=600)
        except Exception as exc:
            error = {'type': type(exc).__name__, 'message': str(exc)}
        finally:
            snapshot = await graph.aget_state(config)
            state = dict(snapshot.values)
            save('06-最终State.json', state)
    save('06-模型与检索Trace.json', trace.to_dict())
    candidate = state.get('final_blueprint') or state.get('merged_blueprint')
    if candidate:
        save('06-真实流程候选.wild', candidate)
    native = [t for diag in (state.get('component_diagnostics') or {}).values()
              for t in diag.get('trace', []) if t.get('stage') == 'native']
    summary = {'session_id': session, 'elapsed_seconds': round(time.monotonic()-started, 3),
               'status': state.get('status'), 'error': error or state.get('error'),
               'validation_error_count': state.get('validation_error_count'),
               'validation_warning_count': state.get('validation_warning_count'),
               'native_attempts': len(native), 'native_marker_ids': [i for t in native for i in t.get('marker_ids', [])],
               'native_failures': [t.get('errors') for t in native if t.get('errors')],
               'llm_calls': len(trace.to_dict().get('llm_calls', [])),
               'diagnostic_auto_approvals': approvals, 'next_nodes': snapshot.next,
               'candidate_saved': bool(candidate)}
    save('06-试跑摘要.json', summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
