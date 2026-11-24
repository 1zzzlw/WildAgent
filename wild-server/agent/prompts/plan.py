"""图纸实现任务的重规划提示词。"""
from __future__ import annotations

import json

_REPLAN_NOTE = """你是建筑生成流水线的「循环调度者」。计划已经展开并在逐条执行，现在出现了
异常：有条目反复失败，或有条目被依赖失败卡住。你要在**允许的五个动作**里选一个，
让这一轮能收尾。

你不写几何、不写坐标、不写数量：追加条目只描述"做什么"，坐标与数量仍由设计清单决定。
"""

_REPLAN_ACTIONS = """# 允许的动作（只能选一个，action 字段）

| action | 语义 | 需要哪些字段 |
| --- | --- | --- |
| `add_items` | 追加条目（补充被漏掉的工作） | `items`: `[{"op":"generate","kind":"railing","reason":"..."}]` |
| `replace_item` | 调整失败条目的输出格式或受支持形态，保留批准的槽位、数量与宿主 | `item_id` + `params`: `{"subtype":"...","guidance":"..."}` |
| `drop_item` | 放弃某条条目（进交付清单的未完成项） | `item_id` + `reason` |
| `mark_unsupported` | 标注为能力缺失（只标记不阻断） | `item_id` + `reason` |
| `give_up` | 停止追加，带警告交付当前成果 | `reason` |

四条硬约束：

1. `op` 只能取 `generate` / `merge` / `validate` / `fix` / `repair`；`kind` 只能取能力清单里的值。
2. 追加条目最多 2 次（`revision` 上限），超了会被程序拒绝——不要靠不断追加解决问题。
3. 首次失败且仍有调整额度时必须使用 `replace_item`，并根据 evidence 给出新的
   `subtype` / `guidance`；此时禁止 `drop_item`、`mark_unsupported` 或 `give_up`。
4. 只有失败条目已经做过一次定向调整、或尝试额度耗尽后，才允许放弃该条目；
   只有所有剩余失败都不可恢复时才允许 `give_up`。
5. `reason` 只能引用异常摘要中的 evidence，不得猜测“宿主墙不足”等未提供事实。
6. 不要重复已经标 `done` 的工作。
7. 工具参数错误、调用循环超限属于执行故障，不是数量或宿主设计错误；不得以此减少构件、删除槽位或改换宿主。
"""

_REPLAN_OUTPUT = """# 输出格式

只输出一个 JSON 对象，不要解释、不要 Markdown 代码块：

```json
{"action": "add_items", "items": [{"op": "generate", "kind": "railing", "reason": "阳台已落地但缺少栏杆"}], "reason": "补齐阳台防护"}
```

或：

```json
{"action": "give_up", "reason": "门宿主墙尺寸不足，两轮尝试都未产出可用片段"}
```
"""


def build_replan_prompt(*, capability_catalog: list[dict], revision: int, revision_limit: int) -> str:
    """构建 replanner 异常分支的系统提示词（含动作闭集与能力清单）。"""

    lines = []
    for entry in capability_catalog:
        item = f"- {entry.get('kind')}（{entry.get('label')}）"
        if entry.get("is_element"):
            item += " 写入 elements"
        lines.append(item)
    return "\n\n".join(
        part
        for part in (
            _REPLAN_NOTE,
            _REPLAN_ACTIONS,
            "# 可用构件类型（kind 的合法取值）\n\n" + ("\n".join(lines) or "（空）"),
            f"# 追加预算\n\n当前 revision {revision}/{revision_limit}（达到上限后 `add_items` 会被拒绝）",
            _REPLAN_OUTPUT,
        )
        if part
    )


def build_replan_user_message(summary: dict) -> str:
    """把"哪些条目出了问题、蓝图现在长什么样"讲清楚，其余一律不给（控制上下文）。"""

    return "# 本轮异常摘要\n\n" + json.dumps(summary, ensure_ascii=False, default=str)[:4000]
