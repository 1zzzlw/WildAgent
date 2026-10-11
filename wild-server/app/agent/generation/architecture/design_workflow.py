"""完整图纸起草与格式修订；不检查引擎能否实现设计。"""
from copy import deepcopy
import json

from app.llm.client import create_llm
from app.llm.invocation import invoke_llm, stream_llm, merge_token_usage
from app.utils.json_extractor import extract_json_object
from .design_blocks import ordered_blocks


async def draft_design(*, base_prompt, user_request, thinking_mode=False,
                       on_reasoning_delta=None, current_plan=None, only_blocks=None,
                       defects=None, max_attempts=3, call_accounting=None,
                       allow_design_changes=False, validate=None, **_options):
    context = deepcopy(current_plan or {})
    fields = {f for b in ordered_blocks("standard") if only_blocks is None or b.name in only_blocks
              for f in b.fields}
    prompt = base_prompt + "\n设计可以包含新构件和新造型，使用 description、form 和扩展字段完整描述；不要提前声明无法实现。"
    if only_blocks is not None:
        prompt += "\n本轮只修订这些字段：" + ", ".join(sorted(fields))
    if defects:
        prompt += "\n待修问题：" + str(defects)
    if context:
        prompt += "\n当前图纸：" + json.dumps(context, ensure_ascii=False)
    base = prompt
    rejected, usage = [], None
    accounting = call_accounting if call_accounting is not None else {"model_calls": 0}
    for attempt in range(1, max_attempts + 1):
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": user_request}]
        accounting["model_calls"] = accounting.get("model_calls", 0) + 1
        if thinking_mode and on_reasoning_delta:
            async def emit(delta):
                await on_reasoning_delta("architecture", delta)
            reply = await stream_llm(create_llm(enable_thinking=True, streaming=True),
                                     messages, on_reasoning_delta=emit)
        else:
            reply = await invoke_llm(create_llm(enable_thinking=thinking_mode, streaming=False), messages)
        usage = merge_token_usage(usage, reply.token_usage)
        raw = extract_json_object(reply.content or "")
        issue = "图纸必须是 JSON 对象" if not isinstance(raw, dict) else ""
        if not issue and allow_design_changes and set(raw) - fields:
            issue = "修订包含未授权字段：" + ", ".join(sorted(set(raw) - fields))
        picked = raw if isinstance(raw, dict) else {}
        if not issue and validate is not None:
            try:
                validate({**context, **picked})
            except (ValueError, TypeError, KeyError, RuntimeError) as exc:
                issue = str(exc)
        diag = {"settled": not issue, "model_calls": attempt, "attempts": attempt,
                "token_usage": usage, "last_issue": issue, "rejected_attempts": rejected}
        if not issue:
            return picked, diag
        rejected.append({"attempt": attempt, "issue": issue, "output": reply.content})
        if on_reasoning_delta:
            await on_reasoning_delta("architecture:progress", f"图纸格式需要修订（{attempt}/{max_attempts}）：{issue}。\n")
        prompt = base + "\n只修订格式或图纸自身矛盾，保留设计意图。错误：" + issue + "\n上一稿：" + json.dumps(picked, ensure_ascii=False)
    return {}, diag


async def draft_design_blocks(**kwargs):
    return await draft_design(**kwargs)
