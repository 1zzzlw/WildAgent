"""复现并回归验证：表现层诉求与能力缺失都不再硬阻断整轮生成。

政策变更（2026-09-17，用户明确要求）：`unsupported` 一律编译为 `severity="warning"`，
只标记不阻断——"就算他没有能力生成车库也没关系，不能连尝试都不能尝试"。
因此本脚本里两条例外（房间布局、车库）的期望已从 True 改为 False。
真正还能阻断的只剩"计划对象本身不合法"和"模型服务终态错误"。

用法（在 wild-server 目录下）：
    .venv/Scripts/python.exe ../.workbuddy/diag/check_plan_gate_2026-09-17.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[2] / "wild-server"
sys.path.insert(0, str(SERVER_DIR))

from app.agent.planning.requirements import (  # noqa: E402
    _compile_acceptance,
    compile_structured_requirements,
    validate_structured_requirements,
)

CASES: list[tuple[str, str, str]] = [
    ("plan", "architecture", "生成一份明确的建筑平面草图，标注出主楼的宽度、进深尺寸（例如：宽约12米，深约10米）"),
    ("plan", "architecture", "绘制建筑平面图，主楼宽12米，深10米"),
    ("plan", "architecture", "建筑共两层，首层与二层都要有明确层高"),
    ("plan", "architecture", "屋顶必须采用 gable 类型"),
    ("plan", "architecture", "标注房间布局，明确主要房间位置"),
    ("plan", "architecture", "需要包含一个车库"),
    ("plan", "final_validate", "整体外观看起来要协调美观"),
]

EXPECT_BLOCKING = {
    "生成一份明确的建筑平面草图，标注出主楼的宽度、进深尺寸（例如：宽约12米，深约10米）": False,
    "绘制建筑平面图，主楼宽12米，深10米": False,
    # 以下两条原先期望 True（缺能力 = 硬阻断），政策变更后统一为只标记不阻断。
    "标注房间布局，明确主要房间位置": False,
    "需要包含一个车库": False,
}


def main() -> int:
    failed = 0
    for index, (task_id, phase, text) in enumerate(CASES, start=1):
        requirement = _compile_acceptance(task_id, index, text, phase)
        blocking = requirement["severity"] == "error" and requirement["support_status"] == "unsupported"
        expect = EXPECT_BLOCKING.get(text)
        flag = "  " if expect is None or expect == blocking else "!!"
        if expect is not None and expect != blocking:
            failed += 1
        print(f"{flag} [{requirement['severity']:>7}] {requirement['kind']:<28} "
              f"target={requirement['target']:<26} {text[:34]}")
        if requirement["kind"] == "architecture_dimensions":
            print(f"       expected={json.dumps(requirement['expected'], ensure_ascii=False)}")

    print("\n--- 走完整编译 + 校验链路 ---")
    plan = {
        "dynamic_tasks": [
            {
                "id": "t_arch",
                "phase": "architecture",
                "acceptance": [CASES[0][2]],
            }
        ]
    }
    requirements = compile_structured_requirements(plan)
    issues = validate_structured_requirements(requirements)
    blocking = [i for i in issues if str(i.get("severity") or "error") != "warning"]
    print(f"requirements={len(requirements)} issues={len(issues)} blocking={len(blocking)}")
    for issue in issues:
        print(f"  [{issue.get('severity', 'error')}] {issue['code']}: {issue['message'][:60]}")
    if blocking:
        failed += 1
        print("!! 用户原句仍然被阻断")
    else:
        print("OK 用户原句不再阻断（issue 降级为 warning，交 plan_review 人工裁决）")

    print(f"\nfailed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
