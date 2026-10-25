"""完整图纸起草与字段级修订；不检查引擎能否实现设计。"""

from copy import deepcopy
import json
import re

from app.llm.client import create_llm
from app.llm.invocation import invoke_llm, stream_llm, merge_token_usage
from app.rag.trace import llm_trace_scope
from app.utils.json_extractor import extract_json_object
from app.design.parametric import expand_parameters, PARAMETRIC_PROTOCOL
from .design_blocks import ordered_blocks


async def refine_construction(draft, *, user_request, diagram_hosts, validate, call_accounting=None):
    """审核前一次构造深化；只补 form.construction，失败保留原设计并报告。"""
    from app.design.construction_systems import construction_spec, SYSTEM_PROTOCOL
    targets = [c for c in draft.get("components", []) if c.get("type") in {"door", "window", "cornice"}
               and construction_spec(c) is None and all((c.get("size") or {}).get(k) for k in ("width", "height"))]
    if not targets:
        return draft, {"status": "not_needed", "model_calls": 0}
    target_ids = {c["id"] for c in targets}
    prompt = ("深化已经形成的建筑设计，只决定当前标记的构造层次、框/扇/分格、材料分工及入口遮蔽。"
              "体量、房间、洞口位置与尺寸、原有 form 意图保持不变，不添加/删除构件，不重复已有雨棚和支柱。"
              "先理解整体设计，再为适用部位选择完整构造；不适用、已充分表达或需要改变布局时，construction 写 null 并说明原因。"
              "只返回 JSON {\"details\":[{\"ids\":[\"标记ID\"],\"construction\":{...},\"reason\":\"设计理由\"}]}。"
              "相同构造可在 ids 中列出多个标记；每个 targets ID 恰好出现一次。"
              "按真实墙范围确定门窗套和入口顶板，不能越墙边/墙顶；保留特殊门形、侧亮窗等描述，系统无法表达时不要硬套。"
              + SYSTEM_PROTOCOL + PARAMETRIC_PROTOCOL)
    diag = {"status": "rejected", "model_calls": 1, "target_ids": sorted(target_ids)}
    if call_accounting is not None:
        call_accounting["model_calls"] += 1
    try:
        with llm_trace_scope(stage="architecture_construction"):
            reply = await invoke_llm(create_llm(enable_thinking=False, streaming=False), [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps({"request": user_request, "current_design": draft,
                    "targets": sorted(target_ids), "diagram_hosts": diagram_hosts}, ensure_ascii=False)}])
        diag.update(call_id=getattr(reply, "call_id", None), output=reply.content, token_usage=reply.token_usage)
        if getattr(reply, "finish_reason", None) in {"length", "max_tokens"}:
            raise ValueError("构造深化输出未完整返回")
        raw = extract_json_object(reply.content or "", outer_only=True, raise_on_error=True)
        raw, expansion = expand_parameters(raw, facts={"current_design": draft})
        if expansion:
            diag["parameter_expansion"] = expansion
        if set(raw) != {"details"} or not isinstance(raw["details"], list):
            raise ValueError("构造深化仅接受 details 数组")
        seen = set()
        for detail in raw["details"]:
            if (not isinstance(detail, dict) or set(detail) != {"ids", "construction", "reason"}
                    or not isinstance(detail["ids"], list) or not detail["ids"]
                    or not isinstance(detail["reason"], str) or not detail["reason"].strip()):
                raise ValueError("每项深化须包含 ids、construction 和非空 reason")
            for mid in detail["ids"]:
                if not isinstance(mid, str) or mid not in target_ids or mid in seen:
                    raise ValueError("构造深化标记越界或重复")
                seen.add(mid)
        if seen != target_ids:
            raise ValueError("构造深化遗漏了目标标记")
        candidate, decisions, rejected = deepcopy(draft), [], []
        for detail in raw["details"]:
            selected, error = detail["construction"] is not None, None
            if selected:
                proposed = deepcopy(candidate)
                for component in proposed["components"]:
                    if component["id"] in detail["ids"]:
                        form = component.get("form") or {}
                        form = {"description": form} if isinstance(form, str) else form
                        component["form"] = {**form, "construction": deepcopy(detail["construction"])}
                try:
                    validate(proposed)
                    candidate = proposed
                except (ValueError, TypeError, KeyError, RuntimeError) as exc:
                    selected, error = False, str(exc)
                    rejected.append({"ids": detail["ids"], "error": error})
            decisions.extend({"id": mid, "selected": selected, "reason": detail["reason"], **({"error": error} if error else {})}
                             for mid in detail["ids"])
        status = "partial" if rejected and any(d["selected"] for d in decisions) else "rejected" if rejected else "accepted"
        diag.update(status=status, decisions=decisions, rejected=rejected)
        if rejected:
            diag["error"] = "；".join(f"{','.join(r['ids'])}：{r['error']}" for r in rejected)
        return candidate, diag
    except Exception as exc:
        # 深化是可选步骤；服务异常也保留已经验证的图纸，取消信号仍向上传播。
        diag.update(error=str(exc), error_type=type(exc).__name__)
        return draft, diag


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
    rejected, repairs, expansions, usage = [], [], [], None
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
            use_thinking = thinking_mode and attempt == 1
            if use_thinking and on_reasoning_delta:

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
                    create_llm(enable_thinking=use_thinking, streaming=False), messages
                )

        usage = merge_token_usage(usage, reply.token_usage)

        raw, issue = None, ""
        try:
            if getattr(reply, "finish_reason", None) in {"length", "max_tokens"}:
                raise ValueError("模型输出达到长度上限，图纸或补丁未完整返回")
            raw = extract_json_object(reply.content or "", outer_only=True, raise_on_error=True)
        except ValueError as exc:
            issue = str(exc)

        # 准备返回给调用方的数据
        # 准备接受校验的候选图纸
        # 是否已经进入候选图纸的校验阶段
        picked, candidate, checked = raw or {}, None, False

        if not issue:
            try:
                source = deepcopy(raw)
                raw, expansion = expand_parameters(raw, facts={"current_design": draft or context})
                picked = raw
                if expansion:
                    expansions.append({"attempt": attempt, "source": source, **expansion})
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
            "parameter_expansions": expansions,
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
                + PARAMETRIC_PROTOCOL
                + "\nfacts.current_design 是当前已展开图纸；补丁路径仍指向展开后的实例。"
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
                + json.dumps(draft if draft is not None else picked or {"unparsed_output": reply.content}, ensure_ascii=False)
            )
    return {}, diag
