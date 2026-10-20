"""只运行 architecture 节点；不进入审核、plan、构件生成或场景保存。"""
import asyncio
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
SERVER = HERE.parents[2] / 'wild-server'
sys.path.insert(0, str(SERVER))
from app.agent.generation.architecture.workflow import architecture_planner
from app.rag.trace import rag_trace_scope


def save(name, value):
    (HERE/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


async def main():
    sid = f'architecture_only_{int(time.time())}'
    state = {'user_message': '生成一个别墅', 'intent_profile': 'villa', 'detail_level': 'minimal',
             'thinking_mode': False, 'style_preference': [], 'session_id': sid, 'request_id': sid}
    save('06-输入.json', state)
    started = time.monotonic()
    with rag_trace_scope(sid, session_id=sid, persist=False) as trace:
        try:
            result = await asyncio.wait_for(architecture_planner(state), timeout=240)
        except Exception as exc:
            result = {'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'}
    save('06-输出.json', result)
    save('06-原始模型记录.json', trace.to_dict())
    summary = {'elapsed_seconds': round(time.monotonic()-started, 3), 'error': result.get('error'),
               'review_status': result.get('design_review_status'),
               'calls': len(trace.to_dict().get('llm_calls', [])),
               'architecture_diag': {k:v for k,v in result.get('architecture_diag', {}).items()
                                     if k not in {'raw_plan', 'rejected_attempts', 'programs'}},
               'scope': 'architecture only, no full building generation or rendering'}
    save('06-试跑摘要.json', summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
