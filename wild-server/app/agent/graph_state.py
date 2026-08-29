"""
LangGraph State 定义

所有节点通过这个 State 通信，并由 LangGraph checkpointer 持久化可序列化字段。
诊断字段均已声明，确保 LangGraph 不会丢弃 astream 中的诊断数据。
"""
from typing import Annotated, Any, TypedDict


def merge_state_mapping(left: dict | None, right: dict | None) -> dict:
    """合并并行组件节点写入的通用 State 映射。"""
    merged = dict(left or {})
    merged.update(right or {})
    return merged


class GenerationState(TypedDict, total=False):
    """LangGraph 生成流程的完整状态"""

    # ── 输入 ──
    user_message: str
    request_id: str
    building_type: str
    session_id: str
    style_preference: list[str]  # 分类器规则预选的候选风格 id，供早期节点约束方向
    current_blueprint: dict | None
    selection: list[str]
    recent_messages: list[dict]
    workflow_state: str
    thinking_mode: bool
    procedural_materials_enabled: bool
    plan_mode: bool

    # ── Claude 风格的可审核执行计划 ──
    execution_plan: dict
    execution_plan_status: str
    execution_plan_review_status: str
    execution_plan_validation: list[dict]
    execution_plan_history: list[dict]
    plan_feedback: str
    plan_research_context: str
    plan_research_summary: str
    plan_research_diag: dict

    # ── Plan 模式受控网络研究（本地覆盖不足时临时补充，不写入知识库）──
    research_queries: list[str]      # 缺失主题生成的研究问题
    research_missing_topics: list[str]  # 覆盖判断缺失的主题
    web_research_context: str        # 本次请求临时知识（仅当前 request 生效）
    web_research_diag: dict          # 搜索/命中/丢弃诊断
    execution_plan_diag: dict
    plan_replan_count: int
    max_plan_replans: int
    current_plan_step_id: str
    plan_next_node: str
    
    # ── Layer -1: 意图分类 ──
    intent: str  # "generate" | "edit" | "chat"
    intent_confidence: float
    intent_target: str
    intent_requires_scene: bool
    intent_reason: str
    intent_source: str

    # ── Layer -0.5: 建筑方案（生成分支）──
    architecture_plan: dict
    complexity_profile: dict
    architecture_diag: dict
    floor_plan_design_diag: dict
    floor_plan: dict
    floor_plan_svg: str
    floor_plan_svgs: dict[str, str]
    floor_plan_validation: list[dict]
    floor_plan_notice: str
    floor_plan_feedback: str
    floor_plan_revision: int
    floor_plan_auto_repair_count: int
    floor_plan_auto_repairing: bool
    floor_plan_review_status: str  # "pending" | "revise" | "approved"
    floor_plan_review_history: list[dict]
    material_plan: dict
    material_diag: dict

    # ── Layer -1: 知识问答输出 ──
    chat_reply: str       # 知识问答的文本回复
    chat_diag: dict       # 知识问答的诊断数据

    # ── Layer -1: 增量修改输出 ──
    scene_patch: dict
    patch_reply: str
    patch_diag: dict

    # ── Layer 0: 骨架 ──
    skeleton_blueprint: dict
    skeleton_summary: str
    wall_bounding_box: dict
    spatial_invariants: dict
    suggested_components: list[str]  # 骨架节点建议的组件列表
    design_brief: dict  # 骨架输出的设计清单（facade_plan + component_quota + rag_reference）
    body_gate_reports: list[dict]
    deterministic_body_complete: bool

    # ── Layer 0.5: 第二次风格确认与装饰装配 ──
    style_review_status: str  # "pending" | "revise" | "approved"
    style_package_id: str
    style_feedback: str
    style_revision: int
    decor_ir: dict
    style_gate_report: dict
    decor_diag: dict

    # ── Layer 1: 组件分片（并行）──
    # 以下 legacy 分片字段已不再写入，仅保留用于旧 checkpoint 的读侧兜底；
    # 权威数据在下面的 component_fragments / component_diagnostics。
    door_fragments: list[dict]
    window_fragments: list[dict]
    roof_fragment: dict | None
    railing_fragments: list[dict]
    canopy_fragments: list[dict]
    balcony_fragments: list[dict]
    ramp_fragments: list[dict]
    bay_window_fragments: list[dict]
    cornice_fragments: list[dict]
    chimney_fragments: list[dict]
    light_fragments: list[dict]

    # 新组件优先写入通用映射；上面的旧字段保留，兼容既有节点、测试和前端。
    component_fragments: Annotated[dict[str, Any], merge_state_mapping]
    component_diagnostics: Annotated[dict[str, dict], merge_state_mapping]

    # ── Layer 1 诊断字段（gen + val 分离）──
    skeleton_diag: dict
    door_gen_diag: dict
    door_val_diag: dict
    window_gen_diag: dict
    window_val_diag: dict
    roof_gen_diag: dict
    roof_val_diag: dict
    railing_gen_diag: dict
    railing_val_diag: dict
    canopy_gen_diag: dict
    canopy_val_diag: dict
    balcony_gen_diag: dict
    balcony_val_diag: dict
    light_gen_diag: dict
    light_val_diag: dict
    ramp_gen_diag: dict
    ramp_val_diag: dict
    bay_window_gen_diag: dict
    bay_window_val_diag: dict
    cornice_gen_diag: dict
    cornice_val_diag: dict
    chimney_gen_diag: dict
    chimney_val_diag: dict

    # ── Layer 2: 合并与校验 ──
    merged_blueprint: dict
    merge_diag: dict  # 合并节点的校验→修复循环诊断
    validation_results: list[dict]
    validation_issues: list[dict]
    validation_error_count: int
    validation_warning_count: int
    validation_cache_reused: bool
    validation_snapshot: dict  # ValidationSnapshot 的 dict 形式，供 callback→final_validate 复用
    failed_components: list[dict]
    passed_component_ids: list[str]
    retry_count: int  # 已执行的修复轮次，仅用于审计/展示
    max_retries: int  # 每个失败目标允许的最大修复次数
    component_retry_counts: dict[str, int]  # per-component 重试计数 {component_id: count}

    # ── 回调上下文 ──
    callback_context: dict
    repair_audit: dict
    terminal_model_error: dict  # 模型服务故障；当前图运行必须终止，不进入建筑修复循环

    # ── 最终输出 ──
    final_blueprint: dict
    error: str | None
    status: str  # "complete" | "partial" | "failed"
