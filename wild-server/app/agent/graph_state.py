"""
LangGraph State 定义

所有节点通过这个 State 通信，只在内存中传递。
诊断字段均已声明，确保 LangGraph 不会丢弃 astream 中的诊断数据。
"""
from typing import TypedDict, Callable, Awaitable


class GenerationState(TypedDict, total=False):
    """LangGraph 生成流程的完整状态"""

    # ── 输入 ──
    user_message: str
    building_type: str
    session_id: str
    current_blueprint: dict | None
    selection: list[str]
    thinking_mode: bool
    
    # ── 流式思考回调（node_name, delta_text）──
    on_reasoning_delta: Callable[[str, str], Awaitable[None]] | None

    # ── Layer -1: 意图分类 ──
    intent: str  # "generate" | "edit" | "chat"

    # ── Layer -0.5: 建筑方案（生成分支）──
    architecture_plan: dict
    architecture_diag: dict

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

    # ── Layer 1: 组件分片（并行）──
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
    failed_components: list[dict]
    passed_component_ids: list[str]
    retry_count: int
    max_retries: int
    component_retry_counts: dict[str, int]  # per-component 重试计数 {component_id: count}

    # ── 回调上下文 ──
    callback_context: dict
    repair_audit: dict

    # ── 最终输出 ──
    final_blueprint: dict
    error: str | None
    status: str  # "complete" | "partial" | "failed"
