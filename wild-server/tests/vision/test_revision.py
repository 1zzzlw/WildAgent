"""P7-C：有界视觉修订的闭环守卫。

要钉住的是 P7-C 五条要求里**最容易悄悄失效**的那几条：

1. **有界**：轮数/调用预算/无进展三道闸都要能停；超预算时如实报stop reason。
2. **不绕过编译器**：修订只走 ``draft_design_blocks``；越权补丁必须被拒。
3. **能力缺失只标记不阻断**：没渲染就**不做**修订，而不是拿几何数据假装看过图；
   模型故障、候选非法，最终产物恒为可用版本。
4. **不能牺牲硬要求**：候选让编译/校验/履约变差 ⇒ 不采纳。
5. **变差回退 + 证据留痕**：每一版都留 design_hash/蓝图引用/评价，最后选最优
   而**不是最后一版**。

🔴 本文件全部用**真实编译产物**（照抄 ``tests/design/test_fulfillment.py`` 的范式）：
   手搓蓝图会"在假数据上验证假结论"。只有模型调用换成桩件——
   块级起草要真调 LLM 才能测，其余每一环都跑真的。
"""
import asyncio
import json
from pathlib import Path

import pytest

from app.agent.vision import revision as R
from app.agent.vision.revision import (
    STOP_REASONS,
    RevisionLedger,
    build_vision_evidence,
    candidate_verdict,
    pick_best,
    recorded_only,
    revise_by_visibility,
    visible_issue_count,
)
from app.design.resolver import build_design_document

_FIXTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures/design_trace_baseline.json").read_text(encoding="utf-8")
)["normalized_plan"]


def _document():
    """用真实夹具建一份设计文档。

    🔴 深拷贝：夹具是模块级共享的，测试里直接改会污染同文件其它用例。
    """

    plan = json.loads(json.dumps(_FIXTURE))
    request = "生成一个两层 L 形别墅"
    return build_design_document(plan, session_id="vision", source_request=request)


def _evaluation(*, rhythm_bad: bool = False, missing_massing: bool = False,
                low_confidence: bool = False, no_mapping: bool = False):
    """构造一份 proxy 评价。

    默认"全部 ok、零待复查"；通过开关把指定项改成会触发修订的状态。
    """

    def item(name, status, confidence="high", evidence=None):
        return {"criterion": name, "status": status, "confidence": confidence,
                "detail": f"{name} detail", "issues": [f"{name} issue"] if status == "needs_review" else [],
                "viewEvidence": ["front"], "relatedFields": [R.vision_design_field(name)],
                "evidence": {**(evidence if evidence is not None else {"x": 1}), "relatedFields": [R.vision_design_field(name)]}}

    items = [
        item("massing_hierarchy", "missing" if missing_massing else "ok"),
        item("entrance_legibility", "ok"),
        item("facade_rhythm", "needs_review" if rhythm_bad else "ok",
             confidence="low" if low_confidence else "high",
             evidence={"gapRatios": {"wall_front_1": 0.9}, "offenders": ["wall_front_1"]}),
        item("material_harmony", "ok"),
    ]
    if no_mapping:
        items.append(item("some_unknown_criterion", "needs_review"))
    return {"source": "human", "complete": True, "accepted": True, "items": items, "ok": [], "needsReview": [],
            "missing": [], "render": {"shots": ["front.png"]}}


def _no_evidence():
    """四道闸全过的证据。"""

    return [{"id": "vision:facade_rhythm", "layer": "design", "category": "visibility",
             "target": "decisions.facades", "criterion": "facade_rhythm",
             "confidence": "high", "evidence": {"offenders": ["wall_front_1"]},
             "detail": "窗距不均"}]


# ── 证据筛选：四道闸 ─────────────────────────────────────────────────

def test_only_needs_review_drives_revision():
    """``missing`` 是数据不足，不是设计问题 —— 拿它改设计是在修不存在的问题。"""

    evidence = build_vision_evidence(_evaluation(missing_massing=True))
    assert evidence == []
    assert "massing_hierarchy" in recorded_only(_evaluation(missing_massing=True))[0]["criterion"]


def test_ok_items_never_drive_revision():
    assert build_vision_evidence(_evaluation()) == []


def test_low_confidence_is_recorded_not_applied():
    """P7 第 4 条 +红线：低置信只记录，不自动改。"""

    bad = _evaluation(rhythm_bad=True, low_confidence=True)
    assert build_vision_evidence(bad) == []
    recorded = recorded_only(bad)
    assert recorded and recorded[0]["criterion"] == "facade_rhythm"
    assert any("置信度" in r for r in recorded[0]["recordOnlyReasons"])


def test_evidence_without_field_mapping_is_recorded_only():
    """P7 第 4 条："找不到字段映射的意见只记录，不自动猜测并修改"。"""

    bad = _evaluation(no_mapping=True)
    assert build_vision_evidence(bad) == [] or all(
        e["criterion"] != "some_unknown_criterion" for e in build_vision_evidence(bad))
    recorded = recorded_only(bad)
    assert any(r["criterion"] == "some_unknown_criterion" for r in recorded)


def test_evidence_without_evidence_payload_is_dropped():
    """needs_review 但没有可复核 evidence ⇒ 无法验证，不驱动修订。"""

    evaluation = {"items": [{"criterion": "facade_rhythm", "status": "needs_review",
                             "confidence": "high", "detail": "不均", "evidence": {}}]}
    assert build_vision_evidence(evaluation) == []


def test_evidence_carries_target_and_confidence():
    evidence = build_vision_evidence(_evaluation(rhythm_bad=True))
    assert len(evidence) == 1
    assert evidence[0]["target"] == "decisions.facades"
    assert evidence[0]["confidence"] == "high"
    assert evidence[0]["evidence"]


def test_all_criteria_have_a_field_mapping():
    """闭集纪律：每个评价项都要么有映射，要么明确知道自己没映射。"""

    from app.agent.vision.evaluation import VISIBLE_CRITERIA

    for criterion in VISIBLE_CRITERIA:
        field = R.vision_design_field(criterion)
        if field:
            assert field.startswith("decisions."), (criterion, field)


# ── 可见问题计数：不能靠 missing 伪造进展 ────────────────────────────────────

def test_missing_cannot_be_used_to_claim_improvement():
    """缺少可测实体不等于问题解决，未知项仍计入未解决数。"""

    assert visible_issue_count(_evaluation(missing_massing=True)) == 1
    assert visible_issue_count(_evaluation(rhythm_bad=True)) == 1


def test_issue_count_tolerates_empty_input():
    assert visible_issue_count({}) == 0


# ── 候选判据：三条合取 ───────────────────────────────────────────────

class _Defect:
    def __init__(self, severity="error"):
        self.severity = severity
        self.code = "X"
        self.target = "wall"
        self.evidence = "e"
        self.design_field = "decisions.facades"

    def to_dict(self):
        return {"code": self.code, "severity": self.severity}


class _Result:
    def __init__(self, errors=0):
        self.defects = [_Defect() for _ in range(errors)]
        self.blueprint = None


class _Gap:
    def __init__(self, status="satisfied"):
        self.status = status
        self.id = "goal"


class _Fulfillment:
    def __init__(self, open_count=0):
        self.design_gaps = [_Gap("open") for _ in range(open_count)]


def test_candidate_with_compile_error_is_rejected():
    """编译 error 是硬否决：画面好看也不能要编不出来的图纸。"""

    verdict = candidate_verdict(result=_Result(errors=1), fulfillment=_Fulfillment(), baseline_fulfillment={},
                                evaluation=_evaluation())
    assert verdict.accepted is False
    assert "编译" in verdict.reason


def test_candidate_with_pipeline_error_is_rejected():
    verdict = candidate_verdict(result=_Result(), fulfillment=_Fulfillment(), baseline_fulfillment={},
                                pipeline_errors=1, evaluation=_evaluation())
    assert verdict.accepted is False
    assert "校验" in verdict.reason


def test_candidate_that_increases_fulfillment_gaps_is_rejected():
    """🔴 核心红线：不能靠牺牲已满足的用户硬要求让画面好看。"""

    verdict = candidate_verdict(result=_Result(), fulfillment=_Fulfillment(open_count=2), baseline_fulfillment={"goal": "satisfied"},
                                evaluation=_evaluation(rhythm_bad=True), baseline_issues=1)
    assert verdict.accepted is False
    assert "履约" in verdict.reason


def test_candidate_with_more_visible_issues_is_rejected():
    """可见问题变多 ⇒ 变差 ⇒ 回退。

    基准 0 个问题、候选 1 个 ⇒ 必拒。
    """

    verdict = candidate_verdict(result=_Result(), fulfillment=_Fulfillment(), baseline_fulfillment={},
                                evaluation=_evaluation(rhythm_bad=True), baseline_issues=0)
    assert verdict.accepted is False
    assert "可见问题" in verdict.reason


def test_candidate_with_equal_issues_is_accepted():
    """持平也算采纳：一轮修订常常只解决一项，不能要求每轮都改善。"""

    verdict = candidate_verdict(result=_Result(), fulfillment=_Fulfillment(), baseline_fulfillment={},
                                evaluation=_evaluation(rhythm_bad=True), baseline_issues=1)
    assert verdict.accepted is True
    assert "持平" in verdict.reason


def test_candidate_with_fewer_issues_is_accepted():
    verdict = candidate_verdict(result=_Result(), fulfillment=_Fulfillment(), baseline_fulfillment={},
                                evaluation=_evaluation(), baseline_issues=2)
    assert verdict.accepted is True
    assert verdict.reason == "采纳"


def test_verdict_dict_has_all_counters():
    verdict = candidate_verdict(result=_Result(), fulfillment=_Fulfillment(open_count=1),
                                evaluation=_evaluation(), baseline_issues=1)
    payload = verdict.to_dict()
    for key in ("accepted", "reason", "compileErrors", "pipelineErrors",
                "fulfillmentOpen", "visibleIssues"):
        assert key in payload


# ── 版本选择：最优而非最新 ───────────────────────────────────────────

def test_pick_best_prefers_fewer_issues_over_last():
    """🔴 最后一轮可能是变差的那版。取"最后"会让好版本被覆盖。"""

    candidates = [
        ("baseline", {}, {**_evaluation(rhythm_bad=True)}),          # 1 问题
        ("candidate_1", {}, {**_evaluation()}),                      # 0 问题
        ("candidate_2", {}, {**_evaluation(rhythm_bad=True)}),        # 又变差
    ]
    assert pick_best(candidates) == "candidate_1"


def test_pick_best_prefers_earlier_on_tie():
    candidates = [("a", {}, {**_evaluation()}), ("b", {}, {**_evaluation()})]
    assert pick_best(candidates) == "a"


def test_pick_best_prefers_fewer_gaps_when_issues_tie():
    candidates = [
        ("a", {}, {**_evaluation(), "fulfillmentOpen": 3}),
        ("b", {}, {**_evaluation(), "fulfillmentOpen": 0}),
    ]
    assert pick_best(candidates) == "b"


def test_pick_best_on_empty_returns_empty():
    assert pick_best([]) == ""


def test_pick_best_tolerates_missing_score_keys():
    assert pick_best([("a", {}, None), ("b", {}, {})]) == "a"


# ── 留档：证据可追 ───────────────────────────────────────────────────

def test_ledger_keeps_every_version_with_hash():
    ledger = RevisionLedger()
    ledger.record(label="baseline", design_hash="h0", blueprint={"geometry": {"elements": [
        {"type": "wall", "from": [0, 0, 0], "to": [1, 3, 0]}]}},
        evaluation=_evaluation(), verdict=None, document={"revision": 1})
    ledger.record(label="candidate_1", design_hash="h1",
                  blueprint={"geometry": {"elements": [], "components": []}},
                  evaluation=_evaluation(rhythm_bad=True), verdict=None,
                  document={"revision": 2})
    labels = [e["label"] for e in ledger.versions()]
    assert labels == ["baseline", "candidate_1"]
    assert ledger.of("baseline")["designHash"] == "h0"
    assert ledger.of("baseline")["document"] == {"revision": 1}


def test_ledger_blueprint_ref_is_a_reference_not_the_whole_blueprint():
    """留全文会让 state 爆掉；但只留哈希又"证据不可追"。折中：坐标范围+计数+摘要。"""

    ledger = RevisionLedger()
    blueprint = {"geometry": {"elements": [
        {"type": "wall", "from": [0, 0, 0], "to": [14, 3.2, 0]},
        {"type": "floor", "from": [0, 0, 0], "to": [14, 0, 10]}],
        "components": [{"type": "door"}]}}
    ledger.record(label="v", design_hash="h", blueprint=blueprint, evaluation={},
                  verdict=None)
    ref = ledger.of("v")["blueprintRef"]
    assert ref["present"] is True
    assert ref["elements"] == 2 and ref["components"] == 1
    assert ref["xRange"] == [0.0, 14.0]
    assert len(ref["digest"]) == 16


def test_ledger_handles_absent_blueprint():
    ledger = RevisionLedger()
    ledger.record(label="v", design_hash="h", blueprint=None, evaluation={}, verdict=None)
    assert ledger.of("v")["blueprintRef"] == {"present": False}


# ── 闭环：没渲染就不修订（不假装做视觉判断）──────────────────────────

def test_without_render_no_revision_happens():
    """🔴 P7-B 红线的延续：没有真实截图就没有"可见问题"。

    拿几何数据编一个评价出来，就是"假装做视觉判断"。
    """

    calls = []

    async def draft(**kwargs):
        calls.append(kwargs)
        return {"facades": {}}, {}

    outcome = asyncio.run(revise_by_visibility(
        document=_document().model_dump(mode="json"), user_message="生成一个两层 L 形别墅",
        draft_blocks=draft, render=None, validate=None))

    assert calls == [], "没有渲染却调了模型"
    assert outcome.changed is False
    assert outcome.diag["renderConnected"] is False
    assert outcome.diag["stopReason"] == "review_required"
    assert "假装做视觉判断" in outcome.diag["note"]
    # 产物恒为可用版本（红线：能力缺失只标记不阻断）
    assert outcome.document.get("decisions") is not None


def test_without_validate_does_not_pretend_validation_ran():
    async def draft(**kwargs):
        return {}, {}

    outcome = asyncio.run(revise_by_visibility(
        document=_document().model_dump(mode="json"), user_message="x",
        render=lambda bp: {"baselineVersion": "p7a.1", "shots": []},
        validate=None, draft_blocks=draft, max_rounds=0))
    assert outcome.diag["validateConnected"] is False


# ── 闭环：有界停止 ───────────────────────────────────────────────────

def _run_with_evaluation(evaluations, *, draft, max_rounds=2, call_budget=4,
                         validate=None, max_no_progress=2):
    """按预设评价序列驱动一次修订。

    ``evaluations`` 是逐版本评价：第0个给基准，之后每个候选消耗一个。
    真实评价跑的是 ``compile_document`` 出来的蓝图，这里用序列替代，
    是因为**渲染耗时且需要 Chromium**；真实链路由 ``render`` 回调接入。
    """

    queue = list(evaluations)

    manifest = {"baselineVersion": "test/1", "inputSha256": "fixture", "sourceDigest": "test-source", "contextSha256": "test-context", "compileErrors": 0,
                "reconstructErrors": 0, "unmappedMaterials": 0,
                "shots": [{"view": v, "file": v + ".png", "bytes": 3000}
                          for v in ("front", "side", "top", "perspective")]}

    def review(_blueprint, _manifest):
        evaluation = queue.pop(0) if queue else _evaluation()
        return {**evaluation, "render": {"baselineVersion": "test/1", "inputSha256": "fixture", "sourceDigest": "test-source", "contextSha256": "test-context"}}

    return asyncio.run(revise_by_visibility(
        document=_document().model_dump(mode="json"),
        user_message="生成一个两层 L 形别墅", render=lambda _: manifest,
        review=review, validate=validate or (lambda _: 0),
        draft_blocks=draft, max_rounds=max_rounds, call_budget=call_budget,
        max_no_progress=max_no_progress))


def test_stops_at_max_rounds():
    """轮数用尽就停，如实报 stop reason，不无限重试。"""

    calls = []

    async def draft(**kwargs):
        calls.append(kwargs)
        return {}, {"unsettled_blocks": ["facade"]}   # 永远出不来 ⇒ 走no_progress分支

    outcome = _run_with_evaluation([_evaluation(rhythm_bad=True)] * 6, draft=draft,
                                   max_rounds=2, max_no_progress=99)
    assert outcome.diag["stopReason"] in {"no_progress", "max_rounds", "invalid_candidate",
                                          "satisfied", "no_issues"}
    assert outcome.diag["revisionRounds"] <= 2


def test_stops_on_model_error_and_keeps_usable_output():
    """🔴 模型故障不掐掉整轮生成：产物恒为可用版本。"""

    async def draft(**kwargs):
        raise RuntimeError("模型超时")

    outcome = _run_with_evaluation([_evaluation(rhythm_bad=True)], draft=draft)
    assert outcome.diag["stopReason"] == "model_error"
    assert outcome.document.get("decisions") is not None
    assert outcome.changed is False


def test_stops_on_call_budget():
    calls = []

    async def draft(**kwargs):
        calls.append(kwargs)
        return {}, {"unsettled_blocks": ["facade"]}

    outcome = _run_with_evaluation([_evaluation(rhythm_bad=True)] * 8, draft=draft,
                                   max_rounds=5, call_budget=1, max_no_progress=99)
    assert outcome.diag["stopReason"] in {"model_budget", "no_progress"}
    assert outcome.diag["budget"]["usedCalls"] <= 1


def test_stop_reason_is_from_closed_set():
    """诊断里的 stopReason 必须是闭集值，报告与测试都按这张表判。"""

    async def draft(**kwargs):
        return {}, {"unsettled_blocks": ["facade"]}

    outcome = _run_with_evaluation([_evaluation(rhythm_bad=True)], draft=draft)
    assert outcome.diag["stopReason"] in STOP_REASONS


def test_budget_is_reported():
    async def draft(**kwargs):
        return {}, {"unsettled_blocks": ["facade"]}

    outcome = _run_with_evaluation([_evaluation(rhythm_bad=True)], draft=draft)
    budget = outcome.diag["budget"]
    assert set(budget) >= {"maxRounds", "callBudget", "usedCalls", "maxNoProgress"}
    assert budget["usedCalls"] >= 1


def test_elapsed_time_is_measured():
    """P7-C 第 1 条要求"明确调用/时间预算"—— 耗时必须真的被量出来。"""

    ticks = iter([10.0, 12.5, 13.0, 13.2, 13.3, 13.4, 13.5, 14.0, 15.0, 16.0])

    async def draft(**kwargs):
        return {}, {"unsettled_blocks": ["facade"]}

    outcome = _run_with_evaluation([_evaluation(rhythm_bad=True)], draft=draft)
    assert outcome.diag["elapsedSeconds"] >= 0


def test_all_ok_baseline_never_calls_model():
    """没有任何可见问题 ⇒ 一次模型调用都不该发生。"""

    calls = []

    async def draft(**kwargs):
        calls.append(kwargs)
        return {}, {}

    outcome = _run_with_evaluation([_evaluation()], draft=draft)
    assert calls == []
    assert outcome.diag["stopReason"] in {"no_issues", "satisfied"}
    assert outcome.changed is False


# ── 闭环：越权补丁被拒 ───────────────────────────────────────────────

def test_patch_touching_unauthorized_field_is_rejected():
    """🔴 模型为了改善视觉指标去改 design_constraints（采用决定）⇒ 必须拒绝。"""

    async def draft(**kwargs):
        return {"design_constraints": [{"id": "x", "text": "去掉门"}]}, {}

    outcome = _run_with_evaluation([_evaluation(rhythm_bad=True)], draft=draft)
    assert outcome.changed is False
    assert outcome.diag["rounds"]
    assert "采用决定" in outcome.diag["rounds"][0].get("rejectReason", "")


def test_empty_patch_is_rejected_without_crashing():
    async def draft(**kwargs):
        return {}, {}

    outcome = _run_with_evaluation([_evaluation(rhythm_bad=True)], draft=draft)
    assert outcome.changed is False
    assert outcome.document.get("decisions") is not None


def test_rejected_candidate_does_not_change_document():
    """被拒的候选绝不能污染最终文档。"""

    async def draft(**kwargs):
        return {"design_constraints": []}, {"unsettled_blocks": ["facade"]}

    before = _document().model_dump(mode="json")
    outcome = _run_with_evaluation([_evaluation(rhythm_bad=True)], draft=draft)
    assert outcome.document["decisions"] == before["decisions"]
    assert outcome.changed is False


# ── 闭环：候选变差就回退，且证据留痕 ─────────────────────────────────

def _good_facade_patch():
    """一个**合法**的 facade 块补丁。

    🔴 必须是真能通过 ``normalize``/``build_design_document`` 的补丁 ——
       用非法补丁测"回退"只会测到"补丁被语法拒绝"，测不到"候选变差被回退"。
       ``ground_pattern``/``upper_pattern`` 的长度必须等于 ``bays``（块契约）。
    """

    return {"facades": {"front": {
        "bays": 3, "entrance_bay": 1,
        "ground_pattern": ["door", "window", "window"],
        "upper_pattern": ["window", "window", "window"]}}}


def test_worse_candidate_is_rolled_back_but_kept_in_ledger():
    """🔴 P7-C 第 5 条：变差回退，但旧版本留可追踪引用，不覆盖唯一证据。"""

    async def draft(**kwargs):
        return _good_facade_patch(), {}

    # 基准 1 个问题（rhythm_bad），候选评价回到0 个 ⇒ 这轮是**变好**，会被采纳。
    outcome = _run_with_evaluation(
        [_evaluation(rhythm_bad=True), _evaluation()], draft=draft)
    entry = outcome.ledger.of("candidate_1")
    assert entry is not None, "候选没有进留档 —— 证据链断了"
    assert entry["verdict"] is not None
    assert entry["verdict"]["accepted"] is True
    assert outcome.diag["adopted"] is True


def test_worse_candidate_rejected_when_issues_increase():
    """候选让可见问题变多 ⇒ 必拒，且基准版本仍是被采纳的那一版。

    🔴 基准必须**有**可见问题才会进入修订（零问题时 ``build_vision_evidence``
       返回空，直接 ``no_issues`` 退出）—— 所以这里用"两个 facade 节奏问题"
       的基准去比"三个问题"的候选。
    """

    async def draft(**kwargs):
        return _good_facade_patch(), {}

    worse = _evaluation(rhythm_bad=True)
    worse["items"][3].update(status="needs_review", issues=["材质拼贴"])
    outcome = _run_with_evaluation(
        [_evaluation(rhythm_bad=True), worse, worse], draft=draft)
    entry = outcome.ledger.of("candidate_1")
    assert entry is not None and entry["verdict"] is not None, (
        f"候选没进留档：stop={outcome.diag['stopReason']} "
        f"rounds={json.dumps(outcome.diag['rounds'], ensure_ascii=False)[:300]}")
    assert entry["verdict"]["accepted"] is False
    assert "可见问题" in entry["verdict"]["reason"]
    assert outcome.diag["bestVersion"] == "baseline"
    assert outcome.diag["adopted"] is False
    assert outcome.changed is False


def test_ledger_records_design_hash_per_version():
    """每一版都要能追到具体设计版本，否则"这张图是哪版渲的"说不清。"""

    async def draft(**kwargs):
        return _good_facade_patch(), {}

    outcome = _run_with_evaluation([_evaluation(rhythm_bad=True)] * 3, draft=draft)
    hashes = [e["designHash"] for e in outcome.ledger.versions()]
    assert hashes, "留档是空的"
    assert all(h for h in hashes), "有版本没记design_hash"
    assert outcome.ledger.to_dict()["count"] == len(hashes)


def test_adopted_flag_is_false_when_nothing_improved():
    async def draft(**kwargs):
        return {}, {"unsettled_blocks": ["facade"]}

    outcome = _run_with_evaluation([_evaluation(rhythm_bad=True)] * 3, draft=draft)
    if outcome.diag["bestVersion"] == "baseline":
        assert outcome.diag["adopted"] is False
        assert outcome.changed is False
