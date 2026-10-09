"""Versioned design checks. A compiled scene is not evidence that intent is complete."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .contracts import DesignConstraint, DesignDocument, DesignGap

# These are existing writable design roots, not new geometry capabilities.
CHECK_ROOTS = {"massing", "volumes", "roof", "facades", "structural_grid",
               "circulation", "components", "component_quota", "required_components", "materials"}


def value_at(data: Any, path: str) -> tuple[bool, Any]:
    current = data
    for part in path.strip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return False, None
    return True, current


def merge_design_constraints(existing: list[DesignConstraint], raw: Any, request: str, revision_feedback: str = "") -> list[DesignConstraint]:
    """Never let model patches erase previously adopted intent or overwrite its target."""
    result = {c.id: c for c in existing}
    for entry in raw if isinstance(raw, list) else []:
        try:
            c = DesignConstraint.model_validate(entry)
        except (ValueError, TypeError):
            continue
        # Invalid provenance remains visible, but cannot drive automatic modifications.
        if c.kind == "user_hard" and (not c.source_quote or c.source_quote not in request and c.source_quote not in revision_feedback):
            c = c.model_copy(update={"source": "unknown", "check": "manual", "kind": "reference"})
        if c.id in result:
            continue
        if c.supersedes:
            prior = result.get(c.supersedes)
            explicit_revision = bool(revision_feedback and c.source_quote and c.source_quote in revision_feedback
                                     and c.kind == "user_hard" and prior and prior.target == c.target)
            if explicit_revision:
                result[c.supersedes] = prior.model_copy(update={"adoption": "superseded"})
                c = c.model_copy(update={"source": "user_revision", "adoption": "adopted"})
            else:
                c = c.model_copy(update={"adoption": "proposed"})
        if len(result) < 100:
            result[c.id] = c
    # A model's incidental raw value must not compete with an explicit user goal.
    hard = [c for c in result.values() if c.kind == "user_hard" and c.adoption == "adopted" and c.check != "manual"]
    for key, c in list(result.items()):
        if c.source == "architecture_draft" and c.kind == "preference" and c.adoption == "adopted":
            if any(c.target == h.target or c.target.startswith(h.target+"/") or h.target.startswith(c.target+"/") for h in hard):
                result[key] = c.model_copy(update={"adoption": "superseded"})
    return list(result.values())


def adopted_from_plan(raw: dict) -> list[dict]:
    """Capture existing structured choices BEFORE normalization, without inventing user intent."""
    choices = []
    for root in ("massing", "roof", "volumes", "facades", "components"):
        if root not in raw:
            continue
        value = raw[root]
        if root == "roof" and isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
            value = value[0]
        if value == [] or value == {}:
            continue
        fields = value.items() if isinstance(value, dict) else [(None, value)]
        for key, expected in fields:
            # Descriptions and unrelated style labels are not machine-verifiable promises.
            if root == "massing" and key not in {"width", "depth", "floors", "floor_height", "modeled_floors", "shape", "tiers"}:
                continue
            # P5-A：`volumes`（逐体量覆盖）同样是一条可核对的承诺，必须留下 ——
            # 不收的话归一化会把它当"无关字段"丢掉，用户要的屋型差异无声消失。
            if root == "roof" and key not in {"type", "ridge_axis", "overhang", "volumes"}:
                continue
            target = "/decisions/" + root + ("/"+key if key is not None else "")
            choices.append(dict(id="choice."+target.removeprefix("/decisions/").replace("/", "."),
                kind="preference", target=target, expression="保留已采用的结构化设计选择",
                source="architecture_draft", expected=deepcopy(expected), check="equals"))
    return choices


def value_matches(actual: Any, expected: Any) -> bool:
    """结构化取值比较（数值容差 0.001）。P2A 评价与 P4 履约共用同一份实现。"""
    # Additional schema defaults do not contradict an explicitly selected field.
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and value_matches(actual[k], v) for k,v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual)==len(expected) and all(value_matches(a,e) for a,e in zip(actual,expected))
    if isinstance(expected, (float, int)) and not isinstance(expected, bool):
        return isinstance(actual, (float, int)) and not isinstance(actual, bool) and abs(actual-expected)<=0.001
    return type(actual) is type(expected) and actual == expected


def path_schema(document: DesignDocument, path: str) -> dict | None:
    """Read capability from the actual Pydantic schema rather than a second field catalog."""
    schema = type(document.decisions).model_json_schema()
    node = schema
    tokens = path.strip("/").split("/")
    if not tokens or tokens[0] != "decisions":
        return None
    for token in tokens[1:]:
        while "$ref" in node:
            node = schema.get("$defs", {}).get(node["$ref"].rsplit("/",1)[-1], {})
        if "anyOf" in node:
            node = next((n for n in node["anyOf"] if n.get("type") != "null"), {})
            while "$ref" in node:
                node = schema.get("$defs", {}).get(node["$ref"].rsplit("/",1)[-1], {})
        if node.get("type") == "array" and token.isdigit():
            node = node.get("items", {})
        elif token in node.get("properties", {}):
            node = node["properties"][token]
        elif isinstance(node.get("additionalProperties"), dict):
            node = node["additionalProperties"]
        else:
            return None
    while "$ref" in node:
        node = schema.get("$defs", {}).get(node["$ref"].rsplit("/",1)[-1], {})
    return node


def evaluate_design(document: DesignDocument, design_hash: str) -> list[DesignGap]:
    data = document.model_dump(mode="json")
    gaps = []
    for c in document.constraints:
        if c.adoption == "superseded" or c.kind in {"engine_hard", "system_required"} or c.id == "request.source":
            continue
        exists, actual = value_at(data, c.target)
        root = c.target.strip("/").split("/")
        status = "open"
        reason = "当前设计与采用的决定不一致"
        if c.adoption == "proposed" or c.check == "manual":
            status, reason = "needs_review", "尚无可靠的自动判定方法，需要审核"
        elif len(root) < 2 or root[0] != "decisions" or root[1] not in CHECK_ROOTS:
            status, reason = "unsupported", "当前设计协议没有可写入的对应字段"
        elif path_schema(document, c.target) is None:
            status, reason = "unsupported", "目标字段不在当前设计契约中"
        elif c.check == "equals" and "enum" in (path_schema(document, c.target) or {}) and c.expected not in path_schema(document, c.target)["enum"]:
            status, reason = "unsupported", "目标值超出当前设计协议的枚举能力"
        elif c.check == "equals" and (path_schema(document, c.target) or {}).get("type") == "object" and not isinstance(c.expected, dict):
            status, reason = "unsupported", "目标表达与当前对象协议不兼容"
        elif c.check == "equals":
            same = value_matches(actual, c.expected)
            if exists and same:
                status = "satisfied"
        elif c.check == "contains":
            if isinstance(actual, list) and c.expected in actual:
                status = "satisfied"
            elif not isinstance(actual, list):
                status, reason = "needs_review", "contains 只对明确列表成员进行判定"
        elif c.check == "absent":
            if isinstance(actual, list):
                status = "satisfied" if c.expected not in actual else "open"
            elif not exists:
                status = "satisfied"
            else:
                status, reason = "needs_review", "缺少可验证的列表排除关系"
        elif c.check == "minimum":
            if isinstance(actual, (int, float)) and isinstance(c.expected, (int, float)) and not isinstance(actual, bool) and not isinstance(c.expected, bool):
                status = "satisfied" if actual >= c.expected else "open"
            else:
                status, reason = "needs_review", "minimum 必须比较明确数值"
        if status == "satisfied":
            reason = "当前设计字段满足决定；最终实体仍需交付验收"
        gaps.append(DesignGap(id="gap."+c.id, constraint_id=c.id, status=status,
            design_hash=design_hash, target=c.target, expected=c.expected, actual=actual,
            evidence=f"{c.expression}：{reason}（{c.target}）"))
    if not any(c.source in {"architecture_draft", "user_request", "user_revision"} and c.id != "request.source" for c in document.constraints):
        gaps.append(DesignGap(id="gap.intent.unknown", constraint_id="request.source", status="needs_review",
            design_hash=design_hash, target="/requirements/source_request", expected=document.requirements.source_request,
            evidence="历史文档或起草结果未提供可执行意图，不能证明全部需求已经满足"))
    for trace in document.rule_trace:
        for index, change in enumerate(trace.changes):
            if not change.get("semantic_change"):
                continue
            target = change["path"]
            exists, actual = value_at(data, target)
            # Evidence is historical. A later explicit design revision can replace the
            # degraded value; do not keep reporting the old revision as a current defect.
            still_degraded = exists == change.get("after_exists", True) and value_matches(actual, change.get("after"))
            supported = path_schema(document, target) is not None
            gaps.append(DesignGap(
                id=f"gap.normalization.{trace.rule_id}.{trace.design_revision}.{index}",
                constraint_id=next(iter(change.get("constraint_ids") or []), "request.source"),
                status=("open" if supported and change.get("category") != "derived" else "needs_review") if still_degraded else "satisfied",
                design_hash=design_hash, target=target, expected=change.get("before"), actual=actual,
                evidence=f"{target}：{change['reason']}；原值 {change.get('before')!r}，降级值 {change.get('after')!r}。修订须遵守当前契约，不能恢复非法值。",
            ))
    return gaps
