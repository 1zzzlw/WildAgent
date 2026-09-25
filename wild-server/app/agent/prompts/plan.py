"""plan 阶段的策略提示词：模型只出策略，不出条目、不出坐标。

对应《动态节点设计规划》§3.2：**模型定策略，程序定条目**。

模型要回答的问题只有三个：这次做哪些构件、每类构件走什么形态、有没有额外要补的工作。
条目 id、执行顺序、坐标、数量全部由 ``expand_plan`` 与设计清单决定，所以同一份策略
两次展开必然得到同一串条目。
"""

from __future__ import annotations

import json

_PLAN_NOTE = """你是建筑生成的「计划策略」决策者。你面对的是一个已经完成方案设计、材质方案与
主体骨架的工程流水线：几何已经确定，缺的只是"接下来做哪些构件、按什么形态做"。

你只输出**策略**，不输出几何、不输出数量、不输出坐标。坐标与数量由设计清单
（component_quota / 任意 *_slots 槽位集合）与骨架给定，后续节点会逐字遵守。
"""

_PLAN_RULES = """# 硬性约束

1. `kind` 只能取自【可派发能力清单】，不得创造新类型；不在清单里的需求只能放弃。
2. 不得输出坐标、尺寸、数量、元素 id——写了也会被忽略。
3. `subtype` / `guidance` 是给下游生成节点的**形态提示**（例如门的样式、栏杆的间距风格），
   没有把握就留空，不要编造具体数值。
4. 用户明确否定的构件（清单里的 skip 语义）不要出现。
5. 设计清单里 `min > 0` 的构件必须出现，否则配额无法满足。
6. 每一类构件都要给一句 `reason`，说明为什么这一次要做它。
7. 同一 `kind` 只输出一次；同类重复槽位由一个批次条目一次生成，不能按槽位逐条拆分。
8. 互不依赖、不会写同一构件类型的任务可设 `execution_mode=parallel`，并使用相同
   `parallel_group`；有依赖、需要先看前一批产物或把握不足时必须用 `serial`。
9. `batch_reason` 说明为什么该类型适合一次批量生成，例如“多个同类槽位只有少量尺寸变体”。
"""

_PLAN_OUTPUT = """# 输出格式

只输出一个 JSON 对象，不要解释、不要 Markdown 代码块：

```json
{
  "kinds": [
    {"kind": "door", "subtype": "入户双开门", "guidance": "主入口居中", "reason": "用户点名要入户门", "execution_mode": "parallel", "parallel_group": "openings", "batch_reason": "单个入口槽位"},
    {"kind": "window", "subtype": "", "guidance": "", "reason": "骨架立面已开窗位", "execution_mode": "parallel", "parallel_group": "openings", "batch_reason": "同类窗槽一次批量生成"}
  ],
  "detail_level": "standard",
  "notes": "一层住宅，重点在入口与立面节奏"
}
```

- `detail_level` 只能取 `minimal` / `simple` / `standard` / `detailed`；没有把握就省略。
- `notes` 一句话说明本次策略取舍，会进交付审计。
"""


def build_plan_strategy_prompt(
    *,
    capability_catalog: list[dict],
    design_brief: dict | None,
    skeleton_summary: str,
    detail_level: str,
    slot_counts: dict[str, int] | None = None,
    slot_batches: dict[str, object] | None = None,
    architecture_plan: dict | None = None,
) -> str:
    """构建策略系统提示词。

    ``capability_catalog`` 来自 ``COMPONENT_REGISTRY``，是模型可选项的**唯一**来源；
    ``slot_counts`` 是设计清单里每类构件的精确槽位数量（模型能看到工作量，但不能改它）。
    """

    quota = {}
    if isinstance(design_brief, dict):
        raw_quota = design_brief.get("component_quota")
        if isinstance(raw_quota, dict):
            quota = raw_quota

    lines = []
    for entry in capability_catalog:
        item = f"- {entry.get('kind')}（{entry.get('label')}）"
        if entry.get("depends_on"):
            item += f" 依赖：{'、'.join(entry['depends_on'])}"
        if entry.get("is_element"):
            item += " 写入 elements"
        if entry.get("skip_keywords"):
            item += f" 否定词：{'、'.join(entry['skip_keywords'])}"
        minimum = quota.get(entry.get("kind"), {})
        if isinstance(minimum, dict) and minimum.get("min"):
            item += f" 配额下限：{minimum['min']}"
        slots = (slot_counts or {}).get(str(entry.get("kind")), 0)
        if slots:
            item += f" 精确槽位：{slots} 个"
        lines.append(item)

    facade = ""
    if isinstance(design_brief, dict):
        facade_plan = design_brief.get("facade_plan")
        if facade_plan:
            facade = json.dumps(facade_plan, ensure_ascii=False, default=str)[:1500]

    return "\n\n".join(
        part
        for part in (
            _PLAN_NOTE,
            _PLAN_RULES,
            "# 可派发能力清单\n\n" + ("\n".join(lines) or "（空：本次没有任何可做构件）"),
            f"# 本次生成档位\n\n{detail_level}",
            "# 已批准总体方案摘要\n\n"
            + (
                json.dumps(
                    {
                        key: architecture_plan.get(key)
                        for key in (
                            "profile", "massing", "volumes", "structural_grid",
                            "required_components", "detail_packages",
                        )
                        if architecture_plan.get(key) is not None
                    },
                    ensure_ascii=False,
                    default=str,
                )[:2500]
                if isinstance(architecture_plan, dict)
                else "（未提供）"
            ),
            "# 槽位批次摘要\n\n"
            + (
                json.dumps(slot_batches, ensure_ascii=False, default=str)
                if slot_batches else "（没有可分组槽位）"
            ),
            f"# 设计清单要点\n\n{facade or '（方案未给出立面清单）'}",
            f"# 主体骨架摘要\n\n{skeleton_summary or '（未提供骨架摘要）'}",
            _PLAN_OUTPUT,
        )
        if part
    )


def build_plan_strategy_user_message(user_message: str, design_brief: dict | None) -> str:
    """用户消息 + 配额摘要：模型据此判断"这次真正要做什么"。"""

    quota = {}
    if isinstance(design_brief, dict) and isinstance(design_brief.get("component_quota"), dict):
        quota = design_brief["component_quota"]
    quota_line = json.dumps(quota, ensure_ascii=False, default=str) if quota else "（无配额约束）"
    return f"用户需求：{user_message}\n\n本次构件配额：{quota_line}"


# ── replanner 的异常分支提示词（§5.3）──

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
