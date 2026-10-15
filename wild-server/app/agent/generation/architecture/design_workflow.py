"""完整图纸起草与格式修订；不检查引擎能否实现设计。"""
from copy import deepcopy
import json
import re

from app.llm.client import create_llm
from app.llm.invocation import invoke_llm, stream_llm, merge_token_usage
from app.rag.trace import llm_trace_scope
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
    complete_draft = None
    repair_fields = []
    accounting = call_accounting if call_accounting is not None else {"model_calls": 0}
    for attempt in range(1, max_attempts + 1):
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": user_request}]
        accounting["model_calls"] = accounting.get("model_calls", 0) + 1
        thinking = thinking_mode and attempt == 1
        stage = "architecture.generate" if attempt == 1 else "architecture.format_revision"
        with llm_trace_scope(stage=stage, design_hash=_options.get("design_hash")):
            if thinking_mode and on_reasoning_delta:
                async def emit(delta):
                    await on_reasoning_delta("architecture", delta)
                reply = await stream_llm(create_llm(enable_thinking=thinking, streaming=True),
                                         messages, on_reasoning_delta=emit)
            else:
                reply = await invoke_llm(create_llm(enable_thinking=thinking, streaming=False), messages)
        usage = merge_token_usage(usage, reply.token_usage)
        required_key = "massing" if not repair_fields and only_blocks is None and not context else None
        raw = extract_json_object(reply.content or "", required_key=required_key)
        if raw is None and required_key == "massing" and getattr(reply, "finish_reason", None) != "length":
            raw = extract_json_object(reply.content or "")
        issue = "图纸必须是完整 JSON 对象" if not isinstance(raw, dict) else ""
        if not issue and repair_fields and not set(raw).intersection(repair_fields):
            issue = "局部修订缺少待修字段：" + ", ".join(repair_fields)
        if getattr(reply, "finish_reason", None) == "length" and issue:
            issue = "模型输出达到长度上限，图纸 JSON 未完整返回"
        if not issue and allow_design_changes and set(raw) - fields:
            issue = "修订包含未授权字段：" + ", ".join(sorted(set(raw) - fields))
        picked = raw if isinstance(raw, dict) else {}
        if complete_draft is not None and repair_fields and not issue:
            if set(complete_draft) <= raw.keys():
                picked = raw
            else:
                changed = sorted(key for key in set(raw) - set(repair_fields)
                                 if raw[key] != complete_draft.get(key))
                if changed:
                    issue = ("局部修订改动了其他字段：" + ", ".join(changed)
                             + "；请只返回待修字段，或返回包含完整必填字段的整张图纸")
                else:
                    picked = {**complete_draft, **{key: raw[key] for key in repair_fields if key in raw}}
        if (not issue and isinstance(raw, dict)
                and getattr(reply, "finish_reason", None) != "length"
                and only_blocks is None and not context
                and {"massing", "volumes"} <= picked.keys()):
            complete_draft = picked
        if not issue and validate is not None:
            try:
                validate({**context, **picked})
            except (ValueError, TypeError, KeyError, RuntimeError) as exc:
                issue = str(exc)
        diag = {"settled": not issue, "model_calls": attempt, "attempts": attempt,
                "token_usage": usage, "last_issue": issue, "rejected_attempts": rejected,
                "call_id": getattr(reply, "call_id", None)}
        if not issue:
            return picked, diag
        rejected.append({"attempt": attempt, "issue": issue, "output": reply.content,
                         "call_id": getattr(reply, "call_id", None)})
        if on_reasoning_delta:
            await on_reasoning_delta("architecture:progress", f"图纸格式需要修订（{attempt}/{max_attempts}）：{issue}。\n")
        next_fields = list(dict.fromkeys(
            field for field in re.findall(r"/([a-z_]+)", issue)
            if complete_draft is not None and (field in complete_draft or field in fields or field == "floor_layouts")
        ))
        if ("components" in next_fields and "/host" in issue and "facades" in issue
                and complete_draft is not None):
            next_fields.extend(field for field in ("facades", "volumes")
                               if field in complete_draft and field not in next_fields)
        repair_fields = next_fields or (repair_fields if complete_draft is not None else [])
        if repair_fields:
            related = ("components",) if "facades" in repair_fields else (
                ("facades",) if "components" in repair_fields else ()
            )
            reference = {key: complete_draft[key] for key in ("massing", "volumes", *repair_fields, *related)
                         if key in complete_draft}
            host_hint = ("门窗须依附有效围护；按设计只修订需要的字段：门窗标记、共享 facades，"
                         "或 volumes 中对应体量的 facades 覆盖。不必同时修改三者，也不要凭空增删门窗。"
                         if {"components", "facades", "volumes"} <= set(repair_fields) else "")
            prompt = ("你正在修订已存在图纸中的错误。只返回一个完整 JSON 对象，"
                      "仅包含待修顶层字段：" + ", ".join(repair_fields)
                      + "。未列出的字段由系统保留原稿；数组字段须返回修订后的完整数组。"
                      "保持未涉及问题的字段结构与引用 ID，不要重复输出整张图纸。" + host_hint + "错误：" + issue
                      + "\n相关图纸字段：" + json.dumps(reference, ensure_ascii=False))
        else:
            prompt = (base + "\n只修订格式或图纸自身矛盾，保留设计意图。错误：" + issue
                      + "\n上一稿：" + json.dumps(complete_draft or picked, ensure_ascii=False))
    return {}, diag


async def draft_design_blocks(**kwargs):
    return await draft_design(**kwargs)
