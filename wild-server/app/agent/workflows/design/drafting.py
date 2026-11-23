"""完整图纸起草与字段级修订；不检查引擎能否实现设计。"""

from copy import deepcopy
import json
import re

from app.agent.prompts.design_revision import build_design_repair_prompt
from app.agent.runtime import create_llm
from app.infrastructure.llm.invocation import invoke_llm
from app.infrastructure.llm.invocation import stream_llm
from app.infrastructure.llm.invocation import merge_token_usage
from app.infrastructure.observability.trace import llm_trace_scope
from app.domain.blueprint.json_extractor import extract_json_object
from app.domain.design.parametric import expand_parameters
from app.domain.design.architecture.design_blocks import ordered_blocks


def _repair_paths(issue, draft, fields, *, target_draft=None):
    from app.domain.design.coordinates import entity_reference_paths

    paths = []
    for path in re.findall(r"/(?:[A-Za-z0-9_~.-]+/)*[A-Za-z0-9_~.-]+", issue):
        parts = path.removeprefix("/decisions").strip("/").split("/")
        if parts[0] not in fields:
            continue
        records = draft.get(parts[0])
        if isinstance(records, list) and len(parts) > 1 and not parts[1].isdigit():
            # 空间校验有时用稳定 ID 报错，补丁仍须使用当前数组下标。
            for index, record in enumerate(records):
                if isinstance(record, dict) and record.get("id") == parts[1]:
                    parts[1] = str(index)
                    break
        # 数组错误定位到一个实例；允许一起修订它的尺寸、定位与引用。
        count = 2 if len(parts) > 1 and parts[1].isdigit() else 1
        paths.append("/" + "/".join(parts[:count]))
    wall_ids = set()
    for path in paths:
        parts = path.strip("/").split("/")
        walls = draft.get("walls")
        if parts[0] == "walls" and len(parts) == 2 and isinstance(walls, list):
            index = int(parts[1])
            if index < len(walls) and isinstance(walls[index], dict) and walls[index].get("id"):
                wall_ids.add(walls[index]["id"])
    for path in entity_reference_paths(draft, wall_ids):
        parts = path.strip("/").split("/")
        if parts[0] in fields:
            paths.append("/" + "/".join(parts[:2]))
    if ("walls" in fields and isinstance(draft.get("walls"), list)
            and any(path.startswith("/components") for path in paths)
            and ("宿主" in issue or "/host" in issue)):
        paths.append("/walls/-")
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
    if target_draft is not None:
        mapped = []
        for path in paths:
            parts = path.strip("/").split("/")
            source = draft.get(parts[0])
            target = target_draft.get(parts[0])
            if (len(parts) == 2 and parts[1].isdigit()
                    and isinstance(source, list) and isinstance(target, list)
                    and int(parts[1]) < len(source)):
                record = source[int(parts[1])]
                if isinstance(record, dict) and record.get("id"):
                    parts[1] = "-"
                    for index, existing in enumerate(target):
                        if isinstance(existing, dict) and existing.get("id") == record["id"]:
                            parts[1] = str(index)
                            break
                    path = "/" + "/".join(parts)
            mapped.append(path)
        paths = mapped
    return list(dict.fromkeys(paths))


def _apply_repair(draft, raw, paths):
    from app.domain.design.contracts import DesignPatchOperation
    from app.infrastructure.persistence.repositories.designs import DesignRepository

    if (
        set(raw) != {"operations"}
        or not isinstance(raw["operations"], list)
        or not raw["operations"]
    ):
        raise ValueError(
            '局部修订须返回非空 {"operations":[...]} 字段补丁，不能重写整张图纸或构件数组'
        )
    candidate = deepcopy(draft)
    wall_removals = {}
    for item in raw["operations"]:
        operation = DesignPatchOperation.model_validate(item)
        if not any(
            operation.path == path or operation.path.startswith(path + "/")
            for path in paths
        ):
            raise ValueError(f"补丁超出本轮允许范围：{operation.path}")
        if operation.op != "remove" and "value" not in item:
            raise ValueError(f"{operation.path}：add/replace 必须提供 value")
        records = draft.get(operation.path.lstrip("/"))
        if isinstance(records, list) and any(isinstance(row, dict) and row.get("id") for row in records):
            raise ValueError(
                f"{operation.path}：请修改具体实例或属性，不能替换或清空已有实体数组"
            )
        tokens = DesignRepository._tokens(operation.path)
        if len(tokens) == 3 and tokens[1].isdigit() and tokens[2] == "id":
            records = draft.get(tokens[0])
            if isinstance(records, list) and int(tokens[1]) < len(records):
                old = records[int(tokens[1])]
                if (isinstance(old, dict) and old.get("id")
                        and (operation.op != "replace" or operation.value != old["id"])):
                    raise ValueError(f"{operation.path}：修订须保留实例的稳定 ID")
        if (
            len(tokens) == 2
            and tokens[1].isdigit()
            and isinstance(candidate.get(tokens[0]), list)
        ):
            if int(tokens[1]) >= len(candidate[tokens[0]]):
                raise ValueError(f"路径不存在：{operation.path}")
            if operation.op == "remove" and tokens[0] == "walls":
                index = int(tokens[1])
                if index >= len(draft.get("walls", [])):
                    raise ValueError(f"{operation.path}：删除路径须指向原稿中的墙")
                if index in wall_removals:
                    raise ValueError(f"{operation.path}：不能重复删除同一面墙")
                wall_removals[index] = draft["walls"][index]["id"]
                continue
            if operation.op in {"add", "remove"}:
                raise ValueError(
                    f"{operation.path}：不能插入或删除整个实例来绕过字段错误"
                )
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
    # 先完成属性和引用修订，再按原稿下标倒序删除，避免多个删除导致路径错位。
    for index in sorted(wall_removals, reverse=True):
        candidate["walls"].pop(index)
    if wall_removals:
        from app.domain.design.coordinates import entity_reference_paths, wall_covers
        from app.domain.design.spatial import resolve_geometry

        references = entity_reference_paths(candidate, set(wall_removals.values()))
        if references:
            raise ValueError("删除墙须在同一补丁迁移引用，目标墙 "
                             + "、".join(wall_removals.values()) + "，仍有引用：" + "、".join(references))
        original_hosts = {host["id"]: host for host in resolve_geometry(draft)["hosts"]}
        retained_hosts = {host["id"]: host for host in resolve_geometry(candidate)["hosts"]}
        for index, identity in wall_removals.items():
            removed = original_hosts[identity]
            covered = False
            for retained_id, retained in retained_hosts.items():
                if (retained_id != identity and retained_id in original_hosts
                        and wall_covers(original_hosts[retained_id], removed)
                        and wall_covers(retained, removed)):
                    covered = True
                    break
            if not covered:
                raise ValueError(f"/walls/{index}：{identity} 未被保留墙完整覆盖，不能通过删除实体消除错误")
    return candidate


async def _request_draft(messages, *, thinking_mode, on_reasoning_delta):
    """仅在首轮明确开启思考时转发流式推理内容。"""
    use_thinking = thinking_mode
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
    return reply


def _build_repair_prompt(
    draft, repair_paths, validation_issue, issue, rules, *, rejected_patch=None
) -> str:
    """为允许修订的字段组装规则、当前值和具体校验错误。"""
    from app.domain.design.completeness import value_at

    reference = {}
    for key in ("massing", "coordinate_system", "levels", "profiles", "systems", "volumes", "walls", "facades", "floor_layouts"):
        if key in draft:
            reference[key] = draft[key]
    # 候选宿主是只读背景，不会因此扩大允许修改范围。
    from app.domain.design.coordinates import entity_reference_paths
    from app.domain.design.spatial import resolve_geometry

    wall_ids = set()
    walls = draft.get("walls")
    if isinstance(walls, list):
        for wall in walls:
            wall_id = wall.get("id") if isinstance(wall, dict) else None
            if isinstance(wall_id, str) and wall_id:
                wall_ids.add(wall_id)
    reference["wall_references"] = entity_reference_paths(draft, wall_ids)
    reference["hosted_components"] = {}
    components = draft.get("components")
    for index, component in enumerate(components if isinstance(components, list) else []):
        if not isinstance(component, dict):
            continue
        relation = component.get("relation")
        target = relation.get("target") if isinstance(relation, dict) else None
        if any(isinstance(ref, str) and ref in wall_ids for ref in (component.get("host"), target)):
            reference["hosted_components"][f"/components/{index}"] = component
    try:
        reference["resolved_hosts"] = resolve_geometry(draft)["hosts"]
    except (ValueError, TypeError, KeyError, AttributeError, RuntimeError):
        # 几何本身无效时仍提供原始字段，不能让上下文构造阻断定向修订。
        pass
    reference["repair_targets"] = {}
    if rejected_patch is not None:
        reference["rejected_patch"] = rejected_patch
    for path in repair_paths:
        exists, value = value_at(draft, path)
        reference["repair_targets"][path] = {"exists": exists, "value": value}
    missing_fields = [
        path for path, target in reference["repair_targets"].items()
        if path.count("/") == 1 and not target["exists"]
    ]
    if missing_fields:
        from pydantic import BaseModel

        from app.domain.design.contracts import ArchitectureDecisions

        for path in missing_fields:
            field = ArchitectureDecisions.model_fields.get(path[1:])
            model = field.annotation if field is not None else None
            if isinstance(model, type) and issubclass(model, BaseModel):
                reference["repair_targets"][path]["required_fields"] = [
                    name for name, definition in model.model_fields.items() if definition.is_required()
                ]
    return build_design_repair_prompt(
        repair_paths, validation_issue, issue, rules, reference
    )


def _validation_evidence(exc: Exception, design: dict):
    """从同一次校验的异常链提取阶段及具体问题，不另建一套宽松校验。"""
    from app.domain.design.completeness import value_at

    def stable_path(match):
        parts = match.group().removeprefix("/decisions").strip("/").split("/")
        current = design
        stable = []
        for part in parts:
            if isinstance(current, list) and part.isdigit() and int(part) < len(current):
                current = current[int(part)]
                identity = current.get("id") if isinstance(current, dict) else None
                stable.append(str(identity) if identity else part)
            elif isinstance(current, dict):
                current = current.get(part)
                stable.append(part)
            else:
                stable.append(part)
        return "/" + "/".join(stable)

    def fingerprint(problem):
        text = json.dumps(problem, ensure_ascii=False, sort_keys=True, default=str)
        return re.sub(r"/(?:[A-Za-z0-9_~.-]+/)*[A-Za-z0-9_~.-]+", stable_path, text)

    current = exc
    while current is not None:
        errors = getattr(current, "errors", None)
        if callable(errors):
            problems = []
            for error in errors():
                nested = getattr((error.get("ctx") or {}).get("error"), "conflicts", None)
                if nested:
                    problems.extend(nested)
                else:
                    path = "/" + "/".join(str(part) for part in error["loc"])
                    exists, value = value_at(design, path.removeprefix("/decisions"))
                    problems.append({"path": path, "type": error["type"], "message": error["msg"],
                                     "actual": value if exists else error.get("input")})
            return 0, frozenset(fingerprint(problem) for problem in problems)
        conflicts = getattr(current, "conflicts", None)
        if conflicts:
            problems = []
            for conflict in conflicts:
                # related_paths 是修订范围，删墙后的数组下标变化不等于问题已经消失。
                problems.append({key: value for key, value in conflict.items() if key != "related_paths"})
            return 1, frozenset(fingerprint(problem) for problem in problems)
        current = current.__cause__
    # 无结构证据时，仅完整通过的候选可被采用，不能靠错误文案长度或数量评分。
    return None


# base_prompt：基础系统提示词
# user_request：用户原始需求
# thinking_mode：是否允许首轮开启思考
# on_reasoning_delta：向外发送思考内容、进度的异步函数
# current_plan：可选的起始图纸
# only_blocks：可选的设计字段分组范围
# defects：调用方提供的待修问题
# max_attempts：最多尝试次数，默认 3
# call_accounting：与外层共享的调用计数字典
# allow_design_changes：控制后面的一项顶层字段检查
# validate：外层传入的校验函数
# load_repair_rules：外层传入的修订资料检索函数
# **_options：接收其他命名参数，其中 design_hash 用于追踪
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
    # 调用方传进来的上一轮设计图纸，有起始图纸，就深复制；没有就使用空字典
    context = deepcopy(current_plan or {})
    # 创建空集合，用来保存允许处理的顶层字段名。集合会自动去重。
    fields = set()
    # 遍历设计字段分组
    for block in ordered_blocks():
        if only_blocks is not None and block.name not in only_blocks:
            continue
        fields.update(block.fields)

    # 没有限定分组时，再加入逐层布局字段
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
    # expansions：参数表达式、重复项的展开记录
    # usage：累计模型用量
    rejected = []
    repairs = []
    expansions = []
    usage = None
    # draft：保存后续可以修订的图纸草稿
    # repair_paths：本轮允许修改的具体路径
    # rules：检索到的修订规则
    # validation_issue：保存图纸本身的校验错误
    draft = None
    repair_paths = []
    rules = ""
    validation_issue = ""
    draft_evidence = None

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

        # 设置追踪名称
        stage = (
            "architecture.generate" if attempt == 1 else "architecture.format_revision"
        )
        # 给首次生成和后续修订设置不同的追踪名称，方便查看 trace。
        with llm_trace_scope(stage=stage, design_hash=_options.get("design_hash")):
            reply = await _request_draft(
                messages,
                thinking_mode=thinking_mode and attempt == 1,
                on_reasoning_delta=on_reasoning_delta,
            )

        usage = merge_token_usage(usage, reply.token_usage)

        raw = None
        issue = ""
        try:
            if getattr(reply, "finish_reason", None) in {"length", "max_tokens"}:
                raise ValueError("模型输出达到长度上限，图纸或补丁未完整返回")
            raw = extract_json_object(
                reply.content or "", outer_only=True, raise_on_error=True
            )
        except ValueError as exc:
            issue = str(exc)

        # raw：模型本轮返回的对象，可能是完整设计，也可能是补丁
        # candidate：准备接受校验的候选图纸
        # picked：本轮成功后实际返回的数据
        # checked：是否已经进入候选图纸的校验阶段
        picked = raw or {}
        candidate = None
        checked = False
        adopted = False
        candidate_evidence = None

        if not issue:
            try:
                source = raw
                raw, expansion = expand_parameters(
                    raw, facts={"current_design": draft or context}
                )
                picked = raw
                if expansion:
                    expansions.append(
                        {"attempt": attempt, "source": source, **expansion}
                    )
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
            if validate is not None:
                try:
                    validate(candidate)
                except (ValueError, TypeError, KeyError, RuntimeError) as exc:
                    issue = str(exc)
                    candidate_evidence = _validation_evidence(exc, candidate)
            improved = False
            if draft_evidence is not None and candidate_evidence is not None:
                old_stage, old_problems = draft_evidence
                new_stage, new_problems = candidate_evidence
                # 校验阶段推进可揭示原先被字段错误挡住的问题；同阶段必须严格减少原问题且无新增。
                improved = new_stage > old_stage or (new_stage == old_stage and new_problems < old_problems)
            adopted = draft is None or not issue or improved
            if issue and adopted:
                volumes = candidate.get("volumes")
                has_named_volume = isinstance(volumes, list) and any(
                    isinstance(volume, dict) and volume.get("id") for volume in volumes
                )
                if has_named_volume or {"massing", "volumes"} <= candidate.keys():
                    draft = deepcopy(candidate)
                    draft_evidence = candidate_evidence
        if issue and unchanged:
            issue += "；上一轮未修改冲突数据，不能原样返回"
        if checked and issue and adopted:
            validation_issue = issue
        if repairs and repairs[-1]["attempt"] == attempt:
            repairs[-1]["validated"] = checked and not issue
            repairs[-1]["adopted"] = adopted
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
        if draft is not None and (checked or not repair_paths):
            repair_paths = _repair_paths(validation_issue or issue, draft, fields) or repair_paths
            if checked and not adopted and candidate is not None:
                # 新反馈可扩大关联修订范围，但失败候选的下标必须映射回保留稿的稳定 ID。
                related = _repair_paths(issue, candidate, fields, target_draft=draft)
                repair_paths = list(dict.fromkeys([*repair_paths, *related]))
        if repair_paths:
            if load_repair_rules and checked:
                rules = await load_repair_rules(validation_issue)
            prompt = _build_repair_prompt(
                draft, repair_paths, validation_issue, issue, rules,
                rejected_patch=raw if isinstance(raw, dict) and "operations" in raw else None,
            )
        else:
            prompt = (
                base
                + "\n本轮修复未完成或缺少关键字段的图纸，返回完整 JSON，保留已有设计。错误："
                + issue
                + "\n上一稿："
                + json.dumps(
                    (
                        draft
                        if draft is not None
                        else picked or {"unparsed_output": reply.content}
                    ),
                    ensure_ascii=False,
                )
            )
    return {}, diag
