"""汇总三组真实运行证据；不调用模型、不伪造通用 Agent 对照产物。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .benchmark import GROUPS, RUNS_PER_TASK, TASKS, ScoreCard, task_spec_digest, significance_claim


def summarize(records: list[dict]) -> dict:
    cards = {(group, task.id): ScoreCard(group=group, task_id=task.id)
             for group in GROUPS for task in TASKS}
    seen = set()
    for record in records:
        key = (record.get("group"), record.get("taskId"))
        run_id = record.get("runId")
        if key not in cards or not isinstance(run_id, str) or not run_id:
            raise ValueError("每条记录须提供合法 group、taskId 与非空 runId")
        if (*key, run_id) in seen:
            raise ValueError(f"重复运行记录：{key} / {run_id}")
        if record.get("taskSpecDigest") != task_spec_digest():
            raise ValueError("评测标准摘要不同，不能混合统计")
        if record.get("failureType") == "not_run":
            continue
        seen.add((*key, run_id))
        card = cards[key]
        card.runs += 1
        geometry = record.get("geometry") or {}
        # 缺少校验结果、失败和超时都保留在运行分母中。
        valid = geometry.get("valid") is True and bool(geometry.get("evidence"))
        card.success_runs += int(valid)
        if not valid:
            card.failure_types.append(str(record.get("failureType") or "geometry_unverified"))
        results = record.get("requirements") or {}
        task = next(task for task in TASKS if task.id == key[1])
        for requirement in task.requirements:
            result = results.get(requirement.id) or {}
            status = result.get("status", "needs_review")
            if status not in {"satisfied", "open", "unsupported", "needs_review"}:
                raise ValueError(f"未知验收状态：{status}")
            if not result.get("evidence"):
                status = "needs_review"
            card.by_status[status] = card.by_status.get(status, 0) + 1
            if status in {"satisfied", "open"}:
                card.satisfied[f"{run_id}:{requirement.id}"] = status == "satisfied"
        for field, target in (("modelCalls", card.call_counts), ("tokens", card.token_counts),
                              ("durationSeconds", card.durations)):
            value = record.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                target.append(value)
        card.screenshot_index.extend(str(path) for path in record.get("screenshots") or [])
    return {
        "taskSpecDigest": task_spec_digest(),
        "groups": [{**card.to_dict(), "missingRuns": max(0, RUNS_PER_TASK - card.runs),
                    "interpretation": significance_claim(card.runs)} for card in cards.values()],
        "complete": all(card.runs >= RUNS_PER_TASK for card in cards.values()),
        "note": "未知项单列；失败计入分母；仅汇总提供的证据。视觉效果需匿名看图比较，不能由代理指标代替。",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--records", type=Path, help="各组真实运行记录的 JSON 数组；省略时生成待填写模板")
    args = parser.parse_args()
    if args.records:
        result = summarize(json.loads(args.records.read_text(encoding="utf-8-sig")))
    else:
        result = [{
            "group": group, "taskId": task.id, "runId": str(run + 1),
            "taskSpecDigest": task_spec_digest(), "prompt": task.prompt,
            "geometry": {"valid": None, "evidence": ""},
            "requirements": {r.id: {"status": "needs_review", "evidence": "", "criterion": r.description}
                             for r in task.requirements},
            "modelCalls": None, "tokens": None, "durationSeconds": None,
            "screenshots": [], "failureType": "not_run",
        } for group in GROUPS for task in TASKS for run in range(RUNS_PER_TASK)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
