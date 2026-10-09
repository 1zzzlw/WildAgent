"""P7-C：有界视觉修订 —— 发现 → 建议 → 候选 → 校验 → 采纳/回退。

P7-C 的五条要求与本模块的对应关系：

1. **有界**（"首版最多自动尝试 2 轮，使用明确调用/时间预算"）
   :data:`_MAX_ROUNDS` + :data:`_CALL_BUDGET` + 无进展上限，三重照抄
   ``convergence.py`` 的既有做法，不发明新口径。
2. **走既有受控变更接口，不绕过编译器**
   修订只经``draft_design_blocks(only_blocks=…)``，产出仍然要过
   ``normalize_architecture_plan`` → ``compile_document``。
   🔴 本模块**不接触 three.js、不改渲染代码、不直接改蓝图**。
3. **能力缺失只标记不阻断**：视觉评价不通过**绝不**让生成失败。
   ``stop_reason`` 会如实记账，但 ``final_blueprint`` 恒为可用产物。
4. **每次候选必须重跑共享解析 + 几何校验 + 履约验收**
   :func:`candidate_verdict` 里三条一起跑，缺一条就不许采纳。
5. **变差就回退 + 旧证据保留可追踪引用**
   :class:`RevisionLedger` 逐版留档（哈希、截图、指标、结论），
   :func:`pick_best` 按**同一套判据**选最优版本，而不是"最后一版"。

🔴 **不做的事**（P7-B 的诚实边界在本模块继续生效）：
    - ``missing`` 的评价项**不进修订队列** —— 数据不足不是设计问题，
      拿它去改设计是在修一个不存在的问题；
    - ``confidence == "low"`` 的意见**只记录不自动改**（P7 第 4 条）；
    - 找不到设计字段映射的意见**只记录**，不猜（P7 第 4 条 + ``convergence`` 红线 3）。
"""

from __future__ import annotations

import asyncio
import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from loguru import logger

from app.design.contracts import DesignDocument
from app.agent.vision.evaluation import (
    CONFIDENCE_LEVELS,
    VISIBLE_CRITERIA,
    proxy_evaluate,
)

#: 思考流回调：``(通道名, 文本) -> await``。与 ``design_workflow`` 同一口径。
ReasoningEmitter = Callable[[str, str], Awaitable[None]]

#: 块级起草函数。抽出成别名是为了测试能注入桩件，不必真调模型。
DraftBlocks = Callable[..., Awaitable[tuple[dict[str, Any], dict[str, Any]]]]

#: 修订轮数上限。P7-C 第 1 条"首版最多自动尝试 2 轮"。
_MAX_ROUNDS = 2

#: 模型调用预算（按块计，一次调用出一个块）。
_CALL_BUDGET = 4

#: 连续这么多轮"可见问题数没下降"就停。取 2：改完这处那处又坏是正常波动。
_MAX_NO_PROGRESS = 2

#: 自动修订的**最低置信度**门限。低于它的意见只进 ledger，不驱动修订。
#: 🔴 这是"只标记不阻断"在视觉侧的具体落点：宁可少改，不可乱改。
_AUTO_CONFIDENCE = ("high", "medium")

#: 停止原因闭集。诊断、报告与测试都按这张表判，不要用自由文本。
STOP_REASONS = (
    "time_budget",
    "review_required",
    "render_error",
    "no_issues",          # 没有够格驱动修订的问题
    "satisfied",          # 修完了
    "max_rounds",         # 轮数用尽
    "no_progress",        # 连续无进展
    "model_budget",       # 调用预算用尽
    "model_error",        # 模型故障
    "invalid_candidate",  # 候选没过校验/履约，且无可回退的历史更优版本
    "approval_required",  # 涉及设计语义变化，按 P7-C 第 3 条要人工确认
)

_REVISION_PROMPT = """你正在按**可见效果**修订一份已经定稿的建筑设计图纸。

上一版被程序化视觉检查指出了具体问题。证据里写清了"哪个评价项不达标、证据是什么、
该改图纸的哪一项"。你的任务是**只重出受影响的块**，把可见问题消掉。

四条要求：
- 只改证据指到的字段，其余保持原样；
- **不许牺牲用户硬要求来让指标好看** —— 几何有效性与履约验收的权重高于视觉指标，
  任何让校验变差或让已满足要求变得不满足的改动都会被直接拒绝；
- 不要发明新的体量、新的立面或新的构件类型——那会制造新的问题；
- 改完之后，同一批字段仍必须满足块契约（会有检查，不过会带证据让你重出）。
"""


# ── 评价项 → 设计字段 的映射 ─────────────────────────────────────────
#
# 🔴 P7 第 4 条："找不到字段映射的意见只记录，不自动猜测并修改"。
#    所以这张表是**闭集**：映射不到的 criterion 一律只记录。
#    值是 `block_of_design_field` 认识的 design_field 前缀 —— 与
#    `app/agent/generation/architecture/design_blocks.py` 同口径，不另立一套。

_VISION_FIELD_MAP: dict[str, str] = {
    "massing_hierarchy": "decisions.volumes",
    "facade_rhythm": "decisions.facades",
    "entrance_legibility": "decisions.facades",
    "material_harmony": "decisions.materials",
}


def vision_design_field(criterion: str) -> str:
    """评价项对应的设计字段。映射不到就返回空串 —— 调用方据此只记录。"""

    return _VISION_FIELD_MAP.get(criterion, "")


def build_vision_evidence(evaluation: dict[str, Any]) -> list[dict[str, Any]]:
    """从 proxy 评价里挑出**够格驱动修订**的问题。

    四道闸（任一不过就只记录，不进队列）：

    1. ``status == "needs_review"`` —— ``missing`` 是数据不足，不是设计问题；
    2. ``criterion`` 在 :data:`VISIBLE_CRITERIA` 闭集里；
    3. ``confidence`` 达到 :data:`_AUTO_CONFIDENCE`；
    4. 有 ``design_field`` 映射且带可复核的 ``evidence``。

    返回项形如 ``{"id": "vision:<criterion>", "layer": "design",
    "target": <design_field>, "evidence": {...}}`` —— 与 ``completion.py``
    里 compile 缺陷的证据形状一致，同一套下游能吃。
    """

    if evaluation.get("source") not in {"human", "vision"} or not evaluation.get("complete"):
        return []
    picked: list[dict[str, Any]] = []
    for item in evaluation.get("items") or []:
        criterion = str(item.get("criterion") or "")
        if criterion not in VISIBLE_CRITERIA:
            continue
        if item.get("status") != "needs_review":
            continue
        confidence = str(item.get("confidence") or "")
        if confidence not in _AUTO_CONFIDENCE:
            continue
        evidence = item.get("evidence")
        if not isinstance(evidence, dict) or not evidence:
            continue
        target = vision_design_field(criterion)
        if not target or target not in evidence.get("relatedFields", []):
            continue
        picked.append({
            "id": f"vision:{criterion}",
            "layer": "design",
            "category": "visibility",
            "target": target,
            "criterion": criterion,
            "confidence": confidence,
            "evidence": evidence,
            "detail": str(item.get("detail") or ""),
        })
    return picked


def recorded_only(evaluation: dict[str, Any]) -> list[dict[str, Any]]:
    """只记录、不驱动修订的意见。

    P7 第 4 条要求"输出问题、视角证据、关联设计字段、置信度和建议"，
    所以这些意见**必须出现在报告里**，只是不许触发改稿。
    """

    out: list[dict[str, Any]] = []
    for item in evaluation.get("items") or []:
        criterion = str(item.get("criterion") or "")
        status = str(item.get("status") or "")
        confidence = str(item.get("confidence") or "")
        reasons: list[str] = []
        if status == "missing":
            reasons.append("数据不足，不是设计问题")
        if confidence not in _AUTO_CONFIDENCE:
            reasons.append(f"置信度 {confidence or '未标'} 低于自动修订门槛")
        if criterion not in VISIBLE_CRITERIA:
            # 🔴 闭集外的评价项**也要出现在报告里**，否则意见凭空消失。
            #    评价器闭集（VISIBLE_CRITERIA）与修订映射闭集（_VISION_FIELD_MAP）
            #    是两件事：前者限定"评什么"，后者限定"改什么"。
            reasons.append(f"评价项 {criterion or '(未命名)'} 不在可见问题闭集内")
        elif not vision_design_field(criterion):
            reasons.append("找不到设计字段映射")
        if not reasons:
            continue
        out.append({
            "criterion": criterion,
            "status": status,
            "confidence": confidence,
            "detail": str(item.get("detail") or ""),
            "recordOnlyReasons": reasons,
            "evidence": item.get("evidence") if isinstance(item.get("evidence"), dict) else {},
        })
    return out


def visible_issue_count(evaluation: dict[str, Any]) -> int:
    """未解决项数量；missing 不能通过删除可测实体伪装成进步。"""

    return sum(1 for item in evaluation.get("items") or []
               if item.get("status") in {"needs_review", "missing"})


# ── 候选校验：三条一起跑，缺一条不许采纳 ──────────────────────────────

@dataclass
class CandidateVerdict:
    """一个候选版本的校验结论。"""

    accepted: bool
    reason: str
    compile_errors: int = 0
    pipeline_errors: int = 0
    fulfillment_open: int = 0
    issues: int = 0
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "reason": self.reason,
            "compileErrors": self.compile_errors,
            "pipelineErrors": self.pipeline_errors,
            "fulfillmentOpen": self.fulfillment_open,
            "visibleIssues": self.issues,
            "detail": self.detail,
        }


def candidate_verdict(
    *,
    result: Any,
    fulfillment: Any,
    pipeline_errors: int = 0,
    evaluation: dict[str, Any] | None = None,
    baseline_issues: int | None = None,
    baseline_fulfillment: dict[str, str] | None = None,
) -> CandidateVerdict:
    """判定一个候选能不能采纳。

    🔴 P7-C 第 4 条："不能靠牺牲用户硬要求让画面看起来更好"。

    因此采纳门槛是**合取**，视觉指标只是其中一项：

    - 编译零error（``result.defects`` 里 severity==error）；
    - 几何校验流水线零 error（``pipeline_errors``）；
    - 按要求 ID 核对：原先满足项不能退化，不能新增 open/unsupported；
    - 可见问题数不高于基准（``issues <= baseline_issues``）—— 允许持平，
      但**不许变差**。持平也算接受，因为一轮修订常常只解决一项。

    任一不满足 ⇒ 不采纳，调用方回退到基准版本。
    """

    compile_errors = sum(
        1 for d in getattr(result, "defects", []) if getattr(d, "severity", "") == "error"
    )
    gaps = list(getattr(fulfillment, "design_gaps", []) or [])
    open_now = sum(1 for g in gaps if getattr(g, "status", "") in {"open", "unsupported"})
    issues = visible_issue_count(evaluation or {})

    if compile_errors:
        return CandidateVerdict(
            False, "编译出现 error 缺陷", compile_errors, pipeline_errors,
            open_now, issues, {"defects": [d.to_dict() for d in result.defects
                                           if getattr(d, "severity", "") == "error"][:5]},
        )
    if pipeline_errors:
        return CandidateVerdict(
            False, "几何校验流水线报 error", compile_errors, pipeline_errors, open_now, issues)
    if not evaluation or not evaluation.get("complete") or evaluation.get("source") not in {"human", "vision"}:
        return CandidateVerdict(False, "候选尚未完成真实截图评价", compile_errors, pipeline_errors, open_now, issues)
    current_gaps = {g.id: g.status for g in gaps}
    new_failures = {key for key, status in current_gaps.items() if status in {"open", "unsupported"}} - {
        key for key, status in (baseline_fulfillment or {}).items() if status in {"open", "unsupported"}
    }
    if baseline_fulfillment is None or new_failures or any(
        status == "satisfied" and current_gaps.get(key) != "satisfied"
        for key, status in (baseline_fulfillment or {}).items()
    ):
        return CandidateVerdict(
            False, "履约缺口变多（牺牲了已满足的要求）",
            compile_errors, pipeline_errors, open_now, issues)
    if baseline_issues is not None and issues > baseline_issues:
        return CandidateVerdict(
            False, "可见问题数变多", compile_errors, pipeline_errors, open_now, issues)
    reason = "采纳" if (baseline_issues is None or issues < baseline_issues) else "持平采纳"
    return CandidateVerdict(
        True, reason, compile_errors, pipeline_errors, open_now, issues)


# ── 版本留档与回退 ────────────────────────────────────────────────────

@dataclass
class RevisionLedger:
    """逐版留档。P7-C 第 5 条："旧 Blueprint、截图和验收结果保留可追踪引用，不覆盖唯一证据"。

    🔴 每一条都带 ``design_hash``：截图与蓝图对应到具体设计版本，
       否则"这张图是哪一版渲的"永远说不清。
    """

    entries: list[dict[str, Any]] = field(default_factory=list)

    def record(self, *, label: str, design_hash: str, blueprint: dict[str, Any] | None,
               evaluation: dict[str, Any] | None, verdict: CandidateVerdict | None,
               screenshot: str | None = None, manifest: str | None = None,
               document: dict[str, Any] | None = None) -> None:
        self.entries.append({
            "label": label,
            "designHash": design_hash,
            "issues": visible_issue_count(evaluation or {}),
            "blueprintRef": _blueprint_ref(blueprint),
            "blueprint": deepcopy(blueprint),
            "evaluation": evaluation,
            "verdict": verdict.to_dict() if verdict else None,
            "screenshot": screenshot,
            "manifest": manifest,
            # 🔴 文档本体必须留：回退要靠它。蓝图**不能**反解回设计文档
            #    （编译器是单向过程），所以这一份是唯一的回退依据。
            "document": document,
        })

    def of(self, label: str) -> dict[str, Any] | None:
        for entry in self.entries:
            if entry["label"] == label:
                return entry
        return None

    def versions(self) -> list[dict[str, Any]]:
        return list(self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {"entries": self.entries, "count": len(self.entries)}


def _blueprint_ref(blueprint: dict[str, Any] | None) -> dict[str, Any]:
    """蓝图的**引用**而不是全文。

    🔴 一个 session 可能留十几版蓝图，全量塞进诊断会让 state 爆掉；
       但只留哈希又会"证据不可追"。折中：留可定位的坐标 + 实体计数 + 内容哈希。
    """

    if not isinstance(blueprint, dict):
        return {"present": False}
    geometry = blueprint.get("geometry") or {}
    elements = geometry.get("elements") or []
    components = geometry.get("components") or []
    xs: list[float] = []
    for item in (*elements, *components):
        for key in ("from", "to", "position"):
            point = item.get(key) if isinstance(item, dict) else None
            if isinstance(point, list) and len(point) >= 3:
                try:
                    xs.append(float(point[0]))
                except (TypeError, ValueError):
                    continue
    return {
        "present": True,
        "elements": len(elements),
        "components": len(components),
        "xRange": [min(xs), max(xs)] if xs else None,
        "digest": _digest(blueprint),
    }


def _digest(payload: Any) -> str:
    import hashlib
    import json

    try:
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        blob = repr(payload)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def pick_best(
    candidates: list[tuple[str, dict[str, Any], dict[str, Any] | None]],
) -> str:
    """从候选里挑最优版本的标签。

    🔴 **不能返回"最后一个"** —— 最后一轮可能是变差的那版。
       排序键（依次比）：可见问题数少 → 履约缺口少 → 编译 error 少。
       平手时取**较早**出现的版本：先到先得，避免无谓地采纳更复杂的图纸。

    ``candidates`` 是 ``(label, blueprint, evaluation)`` 三元组。
    """

    if not candidates:
        return ""
    best_label = candidates[0][0]
    best_key: tuple[int, int, int, int] | None = None
    for index, (label, _blueprint, evaluation) in enumerate(candidates):
        evaluation = evaluation or {}
        issues = visible_issue_count(evaluation)
        gaps = evaluation.get("fulfillmentOpen")
        gaps = gaps if isinstance(gaps, int) else 0
        compile_errors = evaluation.get("compileErrors")
        compile_errors = compile_errors if isinstance(compile_errors, int) else 0
        if index and (evaluation.get("accepted") is not True or compile_errors or evaluation.get("pipelineErrors")):
            continue
        key = (issues, gaps, compile_errors, index)
        if best_key is None or key < best_key:
            best_key, best_label = key, label
    return best_label


@dataclass
class RevisionOutcome:
    """有界修订的最终产物。

    🔴 ``document`` / ``blueprint`` **恒为可用产物** —— 哪怕一处没改进。
       视觉评价不通过绝不让生成失败（用户红线：能力缺失只标记不阻断）。
       失败信息全在 ``diag`` 里如实记账。
    """

    document: dict[str, Any]
    blueprint: dict[str, Any] | None
    changed: bool
    diag: dict[str, Any] = field(default_factory=dict)
    ledger: RevisionLedger = field(default_factory=RevisionLedger)


async def revise_by_visibility(
    *,
    document: dict[str, Any],
    user_message: str,
    complexity_profile: dict[str, Any] | None = None,
    architecture_profile: dict[str, Any] | None = None,
    thinking_mode: bool = False,
    max_rounds: int = _MAX_ROUNDS,
    call_budget: int = _CALL_BUDGET,
    max_no_progress: int = _MAX_NO_PROGRESS,
    render: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    review: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None,
    time_budget: float = 120.0,
    validate: Callable[[dict[str, Any]], int] | None = None,
    on_reasoning_delta: ReasoningEmitter | None = None,
    draft_blocks: DraftBlocks | None = None,
    now: Callable[[], float] = time.monotonic,
) -> RevisionOutcome:
    """按可见问题做**有界**修订。

    流程（每轮）::

        当前文档 → compile → blueprint → 渲染 → 绑定截图的人工/视觉评价
                 → 够格的问题 → 映射到块 → 只重出这些块
                 → normalize → compile → 校验 → 履约 → 三条合取判据
                 → 采纳（记账留档）或 回退（保留上一版）

    :param render: ``blueprint -> render_manifest``。**不给就不做视觉评价**，
        也就没有"可见问题"可言 —— 此时如实返回 ``review_required`` 停止原因，
        绝不拿几何数据假装看过图。
    :param validate: ``blueprint -> error 数``，接``run_validation_pipeline``。
        不给则不启动修订，返回 review_required。
    :param now: 注入式时钟，供测试钉住耗时口径。
    """

    from app.design.compilation import compile_document, project_compilation
    from app.design.resolver import (
        architecture_plan_from_document,
    )
    from app.agent.generation.architecture import (
        detect_architecture_profile,
    )
    from app.agent.generation.architecture.design_blocks import (
        block_of_design_field,
        ordered_blocks,
    )
    from app.agent.generation.architecture.design_workflow import draft_design_blocks
    from app.agent.generation.architecture.revision_patch import apply_design_patch

    # 🔴 profile 必须**确定性重算**，不能默认 None ——
    #    `normalize_architecture_plan` 在 profile 缺失时会把 massing 归一化掉，
    #    于是 `apply_design_patch` 的"归一化越权"闸对**每一个**候选都触发 ⇒
    #    修订永远不生效，而且诊断只显示"归一化越权修改 massing"，看不出是这个原因。
    #    与 `design_flow/convergence.py:35` 同一口径。
    effective_architecture_profile = architecture_profile or detect_architecture_profile(
        user_message)

    draft_blocks = draft_blocks or draft_design_blocks
    started = now()
    max_rounds = min(_MAX_ROUNDS, max(0, int(max_rounds)))
    call_budget = min(_CALL_BUDGET, max(0, int(call_budget)))

    current = DesignDocument.model_validate(document)
    original = current.model_dump(mode="json")
    ledger = RevisionLedger()
    run = _Run()
    history: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    last_issues: int | None = None
    validate_connected = validate is not None
    render_connected = render is not None

    def _evaluate(doc: Any, compiled) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """渲染已编译的版本并评价，编译结果由调用方复用。"""

        blueprint = compiled.blueprint
        if not render_connected or not isinstance(blueprint, dict):
            return blueprint, None
        manifest = render(blueprint)
        from .evaluation import validated_review
        evaluation = validated_review(review(blueprint, manifest) if review else None, manifest)
        evaluation["proxy"] = proxy_evaluate(blueprint, doc.model_dump(mode="json"))
        evaluation["render"] = {
            **(manifest or {}),
            "baselineVersion": (manifest or {}).get("baselineVersion"),
            "shots": [s.get("file") for s in (manifest or {}).get("shots") or []],
        }
        return blueprint, evaluation

    base_result = compile_document(current)
    try:
        base_blueprint, base_evaluation = _evaluate(current, base_result)
        base_pipeline = validate(deepcopy(base_blueprint)) if (validate and base_blueprint) else 0
    except Exception as exc:
        return RevisionOutcome(document=original, blueprint=base_result.blueprint,
                               changed=False, diag={"stopReason": "render_error", "error": str(exc)}, ledger=ledger)
    base_issues = visible_issue_count(base_evaluation or {})
    ledger.record(label="baseline", design_hash=resolved_hash(current), blueprint=base_blueprint,
                  evaluation=base_evaluation, verdict=None, document=original)
    history.append(("baseline", base_blueprint, {**(base_evaluation or {}),
                                                    "compileErrors": sum(d.severity == "error" for d in base_result.defects),
                                                    "pipelineErrors": base_pipeline}))
    run.recorded.extend(recorded_only(base_evaluation or {}))

    if not render_connected or not validate_connected or not (base_evaluation or {}).get("complete"):
        # 🔴 没渲染就没有"可见"。拿几何数据编一个评价出来就是 P7-B 明令禁止的
        #   "假装做视觉判断"，所以这里直接停，并如实说明原因。
        run.stop_reason = "review_required"
        diag = _diag(run, max_rounds=max_rounds, call_budget=call_budget,
                     max_no_progress=max_no_progress, start=started, now=now)
        diag["renderConnected"] = render_connected
        diag["validateConnected"] = validate_connected
        diag["note"] = (
            "渲染、几何校验或完整截图评价尚未就绪；本次未做任何修订。"
            "这是 P7-B「不假装做视觉判断」的直接落点。"
        )
        return RevisionOutcome(document=original, blueprint=base_blueprint, changed=False,
                               diag=diag, ledger=ledger)

    def fulfillment_gaps(doc, compiled):
        from app.design.fulfillment import evaluate_fulfillment
        resolved = project_compilation(doc, compiled)
        resolved.design_gaps = [*resolved.design_gaps, *evaluate_fulfillment(
            doc, compiled.blueprint, resolved.design_hash,
            (compiled.stats.get("instance_overrides") or {}).get("instance_entities"),
            (compiled.design_brief or {}).get("roof_slots"),
        )]
        return resolved

    baseline_fulfillment = {g.id: g.status for g in fulfillment_gaps(current, base_result).design_gaps}
    for round_index in range(max_rounds):
        if now() - started >= time_budget:
            run.stop_reason = "time_budget"
            break
        evidence = build_vision_evidence(base_evaluation or {})
        if not evidence:
            run.stop_reason = "satisfied" if last_issues == 0 else "no_issues"
            break

        blocks: list[str] = []
        for item in evidence:
            block = block_of_design_field(str(item["target"]).strip("/").replace("/", "."))
            if block and block.name not in blocks:
                blocks.append(block.name)
        allowed_blocks = [b.name for b in ordered_blocks("standard") if b.name in blocks]
        if not allowed_blocks:
            # 认不出的映射不猜（convergence 红线 3）：只记录，不动稿。
            run.stop_reason = "no_issues"
            break
        if run.calls + len(allowed_blocks) > call_budget:
            run.stop_reason = "model_budget"
            break

        if on_reasoning_delta is not None:
            await on_reasoning_delta(
                "architecture:progress",
                f"\n### 视觉修订\n第 {round_index + 1} 轮，"
                f"发现 {len(evidence)} 项可见问题，重出：{'、'.join(allowed_blocks)}\n",
            )

        plan = architecture_plan_from_document(current)
        materials = current.decisions.materials.resolved_plan
        context = {**plan,
                   "material_plan": materials.model_dump(mode="json") if materials else None}
        run.calls += len(allowed_blocks)
        round_log: dict[str, Any] = {
            "round": round_index, "blocks": allowed_blocks,
            "evidence": [e["id"] for e in evidence], "baseHash": resolved_hash(current),
        }
        try:
            patch, block_diag = await asyncio.wait_for(draft_blocks(
                base_prompt=_REVISION_PROMPT + "\n本轮任务与完成条件：\n"
                             + _tasks_json(evidence, allowed_blocks, current),
                user_request=user_message, thinking_mode=thinking_mode,
                only_blocks=allowed_blocks, complexity_profile=complexity_profile,
                architecture_profile=effective_architecture_profile, current_plan=context,
                allow_probe=False, allow_design_changes=True, max_attempts=1,
                on_reasoning_delta=on_reasoning_delta,
            ), timeout=max(0.01, time_budget - (now() - started)))
        except asyncio.TimeoutError:
            run.stop_reason = "time_budget"
            break
        except Exception as exc:
            # 红线：模型故障不掐掉整轮生成，图纸仍然可用。
            logger.warning(f"[vision_revision] 重出设计块时模型故障，保留当前版本: {exc}")
            run.stop_reason = "model_error"
            round_log["modelError"] = str(exc)
            run.rounds.append(round_log)
            break

        if not patch or (block_diag or {}).get("unsettled_blocks"):
            round_log["noDraft"] = True
            round_log["unsettled"] = list((block_diag or {}).get("unsettled_blocks") or [])
            run.rounds.append(round_log)
            run.no_progress += 1
            if run.no_progress >= max(1, int(max_no_progress)):
                run.stop_reason = "no_progress"
                break
            continue

        try:
            candidate, normalization_changes, derived_changes = apply_design_patch(
                current, patch, allowed_blocks=allowed_blocks, user_message=user_message,
                complexity_profile=complexity_profile,
                architecture_profile=effective_architecture_profile,
            )
            round_log.update(normalizationChanges=normalization_changes, derivedChanges=derived_changes)
        except Exception as exc:
            round_log["rejectReason"] = str(exc)
            run.rounds.append(round_log)
            run.no_progress += 1
            if run.no_progress >= max(1, int(max_no_progress)):
                run.stop_reason = "invalid_candidate"
                break
            continue

        try:
            candidate_result = compile_document(candidate)
            candidate_blueprint, candidate_evaluation = _evaluate(candidate, candidate_result)
            candidate_pipeline = validate(deepcopy(candidate_blueprint)) if candidate_blueprint else 1
        except Exception as exc:
            round_log["renderOrValidationError"] = str(exc)
            run.rounds.append(round_log)
            run.stop_reason = "render_error"
            ledger.record(label=f"candidate_{round_index + 1}", design_hash=resolved_hash(candidate),
                          blueprint=None, evaluation=None, verdict=None,
                          document=candidate.model_dump(mode="json"))
            break
        candidate_resolved = fulfillment_gaps(candidate, candidate_result)
        verdict = candidate_verdict(
            result=candidate_result,
            fulfillment=candidate_resolved,
            baseline_fulfillment=baseline_fulfillment,
            pipeline_errors=candidate_pipeline,
            evaluation=candidate_evaluation,
            baseline_issues=last_issues if last_issues is not None else base_issues,
        )
        round_log.update({
            "issuesBefore": last_issues if last_issues is not None else base_issues,
            "issuesAfter": visible_issue_count(candidate_evaluation or {}),
            "verdict": verdict.to_dict(), "resultHash": resolved_hash(candidate),
        })
        run.rounds.append(round_log)

        label = f"candidate_{round_index + 1}"
        scored = {**(candidate_evaluation or {}),
                  "accepted": verdict.accepted,
                  "compileErrors": verdict.compile_errors,
                  "pipelineErrors": verdict.pipeline_errors,
                  "fulfillmentOpen": verdict.fulfillment_open}
        history.append((label, candidate_blueprint, scored))
        # 🔴截图列表可能为空（渲染回调没给图）。直接取 [0] 会在**候选刚通过
        #   校验之后**抛 IndexError，把一次成功的修订变成崩溃 —— 恰恰是最不该
        #   崩的时刻。取不到就留None，报告里显示"无截图"，不假装有。
        shots = ((candidate_evaluation or {}).get("render") or {}).get("shots") or []
        ledger.record(label=label, design_hash=resolved_hash(candidate),
                      blueprint=candidate_blueprint, evaluation=candidate_evaluation,
                      verdict=verdict,
                      screenshot=shots[0] if shots else None,
                      document=candidate.model_dump(mode="json"))
        run.recorded.extend(recorded_only(candidate_evaluation or {}))

        if not (candidate_evaluation or {}).get("complete"):
            run.stop_reason = "review_required"
            break

        if verdict.accepted:
            baseline_fulfillment = {g.id: g.status for g in candidate_resolved.design_gaps}
            current = candidate
            base_evaluation = candidate_evaluation
            base_blueprint = candidate_blueprint
            run.no_progress = 0 if verdict.issues < (last_issues if last_issues is not None else base_issues) else run.no_progress + 1
        else:
            # 变差 ⇒ 不采纳。current 保持不变即等价于回退，且历史留档在 ledger 里。
            run.no_progress += 1

        last_issues = visible_issue_count(base_evaluation or {})
        if last_issues == 0:
            run.stop_reason = "satisfied"
            break
        if run.no_progress >= max(1, int(max_no_progress)):
            run.stop_reason = "no_progress"
            break
    else:
        run.stop_reason = "max_rounds"

    best_label = pick_best(history)
    best_blueprint = history[0][1]
    current = DesignDocument.model_validate(original)
    if best_label and best_label != "baseline":
        best_blueprint = next((bp for lbl, bp, _ in history if lbl == best_label), base_blueprint)
        entry = ledger.of(best_label)
        if entry is not None and entry.get("document") is not None:
            current = DesignDocument.model_validate(entry["document"])

    diag = _diag(run, max_rounds=max_rounds, call_budget=call_budget,
                 max_no_progress=max_no_progress, start=started, now=now)
    diag["budget"]["timeBudgetSeconds"] = time_budget
    diag.update({
        "bestVersion": best_label,
        "adopted": bool(best_label and best_label != "baseline"),
        "renderConnected": render_connected,
        "validateConnected": validate_connected,
        "confidenceLevels": list(CONFIDENCE_LEVELS),
        "requiresDesignReview": bool(best_label and best_label != "baseline"),
    })
    return RevisionOutcome(
        document=current.model_dump(mode="json"),
        blueprint=best_blueprint,
        changed=current.model_dump(mode="json") != original,
        diag=diag, ledger=ledger,
    )


def _tasks_json(evidence: list[dict[str, Any]], blocks: list[str], document: Any) -> str:
    import json

    from app.agent.generation.architecture.design_blocks import block_of_design_field

    tasks = [{
        "id": item["id"], "block": block_of_design_field(item["target"]).name,
        "evidence": item["evidence"], "detail": item.get("detail"),
        "criterion": item["criterion"], "target": item["target"],
        "confidence": item["confidence"],
        "completion_condition": "该项可见问题消失，且编译/几何校验/履约都不变差",
    } for item in evidence]
    return json.dumps(
        {"base_revision": getattr(document, "revision", 1), "tasks": tasks},
        ensure_ascii=False,
    )


def resolved_hash(document: Any) -> str:
    from app.design.resolver import _stable_hash

    return _stable_hash(document)


@dataclass
class _Run:
    """一次修订运行的可变账本。

    🔴 不用 ``locals()`` 把局部变量传给诊断函数：那样一改函数签名，
       诊断就会**静默**拿到 ``None``，报告全错但测试照样绿。
       显式字段让"漏传"变成 ``AttributeError``，立刻炸。
    """

    rounds: list[dict[str, Any]] = field(default_factory=list)
    recorded: list[dict[str, Any]] = field(default_factory=list)
    calls: int = 0
    no_progress: int = 0
    stop_reason: str = "max_rounds"


def _diag(
    run: _Run, *, max_rounds: int, call_budget: int, max_no_progress: int,
    start: float, now: Callable[[], float],
) -> dict[str, Any]:
    return {
        "stopReason": run.stop_reason,
        "rounds": run.rounds,
        "revisionRounds": len(run.rounds),
        "noProgress": run.no_progress,
        "recordedOnly": run.recorded,
        "budget": {
            "maxRounds": max_rounds,
            "callBudget": call_budget,
            "usedCalls": run.calls,
            "maxNoProgress": max_no_progress,
        },
        "elapsedSeconds": round(now() - start, 3),
        "criteria": list(VISIBLE_CRITERIA),
        "stopReasons": list(STOP_REASONS),
    }


__all__ = [
    "CandidateVerdict",
    "RevisionLedger",
    "RevisionOutcome",
    "STOP_REASONS",
    "build_vision_evidence",
    "candidate_verdict",
    "pick_best",
    "recorded_only",
    "revise_by_visibility",
    "vision_design_field",
    "visible_issue_count",
]
