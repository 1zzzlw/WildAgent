"""真实事故回归：材质「N种」被误编译成构件「每种N个」，把已合并蓝图判死。

真实事件 2026-09-17 16:41，失败任务 req_1789634516108_eu82yreb4
（用户输入"生成一个别墅"，plan_mode）：

    错误: 业务验收未通过：实际数量：{'door': 1, 'window': 13, 'roof': 1}
    [1]~[10.2] 全部 20 个结构校验器【全部通过】，合并也成功（23 个元素）

本脚本从**真实检查点**取出那次运行的验收原文，用**真实的编译/校验函数**验证：

  修复前（已复现过）：原文"材质方案包含墙体、屋顶、门窗至少3种材质"
      被编译成 {"types":["door","window","roof"],"minimum":3} → door/roof < 3
      → failed（severity=error）→ blocking=1 → 整轮判死 + final_blueprint=None
  修复后（本脚本断言）：
      编译成 material_plan_exists + {"minimum":3}，真实 material_plan 有 9 个角色
      → passed → blocking=0

同时断言反向约束：真·实例要求（"至少N个"）不能被这次修复放水。

只读检查点；不改任何文件。
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "wild-server"
sys.path.insert(0, str(ROOT))

from app.agent.planning.requirements import (  # noqa: E402
    _compile_acceptance,
    _minimum_count,
    _minimum_kind_count,
    blocking_acceptance_failures,
)

FAILED_REQUEST = "req_1789634516108_eu82yreb4"
INCIDENT_TEXT = "材质方案包含墙体、屋顶、门窗至少3种材质"
DB = ROOT / "storage" / "sessions" / "langgraph_checkpoints.sqlite3"


def load_state(request_id: str) -> dict:
    """从 langgraph 检查点取出最后一个 channel_values（只读）。"""

    from langgraph.checkpoint.sqlite import SqliteSaver

    thread_id = f"generation:{request_id}"  # 注意前缀，裸 request_id 查不到
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, check_same_thread=False)
    ids = [
        row[0]
        for row in conn.execute(
            "select checkpoint_id from checkpoints where thread_id=? order by checkpoint_id",
            (thread_id,),
        )
    ]
    if not ids:
        raise SystemExit(f"找不到线程 {thread_id} 的检查点")
    saver = SqliteSaver(conn)
    tup = saver.get_tuple(
        {"configurable": {"thread_id": thread_id, "checkpoint_id": ids[-1]}}
    )
    return tup.checkpoint["channel_values"]


def main() -> int:
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"  [{'OK  ' if ok else 'FAIL'}] {label}{('  ' + detail) if detail else ''}")
        if not ok:
            failures.append(label)

    state = load_state(FAILED_REQUEST)

    print("=" * 74)
    print("第 1 步：那次运行的现场（读真实检查点）")
    print("=" * 74)
    merged = state.get("merged_blueprint")
    element_count = len((merged or {}).get("geometry", {}).get("elements", []))
    material_roles = len((state.get("material_plan") or {}).get("roles") or [])
    print(f"  user_message          = {state.get('user_message')!r}")
    print(f"  merged_blueprint      = {type(merged).__name__}（{element_count} 个元素）")
    print(f"  final_blueprint       = {type(state.get('final_blueprint')).__name__}")
    print(f"  material_plan.roles   = {material_roles} 个")
    print(f"  线上 error            = {state.get('error')}")
    print()
    print("  → 蓝图已经合并成功，却因为一条验收被编译错而整轮判死、成果丢弃。")

    print()
    print("=" * 74)
    print("第 2 步：量词区分（修复点一）")
    print("=" * 74)
    for text, want_instance, want_kind in (
        ("至少3种材质", 1, 3),
        ("至少3类构件", 1, 3),
        ("至少3个窗户", 3, None),
        ("至少6扇窗", 6, None),
    ):
        got_instance = _minimum_count(text)
        got_kind = _minimum_kind_count(text)
        check(
            f"{text!r} → 实例下限 {got_instance}、种类下限 {got_kind}",
            got_instance == want_instance and got_kind == want_kind,
            f"期望 {want_instance} / {want_kind}",
        )

    print()
    print("=" * 74)
    print("第 3 步：事故原文的编译结果（修复点二）")
    print("=" * 74)
    requirement = _compile_acceptance("task_4", 1, INCIDENT_TEXT, "final_validate")
    print(f"  原文     : {INCIDENT_TEXT}")
    print(f"  kind     : {requirement['kind']}")
    print(f"  validator: {requirement['validator']}")
    print(f"  expected : {json.dumps(requirement['expected'], ensure_ascii=False)}")
    check(
        "编译到 material_plan 而非 blueprint.components",
        requirement["validator"] == "material_plan_exists"
        and requirement["kind"] == "material_role_count",
    )
    check(
        "expected 只有种类下限，没有 types 列表",
        "types" not in requirement["expected"]
        and requirement["expected"] == {"minimum": 3},
    )
    check(
        "不再是构件存在性检查（正是它误读成每种>=3）",
        requirement["validator"] != "component_presence",
    )

    print()
    print("=" * 74)
    print("第 4 步：用现场真实数据重放验收")
    print("=" * 74)
    state["structured_requirements"] = [requirement]
    state["acceptance_results"] = {
        requirement["source_acceptance_id"]: {
            "status": "failed",
            "observed": {"door": 1, "window": 13, "roof": 1},
            "message": "实际数量：{'door': 1, 'window': 13, 'roof': 1}",
        }
    }
    # 用修复后的检查器重新判一次（材质角色 9 个）
    from app.agent.planning.requirements import evaluate_acceptance_results  # noqa: E402

    fresh = evaluate_acceptance_results(
        state={
            "structured_requirements": [requirement],
            "material_plan": state.get("material_plan"),
            "merged_blueprint": merged,
        },
        result={},
        phase="final_validate",
    )
    result = fresh[requirement["source_acceptance_id"]]
    print(f"  修复后验收结果 : status={result['status']} observed={result['observed']}")
    print(f"  message        : {result['message']}")
    check("材质角色 9 >= 3，判定 passed", result["status"] == "passed")
    check("observed 是材质角色数而不是构件数量", result["observed"] == material_roles)
    check(
        "不再构成阻断项",
        blocking_acceptance_failures([requirement], fresh) == [],
    )

    print()
    print("=" * 74)
    print("第 5 步：反向约束 —— 真·实例要求不能放水")
    print("=" * 74)
    instance_req = _compile_acceptance("task_9", 1, "至少生成3个窗户", "skeleton")
    print(f"  expected : {json.dumps(instance_req['expected'], ensure_ascii=False)}")
    check(
        "'至少生成3个窗户' 仍编译成 window>=3",
        instance_req["expected"] == {"types": ["window"], "minimum": 3},
    )

    print()
    print("=" * 74)
    if failures:
        print(f"结论：{len(failures)} 项未通过 → {failures}")
        return 1
    print("结论：全部通过。该事故已修复，且实例量词未被放水。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
