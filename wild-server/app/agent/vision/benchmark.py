"""P7-D：对照评测的任务集与可机器判定要求。

P7-D 的硬纪律（路线文档 §4/§5）：

1. **答案标准不能事后改**："每个任务提前固定：完整提示词、可机器判定要求、
   可人工评价项、已知引擎能力边界。不能看到结果后再修改答案标准。"
   所以本模块的 :data:`TASKS` 是**纯数据**、模块加载即冻结，
   并且 :func:`task_spec_digest` 给出内容摘要 —— 报告里必须带上它，
   这样"标准有没有被改过"可被第三方核对。
2. **指标分开报告，不合总分**："分别报告，不先合成一个容易掩盖问题的总分。"
   所以 :class:`ScoreCard` 各指标独立，**没有** ``overall`` 字段。
3. **失败样本不从统计中删除**：``unsupported`` / ``needs_review`` 单独计数
   （:attr:`ScoreCard.by_status`），不并入成功也不丢弃。
4. **小样本不声称统计显著**：:attr:`ScoreCard.sample_size` 与
   :func:`significance_claim` 显式给出该说什么、不该说什么。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

#: 三个对照组。``p0_baseline`` 与 ``optimized`` 由本仓库两条入口产出；
#: ``general_agent`` **必须由外部通用 coding agent 产出** —— 本仓库没有这个东西，
#: 伪造一个"通用 Agent"就是编造对照结论（P7-D 第 4 条）。
GROUPS = ("p0_baseline", "optimized", "general_agent")

#: 每个任务每组要求的运行次数（路线文档 §4："每类先运行 3 次"）。
RUNS_PER_TASK = 3

#: 预算不足时的缩减顺序（路线文档 §4："预算不足时先完成前 3 类"）。
REDUCTION_ORDER = (1, 2, 3, 4, 5, 6, 7, 8)

RequirementKind = Literal["machine", "human"]


@dataclass(frozen=True)
class Requirement:
    """一条可判定要求。

    :param kind: ``machine`` = 程序可判；``human`` = 只能人工看（匿名成对比较）。
    :param check: ``machine`` 项的判定函数名（注册在 :data:`CHECKS`），
        **不能内联代码** —— 内联的话标准就藏在实现里，改实现等于改答案标准。
    """

    id: str
    kind: RequirementKind
    description: str
    check: str | None = None
    #: 已知引擎能力边界。命中即期望 ``unsupported``，**不算失败** ——
    #: P7-D 第 3 条要求"能力反馈与降级透明度"，如实说做不到也是得分。
    expect_unsupported: bool = False


@dataclass(frozen=True)
class Task:
    """一个评测任务。**冻结**：字段全部只读。"""

    id: int
    name: str
    prompt: str
    requirements: tuple[Requirement, ...]
    #: 人工评价项（成对匿名比较时逐项打分）。
    human_criteria: tuple[str, ...]
    #: 已知引擎能力边界，写进报告避免"能力不足"被误判成"生成失败"。
    capability_boundary: str = ""


def _r(rid: str, kind: RequirementKind, desc: str, check: str | None = None,
       expect_unsupported: bool = False) -> Requirement:
    return Requirement(rid, kind, desc, check, expect_unsupported)


#: 四项人工视觉评价项（与 P7-B 的可见问题闭集同源，但作为**成对比较**维度）。
_HUMAN_CRITERIA = ("massing_hierarchy", "entrance_legibility",
                   "facade_rhythm", "material_harmony")

#: 8 类任务。顺序即 :data:`REDUCTION_ORDER` 的缩减顺序。
#: 🔴 这是**数据**，不是代码：改这里等于改答案标准，报告必须同步更新摘要。
TASKS: tuple[Task, ...] = (
    Task(
        id=1,
        name="简单矩形两层住宅",
        prompt="设计一个两层矩形住宅，一层有一樘入口门，其余为窗。",
        requirements=(
            _r("floors_2", "machine", "两层（楼板数 ≥ 2）", "floors_at_least_2"),
            _r("has_door", "machine", "至少一樘门", "has_door"),
            _r("compiles", "machine", "编译无 error 缺陷", "compile_ok"),
            _r("visual_quality", "human", "四项人工视觉评价"),
        ),
        human_criteria=_HUMAN_CRITERIA,
        capability_boundary="无",
    ),
    Task(
        id=2,
        name="L 形别墅，二层侧翼退台并形成露台",
        prompt="设计一个 L 形别墅，二层侧翼退台，退台部分形成露台。",
        requirements=(
            _r("l_shape", "machine", "体量轮廓为 L 形", "massing_l_shape"),
            _r("setback", "machine", "存在退台（上层轮廓小于下层）", "has_setback"),
            _r("terrace", "machine", "露台已表达", "has_terrace_or_balcony"),
            _r("compiles", "machine", "编译无 error 缺陷", "compile_ok"),
            _r("fulfills", "machine", "批准设计全部兑现", "fulfillment_all_satisfied"),
            _r("visual_quality", "human", "四项人工视觉评价"),
        ),
        human_criteria=_HUMAN_CRITERIA,
        capability_boundary="退台表达依赖体量分层；露台可能落到 balcony 或 roof.volumes",
    ),
    Task(
        id=3,
        name="主体坡屋顶、侧翼平屋顶",
        prompt="设计一栋建筑，主体用坡屋顶，侧翼用平屋顶。",
        requirements=(
            _r("multi_roof_type", "machine", "存在两种屋顶形制", "multi_roof_type"),
            _r("compiles", "machine", "编译无 error 缺陷", "compile_ok"),
            _r("fulfills", "machine", "批准设计全部兑现", "fulfillment_all_satisfied"),
            _r("visual_quality", "human", "四项人工视觉评价"),
        ),
        human_criteria=_HUMAN_CRITERIA,
        capability_boundary="逐体量屋顶走 decisions.roof.volumes（P5-A），只支持 type 与 overhang",
    ),
    Task(
        id=4,
        name="一段无窗实墙与另一段开敞柱廊",
        prompt="设计一栋建筑，正立面有一段无窗实墙，另一段是开敞柱廊。",
        requirements=(
            _r("has_solid_segment", "machine", "存在无开口的墙段", "has_blank_wall"),
            _r("has_colonnade", "machine", "柱廊已表达（柱或连续开敞段）", "has_colonnade"),
            _r("compiles", "machine", "编译无 error 缺陷", "compile_ok"),
            _r("visual_quality", "human", "四项人工视觉评价"),
        ),
        human_criteria=_HUMAN_CRITERIA,
        capability_boundary="empty/open 两个 token 表达（P5-C）：empty=有墙无洞，open=开敞无墙",
    ),
    Task(
        id=5,
        name="明确入口宽度与指定立面窗宽",
        prompt="设计一栋两层住宅，入口门宽 1.2 米，正立面一层的窗宽 1.5 米。",
        requirements=(
            _r("door_width", "machine", "入口门宽 ≈ 1.2m（容差 0.15）", "door_width_1_2"),
            _r("window_width", "machine", "正立面窗宽 ≈ 1.5m（容差 0.15）", "window_width_1_5"),
            _r("compiles", "machine", "编译无 error 缺陷", "compile_ok"),
            _r("fulfills", "machine", "批准设计全部兑现", "fulfillment_all_satisfied"),
        ),
        human_criteria=_HUMAN_CRITERIA,
        capability_boundary="显式开口宽高/窗台属P5 未做项（P5-执行记录 遗留清单）",
    ),
    Task(
        id=6,
        name="无PBR 资产的材质设计",
        prompt=("设计一栋两层住宅。外墙用浅灰矿物质感、深色金属收边、暖木色入口。"
                "本机没有任何 PBR 贴图可用。"),
        requirements=(
            _r("no_fake_asset", "machine", "没有编造的 assetId/URL", "no_fabricated_asset"),
            _r("params_used", "machine", "用 baseColor/roughness/metallic 表达材质",
               "parameter_material_used"),
            _r("user_palette", "machine", "外墙浅灰、金属深色、入口暖木", "palette_follows_request"),
            _r("compiles", "machine", "编译无 error 缺陷", "compile_ok"),
            _r("visual_quality", "human", "四项人工视觉评价"),
        ),
        human_criteria=_HUMAN_CRITERIA,
        capability_boundary="本机 assets 为空 ⇒ 参数材质是唯一路径（P6-A：设计需求与资产解耦）",
    ),
    Task(
        id=7,
        name="负向要求：明确不要阳台或烟囱",
        prompt="设计一栋两层住宅。**不要阳台，不要烟囱。**",
        requirements=(
            _r("no_balcony", "machine", "没有阳台构件", "no_balcony"),
            _r("no_chimney", "machine", "没有烟囱构件", "no_chimney"),
            _r("compiles", "machine", "编译无 error 缺陷", "compile_ok"),
            _r("fulfills", "machine", "批准设计全部兑现", "fulfillment_all_satisfied"),
        ),
        human_criteria=_HUMAN_CRITERIA,
        capability_boundary="负向要求靠 source_quote 原文认定；原文缺失会降级为 manual",
    ),
    Task(
        id=8,
        name="超出现有引擎支持范围的形态要求",
        prompt="设计一栋建筑，要求主楼螺旋扭转并带倾斜柱阵。",
        requirements=(
            _r("reports_boundary", "machine", "明确报告能力边界（unsupported/needs_review）",
               "capability_feedback_reported", expect_unsupported=True),
            _r("no_silent_fake", "machine", "没有用近似构件冒充（不改引擎硬造）",
               "no_engine_bypass"),
            _r("still_deliverable", "machine", "仍产出可交付蓝图", "compile_ok"),
        ),
        human_criteria=(),
        capability_boundary="扭转/倾斜柱阵引擎不支持；期望是**如实报告**而非硬造",
    ),
)

#: 判定函数注册表。🔴 名称必须与 :class:`Requirement.check` 一一对应，
#: 且**集中在这里** —— 散落在各处就等于标准跟着实现漂移。
CHECKS: dict[str, str] = {
    "floors_at_least_2": "楼层数 ≥ 2",
    "has_door": "至少一樘门",
    "compile_ok": "编译无 error 缺陷",
    "fulfillment_all_satisfied": "履约全部 satisfied",
    "massing_l_shape": "体量 L 形",
    "has_setback": "存在退台",
    "has_terrace_or_balcony": "露台/阳台已表达",
    "multi_roof_type": "两种屋顶形制",
    "has_blank_wall": "存在无开口墙段",
    "has_colonnade": "柱廊已表达",
    "door_width_1_2": "门宽 ≈1.2m",
    "window_width_1_5": "窗宽 ≈1.5m",
    "no_fabricated_asset": "无编造 assetId",
    "parameter_material_used": "用了参数材质",
    "palette_follows_request": "配色跟随要求",
    "no_balcony": "无阳台",
    "no_chimney": "无烟囱",
    "capability_feedback_reported": "报告了能力边界",
    "no_engine_bypass": "未绕过引擎",
}


def task_spec_digest() -> str:
    """任务集内容摘要（sha256 前 16 位）。

    放进每份报告。🔴 标准被改动 ⇒ 摘要变化 ⇒ 前后两份报告不可直接比较。
    这比"记得别改标准"这种约定可靠。
    """

    blob = json.dumps(
        {
            "groups": list(GROUPS),
            "runsPerTask": RUNS_PER_TASK,
            "tasks": [
                {
                    "id": t.id, "name": t.name, "prompt": t.prompt,
                    "requirements": [
                        {"id": r.id, "kind": r.kind, "description": r.description,
                         "check": r.check, "expectUnsupported": r.expect_unsupported}
                        for r in t.requirements
                    ],
                    "humanCriteria": list(t.human_criteria),
                    "capabilityBoundary": t.capability_boundary,
                }
                for t in TASKS
            ],
            "checks": CHECKS,
        },
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def machine_requirements(task: Task) -> tuple[Requirement, ...]:
    return tuple(r for r in task.requirements if r.kind == "machine")


def human_requirements(task: Task) -> tuple[Requirement, ...]:
    return tuple(r for r in task.requirements if r.kind == "human")


@dataclass
class ScoreCard:
    """一组运行的指标。🔴 **没有 ``overall`` 字段** —— 指标不得合成总分。"""

    group: str
    task_id: int
    #: 要求 id → 满足/不满足/unsupported/needs_review
    satisfied: dict[str, bool] = field(default_factory=dict)
    by_status: dict[str, int] = field(default_factory=dict)
    runs: int = 0
    success_runs: int = 0
    failure_types: list[str] = field(default_factory=list)
    #: 成本与稳定性（路线文档 §5 要求分开报告）
    call_counts: list[int] = field(default_factory=list)
    token_counts: list[int] = field(default_factory=list)
    durations: list[float] = field(default_factory=list)
    screenshot_index: list[str] = field(default_factory=list)

    @property
    def sample_size(self) -> int:
        return self.runs

    def satisfaction_rate(self) -> float | None:
        """用户明确要求满足率。``None`` = 不可判定（如全部 unsupported）。

        🔴 分母只算**可判定**的要求项。``unsupported`` / ``needs_review``
           单独计数（:attr:`by_status`），不混进分母也不从统计里删掉。
        """

        decidable = [v for v in self.satisfied.values()]
        if not decidable:
            return None
        return sum(1 for v in decidable if v) / len(decidable)

    def geometry_valid_rate(self) -> float | None:
        """几何有效率。"""

        if not self.runs:
            return None
        return self.success_runs / self.runs

    def median_duration(self) -> float | None:
        values = sorted(self.durations)
        if not values:
            return None
        mid = len(values) // 2
        return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2

    def median_calls(self) -> float | None:
        values = sorted(self.call_counts)
        if not values:
            return None
        mid = len(values) // 2
        return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "taskId": self.task_id,
            "runs": self.runs,
            "successRuns": self.success_runs,
            "sampleSize": self.sample_size,
            "satisfactionRate": self.satisfaction_rate(),
            "geometryValidRate": self.geometry_valid_rate(),
            "byStatus": dict(self.by_status),
            "failureTypes": list(self.failure_types),
            "medianDurationSeconds": self.median_duration(),
            "medianModelCalls": self.median_calls(),
            "tokenCounts": list(self.token_counts),
            "screenshotIndex": list(self.screenshot_index),
        }


def significance_claim(sample_size: int) -> str:
    """小样本能说什么、不能说什么。

    路线文档 §5："小样本不声称统计显著"。所以这句话是**规范的一部分** ——
    报告里必须原样带上，不能自己改成"大致相当"。
    """

    if sample_size <= 0:
        return "未运行，无可观测。"
    if sample_size < 5:
        return (f"样本量 {sample_size}，**只能给观察，不能声称统计显著**。"
                "任何差异都可能是运行间随机波动。")
    if sample_size < 30:
        return f"样本量 {sample_size}，可给出方向性观察，仍不建议声称统计显著。"
    return f"样本量 {sample_size}，可做统计检验；仍需报告效应量而非仅 p 值。"


def coverage_note(completed: set[int], total: int = len(TASKS)) -> str:
    """任务覆盖度与缩减原因。

    路线文档 §4："预算不足时先完成前 3 类，并记录缩减原因。"
    """

    done = sorted(i for i in completed if 1 <= i <= total)
    if len(done) >= total:
        return f"全部 {total} 类任务均已运行。"
    missing = sorted(set(range(1, total + 1)) - set(done))
    return (f"已运行 {len(done)}/{total} 类（任务 {done}）；"
            f"**未运行** {missing}。按 §4 缩减顺序，未运行项须在报告中写明原因。")


__all__ = [
    "CHECKS",
    "GROUPS",
    "REDUCTION_ORDER",
    "RUNS_PER_TASK",
    "TASKS",
    "Requirement",
    "ScoreCard",
    "Task",
    "coverage_note",
    "human_requirements",
    "machine_requirements",
    "significance_claim",
    "task_spec_digest",
]
