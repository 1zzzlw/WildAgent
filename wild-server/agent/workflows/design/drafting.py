"""完整图纸起草与字段级修订；不检查引擎能否实现设计。"""

from copy import deepcopy
from functools import partial
import json
import re

from agent.prompts.design_revision import build_design_repair_prompt
from agent.runtime import create_llm
from agent.state import GenerationState
from agent.tools.design_validation import validate_design_draft
from agent.llm.invocation import invoke_llm
from agent.llm.invocation import stream_llm
from agent.llm.invocation import merge_token_usage
from agent.utils.observability.trace import llm_trace_scope
from agent.utils.blueprint.json_extractor import extract_json_object
from agent.utils.design.contracts import DesignDocument, ResolvedDesign
from agent.utils.design.parametric import expand_parameters

_MAX_ATTEMPTS = 3
_REPAIR_FIELDS = frozenset(
    {
        "concept",
        "design_intent",
        "design_constraints",
        "design_rationale",
        "massing",
        "coordinate_system",
        "levels",
        "profiles",
        "volumes",
        "structural_grid",
        "systems",
        "slabs",
        "voids",
        "floor_layouts",
        "circulation",
        "walls",
        "facades",
        "curtain_wall",
        "roofs",
        "roof",
        "components",
        "relations",
        "materials",
        "detail_packages",
    }
)


def _repair_paths(issue, draft, fields, *, target_draft=None):
    from agent.utils.design.coordinates import entity_reference_paths

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
            if (
                index < len(walls)
                and isinstance(walls[index], dict)
                and walls[index].get("id")
            ):
                wall_ids.add(walls[index]["id"])
    for path in entity_reference_paths(draft, wall_ids):
        parts = path.strip("/").split("/")
        if parts[0] in fields:
            paths.append("/" + "/".join(parts[:2]))
    if (
        "walls" in fields
        and isinstance(draft.get("walls"), list)
        and any(path.startswith("/components") for path in paths)
        and ("宿主" in issue or "/host" in issue)
    ):
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
            if (
                len(parts) == 2
                and parts[1].isdigit()
                and isinstance(source, list)
                and isinstance(target, list)
                and int(parts[1]) < len(source)
            ):
                record = source[int(parts[1])]
                if isinstance(record, dict) and record.get("id"):
                    parts[1] = "-"
                    for index, existing in enumerate(target):
                        if (
                            isinstance(existing, dict)
                            and existing.get("id") == record["id"]
                        ):
                            parts[1] = str(index)
                            break
                    path = "/" + "/".join(parts)
            mapped.append(path)
        paths = mapped
    return list(dict.fromkeys(paths))


def _apply_repair(draft, raw, paths):
    from agent.utils.design.contracts import DesignPatchOperation
    from agent.utils.design.patch import apply_operation, pointer_tokens

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
        if isinstance(records, list) and any(
            isinstance(row, dict) and row.get("id") for row in records
        ):
            raise ValueError(
                f"{operation.path}：请修改具体实例或属性，不能替换或清空已有实体数组"
            )
        tokens = pointer_tokens(operation.path)
        if len(tokens) == 3 and tokens[1].isdigit() and tokens[2] == "id":
            records = draft.get(tokens[0])
            if isinstance(records, list) and int(tokens[1]) < len(records):
                old = records[int(tokens[1])]
                if (
                    isinstance(old, dict)
                    and old.get("id")
                    and (operation.op != "replace" or operation.value != old["id"])
                ):
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
        apply_operation(
            candidate, operation.op, operation.path, deepcopy(operation.value)
        )
    # 先完成属性和引用修订，再按原稿下标倒序删除，避免多个删除导致路径错位。
    for index in sorted(wall_removals, reverse=True):
        candidate["walls"].pop(index)
    if wall_removals:
        from agent.utils.design.coordinates import entity_reference_paths, wall_covers
        from agent.utils.design.spatial import resolve_geometry

        references = entity_reference_paths(candidate, set(wall_removals.values()))
        if references:
            raise ValueError(
                "删除墙须在同一补丁迁移引用，目标墙 "
                + "、".join(wall_removals.values())
                + "，仍有引用："
                + "、".join(references)
            )
        original_hosts = {host["id"]: host for host in resolve_geometry(draft)["hosts"]}
        retained_hosts = {
            host["id"]: host for host in resolve_geometry(candidate)["hosts"]
        }
        for index, identity in wall_removals.items():
            removed = original_hosts[identity]
            covered = False
            for retained_id, retained in retained_hosts.items():
                if (
                    retained_id != identity
                    and retained_id in original_hosts
                    and wall_covers(original_hosts[retained_id], removed)
                    and wall_covers(retained, removed)
                ):
                    covered = True
                    break
            if not covered:
                raise ValueError(
                    f"/walls/{index}：{identity} 未被保留墙完整覆盖，不能通过删除实体消除错误"
                )
    return candidate


async def _request_draft(messages, *, thinking_mode, on_reasoning_delta, tools=()):
    """仅在首轮明确开启思考时转发流式推理内容。"""
    streaming = thinking_mode and on_reasoning_delta is not None
    model = create_llm(enable_thinking=thinking_mode, streaming=streaming)
    if tools:
        model = model.bind_tools(tools)
    if streaming:

        async def emit(delta):
            await on_reasoning_delta("architecture", delta)

        return await stream_llm(
            model,
            messages,
            on_reasoning_delta=emit,
            keep_message=bool(tools),
        )
    return await invoke_llm(model, messages)


def _build_repair_prompt(
    draft, repair_paths, validation_issue, issue, *, rejected_patch=None
) -> str:
    """为允许修订的字段组装规则、当前值和具体校验错误。"""
    from agent.utils.design.completeness import value_at

    reference = {}
    for key in (
        "massing",
        "coordinate_system",
        "levels",
        "profiles",
        "systems",
        "volumes",
        "walls",
        "facades",
        "floor_layouts",
    ):
        if key in draft:
            reference[key] = draft[key]
    # 候选宿主是只读背景，不会因此扩大允许修改范围。
    from agent.utils.design.coordinates import entity_reference_paths
    from agent.utils.design.spatial import resolve_geometry

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
    for index, component in enumerate(
        components if isinstance(components, list) else []
    ):
        if not isinstance(component, dict):
            continue
        relation = component.get("relation")
        target = relation.get("target") if isinstance(relation, dict) else None
        if any(
            isinstance(ref, str) and ref in wall_ids
            for ref in (component.get("host"), target)
        ):
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
        path
        for path, target in reference["repair_targets"].items()
        if path.count("/") == 1 and not target["exists"]
    ]
    if missing_fields:
        from pydantic import BaseModel

        from agent.utils.design.contracts import ArchitectureDecisions

        for path in missing_fields:
            field = ArchitectureDecisions.model_fields.get(path[1:])
            model = field.annotation if field is not None else None
            if isinstance(model, type) and issubclass(model, BaseModel):
                reference["repair_targets"][path]["required_fields"] = [
                    name
                    for name, definition in model.model_fields.items()
                    if definition.is_required()
                ]
    return build_design_repair_prompt(repair_paths, validation_issue, issue, reference)


def _validation_evidence(exc: Exception, design: dict):
    """从同一次校验的异常链提取阶段及具体问题，不另建一套宽松校验。"""
    from agent.utils.design.completeness import value_at

    def stable_path(match):
        parts = match.group().removeprefix("/decisions").strip("/").split("/")
        current = design
        stable = []
        for part in parts:
            if (
                isinstance(current, list)
                and part.isdigit()
                and int(part) < len(current)
            ):
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
                nested = getattr(
                    (error.get("ctx") or {}).get("error"), "conflicts", None
                )
                if nested:
                    problems.extend(nested)
                else:
                    path = "/" + "/".join(str(part) for part in error["loc"])
                    exists, value = value_at(design, path.removeprefix("/decisions"))
                    problems.append(
                        {
                            "path": path,
                            "type": error["type"],
                            "message": error["msg"],
                            "actual": value if exists else error.get("input"),
                        }
                    )
            return 0, frozenset(fingerprint(problem) for problem in problems)
        conflicts = getattr(current, "conflicts", None)
        if conflicts:
            problems = []
            for conflict in conflicts:
                # related_paths 是修订范围，删墙后的数组下标变化不等于问题已经消失。
                problems.append(
                    {
                        key: value
                        for key, value in conflict.items()
                        if key != "related_paths"
                    }
                )
            return 1, frozenset(fingerprint(problem) for problem in problems)
        current = current.__cause__
    # 无结构证据时，仅完整通过的候选可被采用，不能靠错误文案长度或数量评分。
    return None


async def draft_design(
    *,
    state: GenerationState,
    base_prompt,
    profile_id: str,
    object_scene: bool,
    call_accounting: dict[str, int],
    thinking_mode=False,
    on_reasoning_delta=None,
    request_draft=None,
) -> tuple[DesignDocument, ResolvedDesign, dict] | tuple[None, None, dict]:
    """起草并校验图纸，返回正式文档、解析结果和诊断。"""
    user_request = state["user_message"]
    prompt = base_prompt

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
    # validation_issue：保存图纸本身的校验错误
    # draft_evidence：保存上轮校验的阶段和问题数量，用于判断本轮是否有改进
    draft = None
    repair_paths = []
    validation_issue = ""
    draft_evidence = None

    initial_calls = call_accounting["model_calls"]

    request_draft = request_draft or partial(
        _request_draft, on_reasoning_delta=on_reasoning_delta
    )

    # 开始最多三次尝试
    # 对应首次生成，加上最多两次修订。第一次成功就立即返回，不会继续调用。
    for attempt in range(1, _MAX_ATTEMPTS + 1):

        # 任务描述：首次生成时使用用户原始需求；修订时使用系统提示和原始需求，要求只修订错误字段。
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

        call_accounting["model_calls"] += 1

        # 设置追踪名称
        stage = (
            "architecture.generate" if attempt == 1 else "architecture.format_revision"
        )

        # 给首次生成和后续修订设置不同的追踪名称，方便查看 trace。
        with llm_trace_scope(stage=stage):
            reply = await request_draft(
                messages,
                # 只有第一次才开思考模式，重试关掉，节省 token
                thinking_mode=thinking_mode and attempt == 1,
            )

        usage = merge_token_usage(usage, reply.token_usage)

        raw = None
        issue = ""
        try:
            # getattr()：动态获取对象的属性 / 方法
            # obj：目标对象
            # name：属性名字符串
            # default（可选）：找不到属性时返回这个；不填找不到直接抛 AttributeError
            # finish_reason：模型输出结束的原因，可能是 "stop"、"length"、"max_tokens" 等
            if getattr(reply, "finish_reason", None) in {"length", "max_tokens"}:
                raise ValueError("模型输出达到长度上限，图纸或补丁未完整返回")
            # 把模型回复里的 JSON 文本解析成 Python 字典 raw
            raw = extract_json_object(
                reply.content or "", outer_only=True, raise_on_error=True
            )
        except ValueError as exc:
            issue = str(exc)

        # raw：模型本轮返回的对象，可能是完整设计，也可能是补丁
        # picked：解析失败或修订失败时供反馈使用的本轮数据
        # candidate：准备接受校验的候选图纸
        # checked：是否已经进入候选图纸的校验阶段
        # adopted：候选图纸是否被采纳为后续修订的基础
        # candidate_evidence：候选图纸的校验阶段和问题数量，用于判断是否有改进
        picked = raw or {}
        candidate = None
        checked = False
        adopted = False
        candidate_evidence = None

        if not issue:
            try:
                source = raw
                # 把模型返回里的简写、表达式、重复项展开成标准图纸结构。
                raw, expansion = expand_parameters(
                    raw, facts={"current_design": draft or {}}
                )
                picked = raw
                if expansion:
                    expansions.append(
                        {"attempt": attempt, "source": source, **expansion}
                    )
                if repair_paths:
                    candidate = _apply_repair(draft, raw, repair_paths)
                    picked = candidate
                    repairs.append(
                        {"attempt": attempt, "operations": deepcopy(raw["operations"])}
                    )
                else:
                    candidate = raw.copy()
            except (ValueError, TypeError, KeyError) as exc:
                issue = str(exc)

        unchanged = bool(repair_paths and candidate == draft)

        # 如果没有错误进入校验阶段
        if not issue:
            checked = True
            try:
                document, resolved = validate_design_draft(
                    candidate,
                    state,
                    profile_id=profile_id,
                    object_scene=object_scene,
                )
            except (ValueError, TypeError, KeyError, RuntimeError) as exc:
                issue = str(exc)
                candidate_evidence = _validation_evidence(exc, candidate)
            improved = False
            if draft_evidence is not None and candidate_evidence is not None:
                old_stage, old_problems = draft_evidence
                new_stage, new_problems = candidate_evidence
                # 校验阶段推进可揭示原先被字段错误挡住的问题；同阶段必须严格减少原问题且无新增。
                improved = new_stage > old_stage or (
                    new_stage == old_stage and new_problems < old_problems
                )
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
            "model_calls": call_accounting["model_calls"] - initial_calls,
            "attempts": attempt,
            "token_usage": usage,
            "last_issue": issue,
            "rejected_attempts": rejected,
            "repairs": repairs,
            "parameter_expansions": expansions,
            "call_id": getattr(reply, "call_id", None),
        }
        if not issue:
            diag["raw_plan"] = candidate
            return document, resolved, diag
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
                f"图纸需要修订（{attempt}/{_MAX_ATTEMPTS}）：{issue}。\n",
            )
        if attempt == _MAX_ATTEMPTS:
            break
        if draft is not None and (checked or not repair_paths):
            repair_paths = (
                _repair_paths(validation_issue or issue, draft, _REPAIR_FIELDS)
                or repair_paths
            )
            if checked and not adopted and candidate is not None:
                # 新反馈可扩大关联修订范围，但失败候选的下标必须映射回保留稿的稳定 ID。
                related = _repair_paths(
                    issue, candidate, _REPAIR_FIELDS, target_draft=draft
                )
                repair_paths = list(dict.fromkeys([*repair_paths, *related]))
        if repair_paths:
            prompt = _build_repair_prompt(
                draft,
                repair_paths,
                validation_issue,
                issue,
                rejected_patch=(
                    raw if isinstance(raw, dict) and "operations" in raw else None
                ),
            )
        else:
            prompt = (
                base_prompt
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
    diag["raw_plan"] = {}
    return None, None, diag
