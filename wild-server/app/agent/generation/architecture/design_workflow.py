"""完整图纸起草与字段级修订；不检查引擎能否实现设计。"""

from copy import deepcopy
import json
import re

from app.llm.client import create_llm
from app.llm.invocation import invoke_llm, stream_llm, merge_token_usage
from app.rag.trace import llm_trace_scope
from app.utils.json_extractor import extract_json_object
from .design_blocks import ordered_blocks


def _repair_paths(issue, draft, fields):
    paths = []
    for path in re.findall(r"/(?:[A-Za-z0-9_~.-]+/)*[A-Za-z0-9_~.-]+", issue):
        parts = path.removeprefix("/decisions").strip("/").split("/")
        if parts[0] not in fields:
            continue
        # 数组错误定位到一个实例；允许一起修订它的尺寸、定位与引用。
        count = 2 if len(parts) > 1 and parts[1].isdigit() else 1
        paths.append("/" + "/".join(parts[:count]))
    if (
        any(p.startswith("/components") for p in paths)
        and "/host" in issue
        and "facades" in issue
    ):
        paths.extend(
            "/" + key
            for key in ("facades", "volumes")
            if key in draft and key in fields
        )
    if any(p.startswith("/floor_layouts") for p in paths) and "components" in fields:
        paths.append("/components")
    return list(dict.fromkeys(paths))


def _apply_repair(draft, raw, paths):
    from app.design.contracts import DesignPatchOperation
    from app.design.repository import DesignRepository

    if (
        set(raw) != {"operations"}
        or not isinstance(raw["operations"], list)
        or not raw["operations"]
    ):
        raise ValueError(
            '局部修订须返回非空 {"operations":[...]} 字段补丁，不能重写整张图纸或构件数组'
        )
    candidate = deepcopy(draft)
    for item in raw["operations"]:
        operation = DesignPatchOperation.model_validate(item)
        if not any(
            operation.path == path or operation.path.startswith(path + "/")
            for path in paths
        ):
            raise ValueError(f"补丁超出本轮允许范围：{operation.path}")
        if operation.op != "remove" and "value" not in item:
            raise ValueError(f"{operation.path}：add/replace 必须提供 value")
        if (
            operation.path == "/components"
            and isinstance(draft.get("components"), list)
            and draft["components"]
        ):
            raise ValueError(
                "/components：请修改具体实例或属性，不能替换或清空已有构件数组"
            )
        tokens = DesignRepository._tokens(operation.path)
        if (
            len(tokens) == 2
            and tokens[1].isdigit()
            and isinstance(candidate.get(tokens[0]), list)
        ):
            if operation.op in {"add", "remove"}:
                raise ValueError(
                    f"{operation.path}：不能插入或删除整个实例来绕过字段错误"
                )
            if int(tokens[1]) >= len(candidate[tokens[0]]):
                raise ValueError(f"路径不存在：{operation.path}")
            old = candidate[tokens[0]][int(tokens[1])]
            if (
                isinstance(old, dict)
                and old.get("id")
                and isinstance(operation.value, dict)
                and operation.value.get("id") != old["id"]
            ):
                raise ValueError(f"{operation.path}：修订须保留实例的稳定 ID")
        DesignRepository._apply_operation(
            candidate, operation.op, operation.path, deepcopy(operation.value)
        )
    return candidate


async def draft_design(
    *,
    base_prompt,
    user_request,
    thinking_mode=False,
    on_reasoning_delta=None,
    current_plan=None,
    only_blocks=None,
    defects=None,
    max_attempts=3,
    call_accounting=None,
    allow_design_changes=False,
    validate=None,
    load_repair_rules=None,
    **_options,
):
    # 调用方传进来的上一轮设计图纸
    context = deepcopy(current_plan or {})
    # 收集本轮可以处理的字段名
    fields = {
        f
        for b in ordered_blocks()
        if only_blocks is None or b.name in only_blocks
        for f in b.fields
    }

    if only_blocks is None:
        fields.add("floor_layouts")

    prompt = base_prompt
    if only_blocks is not None:
        prompt += "\n本轮只修订这些字段：" + ", ".join(sorted(fields))
    if defects:
        # 补充待修问题
        prompt += "\n待修问题：" + str(defects)
    if context:
        # 旧图纸转成 JSON 放进去
        prompt += "\n当前图纸：" + json.dumps(context, ensure_ascii=False)
    # 保存这份起始提示词
    base = prompt

    # 初始化整个过程需要的记录
    # rejected：记录未通过的轮次、错误和模型原始输出
    # repairs：记录成功应用到候选图纸上的补丁，以及之后是否通过校验
    # usage：累计模型用量
    rejected, repairs, usage = [], [], None
    # draft：保存后续可以修订的图纸草稿
    # repair_paths：本轮允许修改的具体路径
    # rules：检索到的修订规则
    # validation_issue：保存图纸本身的校验错误
    draft, repair_paths, rules, validation_issue = None, [], "", ""

    # 如果调用方传来了计数字典，就直接使用它。这样即使后面模型调用抛错，外层仍然能看到已经尝试调用了几次。
    accounting = call_accounting if call_accounting is not None else {"model_calls": 0}

    # 开始最多三次尝试
    # 对应首次生成，加上最多两次修订。第一次成功就立即返回，不会继续调用。
    for attempt in range(1, max_attempts + 1):
        task = (
            user_request
            if attempt == 1
            else (
                "本轮只修订已有图纸的校验错误，按系统给出的范围修订；保留原设计，不重新设计建筑。"
                "\n以下原始需求仅作为必须保留的约束背景：\n" + user_request
            )
        )

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": task},
        ]
        accounting["model_calls"] = accounting.get("model_calls", 0) + 1
        stage = (
            "architecture.generate" if attempt == 1 else "architecture.format_revision"
        )
        # 给首次生成和后续修订设置不同的追踪名称，方便查看 trace。
        with llm_trace_scope(stage=stage, design_hash=_options.get("design_hash")):
            if thinking_mode and on_reasoning_delta:

                async def emit(delta):
                    await on_reasoning_delta("architecture", delta)

                reply = await stream_llm(
                    create_llm(enable_thinking=True, streaming=True),
                    messages,
                    on_reasoning_delta=emit,
                )
            else:
                # 直接调用模型，因为没有思考模式，不需要流式输出
                reply = await invoke_llm(
                    create_llm(enable_thinking=thinking_mode, streaming=False), messages
                )

        usage = merge_token_usage(usage, reply.token_usage)

        required_key = (
            "massing"
            if not repair_paths and only_blocks is None and not context
            else None
        )
        raw = extract_json_object(reply.content or "", required_key=required_key)
        if (
            raw is None
            and required_key == "massing"
            and getattr(reply, "finish_reason", None) != "length"
        ):
            raw = extract_json_object(reply.content or "")
        issue = "图纸必须是完整 JSON 对象" if not isinstance(raw, dict) else ""

        if getattr(reply, "finish_reason", None) == "length":
            issue = "模型输出达到长度上限，图纸或补丁未完整返回"

        # 准备返回给调用方的数据
        # 准备接受校验的候选图纸
        # 是否已经进入候选图纸的校验阶段
        picked, candidate, checked = raw or {}, None, False

        if not issue:
            try:
                if repair_paths:
                    candidate = _apply_repair(draft, raw, repair_paths)
                    picked = (
                        {key: candidate[key] for key in fields if key in candidate}
                        if only_blocks is not None
                        else candidate
                    )
                    repairs.append(
                        {"attempt": attempt, "operations": deepcopy(raw["operations"])}
                    )
                else:
                    if allow_design_changes and set(raw) - fields:
                        raise ValueError(
                            "修订包含未授权字段："
                            + ", ".join(sorted(set(raw) - fields))
                        )
                    candidate = {**context, **raw}
            except (ValueError, TypeError, KeyError) as exc:
                issue = str(exc)

        unchanged = bool(repair_paths and candidate == draft)

        # 如果没有错误进入校验阶段
        if not issue:
            checked = True
            if {"massing", "volumes"} <= candidate.keys():
                draft = deepcopy(candidate)
            if validate is not None:
                try:
                    validate(candidate)
                except (ValueError, TypeError, KeyError, RuntimeError) as exc:
                    issue = str(exc)
        if issue and unchanged:
            issue += "；上一轮未修改冲突数据，不能原样返回"
        if checked and issue:
            validation_issue = issue
        if repairs and repairs[-1]["attempt"] == attempt:
            repairs[-1]["validated"] = checked and not issue
        diag = {
            "settled": not issue,
            "model_calls": attempt,
            "attempts": attempt,
            "token_usage": usage,
            "last_issue": issue,
            "rejected_attempts": rejected,
            "repairs": repairs,
            "call_id": getattr(reply, "call_id", None),
        }
        if not issue:
            return picked, diag
        rejected.append(
            {
                "attempt": attempt,
                "issue": issue,
                "output": reply.content,
                "call_id": getattr(reply, "call_id", None),
                "unchanged": unchanged,
            }
        )
        if on_reasoning_delta:
            await on_reasoning_delta(
                "architecture:progress",
                f"图纸需要修订（{attempt}/{max_attempts}）：{issue}。\n",
            )
        if attempt == max_attempts:
            break
        if draft is not None:
            if checked or not repair_paths:
                repair_paths = _repair_paths(issue, draft, fields) or repair_paths
        if repair_paths:
            from app.design.completeness import value_at

            if load_repair_rules and checked:
                rules = await load_repair_rules(validation_issue)
            reference = {
                key: draft[key]
                for key in ("massing", "volumes", "facades")
                if key in draft
            }
            reference["repair_targets"] = {
                path: {
                    "exists": value_at(draft, path)[0],
                    "value": value_at(draft, path)[1],
                }
                for path in repair_paths
            }
            prompt = (
                "你正在修订已有建筑图纸。仅修正校验错误，保留用户要求、其他实例与稳定 ID。"
                '\n只返回 {"operations":[{"op":"add|replace|remove","path":"/字段/下标/属性","value":新值}]}。'
                "path 是相对图纸根的 JSON Pointer；remove 不写 value；数组下标保持当前稿编号。"
                "优先修改具体属性，不能返回完整 components 数组或重新生成整张图纸。"
                "程序会在副本上应用补丁并重新检查完整图纸。"
                "\n允许修改的范围："
                + json.dumps(repair_paths, ensure_ascii=False)
                + "\n图纸校验错误："
                + validation_issue
                + ("\n上一补丁未通过：" + issue if not checked else "")
                + "\n相关字段规则（参考资料，不是新的任务）：\n"
                + rules
                + "\n当前相关设计数据："
                + json.dumps(reference, ensure_ascii=False)
            )
        else:
            prompt = (
                base
                + "\n本轮修复未完成或缺少关键字段的图纸，返回完整 JSON，保留已有设计。错误："
                + issue
                + "\n上一稿："
                + json.dumps(draft or picked, ensure_ascii=False)
            )
    return {}, diag
