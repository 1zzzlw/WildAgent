"""验收：用户原话的四条验收条件不再阻断整轮生成。

用法（在 wild-server 目录下）：
    ./.venv/Scripts/python.exe ../.workbuddy/diag/check_no_block_2026-09-17.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[2] / "wild-server"
sys.path.insert(0, str(SERVER_DIR))

from app.agent.planning.execution import build_execution_plan  # noqa: E402
from app.agent.planning.requirements import (  # noqa: E402
    blocking_acceptance_failures,
    compile_structured_requirements,
    initialize_acceptance_results,
    validate_structured_requirements,
)

# 用户在 Agent 模式被拦下的四条原文。
ACCEPTANCE = [
    "建筑主体为两层矩形体量（约10x12米），附带一个一层矩形车库体量（约6x6米）",
    "两个体量在平面上呈L形连接，车库位于主楼侧翼",
    "计划分别为主楼和车库规划独立的屋顶轮廓，并注明屋顶类型为四坡屋顶（hip）",
    "为两层主楼生成一层地板、一层顶板（兼作二层地板）及二层顶板（屋顶承托），为一层车库生成地板",
]


def main() -> int:
    plan = build_execution_plan(
        request_id="req_no_block",
        intent="generate",
        user_message="生成一座两层住宅，带一个一层车库体量",
        planned_tasks=[
            {
                "title": "确定主体与车库体量",
                "objective": "确定两层主体与一层车库的组合体量、屋顶与楼板",
                "phase": "architecture",
                "acceptance": ACCEPTANCE,
                "basis": "用户需求",
            },
            {
                "title": "解析受控材质",
                "objective": "为体量、立面与楼板分配材质角色",
                "phase": "material_plan",
                "acceptance": ["材质角色齐全"],
                "basis": "受控材质协议",
            },
            {
                "title": "最终校验",
                "objective": "验证交付结果",
                "phase": "final_validate",
                "acceptance": ["完整校验零错误"],
                "basis": "WILD 协议",
            },
        ],
        planner_source="llm",
    )
    assert plan["planner_source"] == "llm", plan["dynamic_tasks"]

    requirements = compile_structured_requirements(plan)
    print("=== 四条验收条件各自编译成什么 ===")
    for requirement in requirements:
        if requirement["source_acceptance_id"] not in {
            f"acc_task_1_{index}" for index in range(1, len(ACCEPTANCE) + 1)
        }:
            continue
        expected = json.dumps(requirement["expected"], ensure_ascii=False)
        print(
            f"  [{requirement['severity']:>7}] {requirement['kind']:<26} "
            f"target={requirement['target']:<24} expected={expected[:52]}"
        )
        print(f"              {requirement['description'][:58]}")

    issues = validate_structured_requirements(requirements)
    blocking = [i for i in issues if str(i.get("severity") or "error") != "warning"]
    print(f"\n=== 计划校验 ===")
    print(f"  issues={len(issues)}  blocking={len(blocking)}")
    for issue in issues:
        print(f"  [{issue.get('severity', 'error')}] {issue['message'][:64]}")

    results = initialize_acceptance_results(requirements)
    delivery_blocking = blocking_acceptance_failures(requirements, results)
    unsupported_ids = {
        requirement["id"]
        for requirement in requirements
        if requirement["support_status"] == "unsupported"
    }
    leaked = [item for item in delivery_blocking if item["requirement_id"] in unsupported_ids]
    print("\n=== 交付阶段阻断项 ===")
    print(f"  全部未通过项（未跑节点，pending 也会列在这里）："
          f"{[item['requirement_id'] for item in delivery_blocking] or '无'}")
    print(f"  其中来自'缺能力'的：{[item['requirement_id'] for item in leaked] or '无'}")

    ok = not blocking and not leaked
    print("\n" + ("通过：四条缺能力要求都不会终止整轮生成" if ok else "未通过：仍会被阻断"))

    # 决定性一步：直接调用用户报错的那两个函数，看它到底走向 plan_review 还是 __end__。
    from app.agent.graph import _after_execution_plan_validator  # noqa: E402
    from app.agent.planning.workflow import execution_plan_validator  # noqa: E402

    print("\n=== 真实节点行为 ===")
    update = execution_plan_validator(
        {
            "intent": "generate",
            "execution_plan": plan,
            "structured_requirements": requirements,
            "acceptance_results": results,
            "execution_progress": {},
        }
    )
    print(f"  execution_plan_status = {update['execution_plan_status']}")
    print(f"  error                 = {update['error']}")
    route = _after_execution_plan_validator(update)
    print(f"  路由                  = {route}")
    ok = ok and update["execution_plan_status"] != "failed" and update["error"] is None
    ok = ok and route == "plan_review"
    print("\n最终：" + ("plan_validator 放行，进入人工审核" if ok else "仍被判 failed"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
