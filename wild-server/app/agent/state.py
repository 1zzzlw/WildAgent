"""LangGraph State 定义。

所有节点通过这个 State 通信，并由 LangGraph checkpointer 持久化可序列化字段。

"""

from typing import Annotated, Any, NotRequired, TypedDict


def merge_state_mapping(left: dict | None, right: dict | None) -> dict:
    """合并分片映射的**局部更新**。

    ``execute`` 可以并发返回互不依赖的构件类型，``repair/state_updates.py`` 也会按
    构件类型回写**部分**键；没有 reducer 时，任一局部更新都会覆盖其它类型的分片。
    """
    merged = dict(left or {})
    merged.update(right or {})
    return merged


class GenerationInput(TypedDict):
    """图的公开输入契约；其余 GenerationState 字段只能由节点产生。"""

    user_message: str  # 用户本轮输入的自然语言需求。
    request_id: NotRequired[str]  # 本次生成任务 ID，用于日志、事件和 checkpoint 定位。
    session_id: NotRequired[str]  # 会话 ID，用于关联设计文档和多轮交互。
    building_type: NotRequired[str]  # 入口预识别的建筑类型，例如 villa、office。
    current_blueprint: NotRequired[dict | None]  # 编辑模式下已有的 .wild Blueprint；新建时为空。
    selection: NotRequired[list[str]]  # 前端当前选中的 Blueprint 元素 ID 列表。
    recent_messages: NotRequired[list[dict]]  # 供意图分类参考的近期对话消息。
    workflow_state: NotRequired[str]  # 前端当前工作流状态，例如 idle、generating。
    thinking_mode: NotRequired[bool]  # 是否开启模型深度思考及 reasoning 流式展示。
    procedural_materials_enabled: NotRequired[bool]  # 是否允许使用程序化材质方案。


# total=False 当前类里定义的所有字段默认全部可选，可以缺省。
class GenerationState(TypedDict, total=False):
    """LangGraph 生成流程的完整状态"""

    # ── 输入 ──
    user_message: str  # 用户本轮输入的自然语言需求。
    request_id: str  # 本次生成任务 ID，用于串联日志、事件与 checkpoint。
    building_type: str  # 当前识别或指定的建筑类型。
    session_id: str  # 当前会话 ID，用于关联设计文档和多轮任务。
    style_preference: list[str]  # 分类器规则预选的候选风格 id，供早期节点约束方向
    current_blueprint: dict | None  # 编辑模式使用的现有 .wild Blueprint；新建时为空。
    selection: list[str]  # 前端当前选中的 Blueprint 元素 ID 列表。
    recent_messages: list[dict]  # 供意图分类和上下文判断使用的近期对话。
    workflow_state: str  # 前端传入的工作流状态，例如 idle、generating。
    thinking_mode: bool  # 是否启用模型深度思考和 reasoning 流式展示。
    procedural_materials_enabled: bool  # 是否允许生成程序化材质。

    # ── Layer -1: 意图分类 ──
    intent: str  # "generate" | "edit" | "chat"
    intent_confidence: float  # 意图分类置信度，范围为 0～1。
    intent_target: str  # 从用户消息中识别出的操作对象，例如"别墅"或"正门"。
    intent_target_kind: str  # "architecture" | "object"：本轮交付的是建筑方案还是单个物件。
    intent_requires_scene: bool  # 当前意图是否必须依赖已有 Blueprint 场景。
    intent_reason: str  # 分类器给出的简短、可展示判断理由。
    intent_source: str  # 分类结果来源，例如 rule、llm 或 fallback。

    # ── plan：动态执行计划──
    plan: dict  # PlanDocument：条目列表 + revision + 预算 + 有界终止计数。
    plan_events: list[dict]  # 本轮条目状态变化的增量事件，供前端进度面板累加消费。
    current_item_id: str | None  # 本轮正在执行的条目 id，trace 与事件的挂载点。
    tool_trace: dict  # {item_id: [{tool, ok, chars}]}：条目的工具/检索审计轨迹。

    # ── Layer -0.5: 建筑方案（生成分支）──
    architecture_plan: dict  # 归一化后的总体建筑方案，供后续节点执行。
    architecture_diag: dict  # 总体方案来源、RAG 和模型调用诊断（前端方案摘要消费）。
    design_document: dict  # 可人工审核、带 revision 的结构化建筑设计文档。
    resolved_design: dict  # 将 DesignDocument 默认值和引用解析后的可执行视图。
    design_review_status: str  # 建筑设计审核状态，例如 pending、approved、revise。
    design_feedback: str  # 用户对当前建筑设计提出的修改意见。
    design_material_refresh: bool  # 本轮修订后是否需要重新生成材质方案。
    material_plan: dict  # 材质角色、颜色和资产引用组成的受控材质方案。
    material_diag: dict  # 材质检索、解析、校验和回退诊断（前端资产摘要消费）。

    # ── Layer -1: 知识问答输出 ──
    chat_reply: str       # 知识问答的文本回复
    chat_diag: dict       # 知识问答的诊断数据

    # ── Layer -1: 增量修改输出 ──
    scene_patch: dict  # 编辑模式生成并校验后的 ScenePatch 操作集合。
    patch_reply: str  # 返回给用户的修改结果说明。
    patch_diag: dict  # ScenePatch 模型调用、解析和校验诊断。

    # ── Layer 0: 骨架 ──
    skeleton_blueprint: dict  # skeleton 节点生成的主体 Blueprint，尚未合并组件分片。
    skeleton_summary: str  # 主体骨架生成结果的简短说明。
    wall_bounding_box: dict  # 主体墙体的空间包围盒，供组件放置和校验参考。
    spatial_invariants: dict  # 从主体提取的楼层、边界、宿主等空间不变量。
    suggested_components: list[str]  # 骨架节点建议的组件列表
    design_brief: dict  # 骨架输出的设计清单（facade_plan + component_quota + rag_reference）
    skeleton_diag: dict  # 主体骨架模型调用、解析、恢复和校验诊断。

    # ── Layer 1: 组件分片 ──
    component_fragments: Annotated[dict[str, Any], merge_state_mapping]  # 各构件类型的源分片映射。
    component_diagnostics: Annotated[dict[str, dict], merge_state_mapping]  # 生成与校验的诊断映射。

    # ── Layer 2: 合并与校验 ──
    merged_blueprint: dict  # 主体骨架与所有组件分片合并后的 Blueprint。
    merge_diag: dict  # 合并诊断：批次合并只有并入计数，收尾合并才带校验→修复循环与蓝图指纹
    validation_results: list[dict]  # 各校验器返回的原始结果列表。
    validation_issues: list[dict]  # 汇总后的结构化错误与警告列表。
    validation_error_count: int  # 当前阻断级校验错误数量。
    validation_warning_count: int  # 当前非阻断级校验警告数量。
    validation_cache_reused: bool  # final_validate 是否复用了 callback 已完成的校验快照。
    validation_snapshot: dict  # ValidationSnapshot 的 dict 形式，供 callback→final_validate 复用
    failed_components: list[dict]  # 校验失败且可能进入定向修复的组件信息。
    passed_component_ids: list[str]  # 已通过校验、修复时应尽量保持不变的组件 ID。
    retry_count: int  # 已执行的修复轮次，仅用于审计/展示
    max_retries: int  # 每个失败目标允许的最大修复次数
    component_retry_counts: dict[str, int]  # per-component 重试计数 {component_id: count}

    # ── 回调上下文 ──
    repair_audit: dict  # 修复前后错误变化、接受或拒绝原因等审计记录。
    terminal_model_error: dict  # 模型服务故障；当前图运行必须终止，不进入建筑修复循环

    # ── 最终输出 ──
    final_blueprint: dict  # 通过最终校验、可交付给前端的 .wild Blueprint。
    error: str | None  # 当前任务的终止错误；正常完成时为空。
    status: str  # "complete" | "partial" | "failed"
