"""plan 条目与 plan 文档的唯一类型定义。

对应《动态节点设计规划》§2.2（PlanItem 字段契约）与 §2.6（两个状态机）。

两条硬规定（不得放松）：
1. 模型不写任何状态字段——计划态只由 ``reconcile`` 写，执行态只由 ``execute`` 写。
2. 条目 id 必须确定性生成（``{op}_{kind}_{序号}``），不使用随机数、时间戳或 uuid，
   否则同一份输入两次运行的产物不同，回归样例与双跑对照都失去意义。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PLAN_SCHEMA_VERSION = "plan/1.0"

#: op 是闭集（§2.3）。新增 op 属于架构变更，需要同时补执行器与测试。
OPS: tuple[str, ...] = ("generate", "merge", "validate", "fix", "repair")

#: 计划态的四个终态（§2.6）。``run.state == "failed"`` 不是终态。
TERMINAL_STATUSES: tuple[str, ...] = ("done", "abandoned", "skipped", "unsupported")

#: merge 的两种作用域（§3.3 / §4.4）。批次合并只"并入"，收尾合并才"归一"。
#: 两者的区别是硬约束：只有收尾合并有权删改元素，所以只有它的结论能判定"产物没落地"。
MERGE_SCOPES: tuple[str, ...] = ("batch", "final")

PlanStatus = Literal[
    "pending",  # 待办
    "ready",  # 依赖已满足，下一轮可执行
    "blocked",  # 依赖未完成或已失败
    "done",  # 产物已产出且已并入蓝图并对账通过
    "abandoned",  # 重试耗尽或判定无法完成，进交付清单
    "skipped",  # 计划不再需要（进交付清单）
    "unsupported",  # 能力缺失（只标记不阻断）
]

RunState = Literal[
    "idle",
    "running",
    "succeeded",
    "failed",
    "aborted",
]


class PlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ItemRun(PlanModel):
    """执行态：一条条目"这一次跑成没跑成"。只有 ``execute`` 写这个字段。"""

    state: RunState = "idle"
    attempts: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)
    artifacts: list[str] = Field(default_factory=list, max_length=200)
    evidence: str = Field(default="", max_length=2000)
    elapsed_ms: int | None = Field(default=None, ge=0)

    @property
    def exhausted(self) -> bool:
        return self.attempts >= self.max_attempts


class PlanItem(PlanModel):
    """一条工作项：一个算子 + 一份数据（§2.2）。"""

    id: str = Field(min_length=1, max_length=120)
    op: str = Field(min_length=1, max_length=24)
    kind: str = Field(default="", max_length=64)
    label: str = Field(default="", max_length=120)
    target: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list, max_length=200)
    origin: Literal["plan", "emergent"] = "plan"
    status: PlanStatus = "pending"
    run: ItemRun = Field(default_factory=ItemRun)

    @model_validator(mode="after")
    def op_is_in_closed_set(self) -> "PlanItem":
        if self.op not in OPS:
            raise ValueError(f"op 必须在闭集内 {OPS}，收到 {self.op!r}")
        return self

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def is_runnable(self) -> bool:
        return self.status in {"pending", "ready"}

    @property
    def is_batch_merge(self) -> bool:
        """批次合并：只把一组分片并进蓝图，不删不改（§3.3）。"""

        return self.op == "merge" and self.params.get("scope") == "batch"

    @property
    def is_final_merge(self) -> bool:
        """收尾合并：``merge`` 里除批次合并之外的都算。

        旧计划（展开规则改之前）的 ``merge`` 没有写 scope，语义就是收尾归一，
        所以这里的默认值取"是"——判断错一边会把批次合并当成有删除权的那一个。
        """

        return self.op == "merge" and not self.is_batch_merge


class PlanKindStrategy(PlanModel):
    """某个构件类型的本轮策略（模型产出，程序归一化）。

    ``subtype`` / ``guidance`` 只做**提示**：坐标与数量永远由设计清单与骨架给定，
    模型不许在策略里写几何（§3.2）。
    """

    kind: str = Field(min_length=1, max_length=64)
    subtype: str = Field(default="", max_length=64)
    guidance: str = Field(default="", max_length=300)
    reason: str = Field(default="", max_length=300)
    execution_mode: Literal["serial", "parallel"] = "serial"
    parallel_group: str = Field(default="", max_length=64)
    batch_reason: str = Field(default="", max_length=300)


class PlanStrategy(PlanModel):
    """模型给出的构件与批次策略；程序负责校验并展开为合法条目。"""

    kinds: list[PlanKindStrategy] = Field(default_factory=list, max_length=40)
    detail_level: str | None = None
    notes: str = Field(default="", max_length=500)
    source: Literal["llm", "deterministic", "fallback"] = "deterministic"


class PlanHistoryEntry(PlanModel):
    """一轮追加/失效条目的摘要，供前端与审计使用。"""

    revision: int = Field(ge=1)
    action: str = Field(min_length=1, max_length=64)
    item_ids: list[str] = Field(default_factory=list, max_length=200)
    reason: str = Field(default="", max_length=500)


class PlanDocument(PlanModel):
    """存进 ``state.plan`` 的整份计划（§2.2）。"""

    schema_version: Literal["plan/1.0"] = PLAN_SCHEMA_VERSION
    revision: int = Field(default=1, ge=1)
    detail_level: Literal["minimal", "simple", "standard", "detailed"] = "standard"
    budget: dict[str, int] = Field(default_factory=dict)
    items: list[PlanItem] = Field(default_factory=list, max_length=200)
    history: list[PlanHistoryEntry] = Field(default_factory=list, max_length=50)
    # ── 循环控制计数（§5.4：五重有界终止条件）──
    iterations: int = Field(default=0, ge=0)
    no_progress_rounds: int = Field(default=0, ge=0)
    last_progress_signature: str = Field(default="", max_length=200)
    #: replanner 主动放弃（§5.3 的 ``give_up``）：带警告交付，而不是把整轮判死。
    give_up: bool = False
    #: 本次运行已发生的模型调用次数（用于 §5.4 的预算判定）。
    #: 由节点在真实发起模型调用的地方累加——**估算值**，工具循环的每一轮各计一次。
    llm_calls: int = Field(default=0, ge=0)

    def add_llm_calls(self, count: int = 1) -> "PlanDocument":
        """累加模型调用计数（唯一入口，便于日后换成精确计费）。"""

        self.llm_calls += max(0, int(count))
        return self

    def llm_budget_exhausted(self) -> bool:
        limit = int((self.budget or {}).get("llm_calls", 0) or 0)
        return bool(limit) and self.llm_calls >= limit

    def item(self, item_id: str) -> PlanItem | None:
        for candidate in self.items:
            if candidate.id == item_id:
                return candidate
        return None

    def items_by_op(self, op: str) -> list[PlanItem]:
        return [item for item in self.items if item.op == op]

    def terminal_ids(self) -> set[str]:
        return {item.id for item in self.items if item.is_terminal}

    def progress_signature(self) -> str:
        """业务进展签名；重试次数增加本身不算进展。"""

        snapshot = json.dumps(
            [
                {
                    "id": item.id,
                    "status": item.status,
                    "run_state": item.run.state,
                    "artifacts": item.run.artifacts,
                    "params": item.params,
                }
                for item in self.items
            ],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(snapshot.encode("utf-8")).hexdigest()
