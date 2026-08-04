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
    thinking_mode: bool
    
    # ── 流式思考回调（node_name, delta_text）──
    on_reasoning_delta: Callable[[str, str], Awaitable[None]] | None

    # ── Layer 0: 骨架 ──
    skeleton_blueprint: dict
    skeleton_summary: str
    wall_bounding_box: dict
    suggested_components: list[str]  # 骨架节点建议的组件列表

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

    # ── Layer 1 诊断字段（必须在 State 中声明，否则 LangGraph 丢弃）──
    skeleton_diag: dict
    door_diag: dict
    window_diag: dict
    roof_diag: dict
    railing_diag: dict
    canopy_diag: dict
    balcony_diag: dict
    light_diag: dict
    ramp_diag: dict
    bay_window_diag: dict
    cornice_diag: dict
    chimney_diag: dict

    # ── Layer 2: 合并与校验 ──
    merged_blueprint: dict
    validation_results: list[dict]
    failed_components: list[dict]
    passed_component_ids: list[str]
    retry_count: int
    max_retries: int

    # ── 回调上下文 ──
    callback_context: dict

    # ── 最终输出 ──
    final_blueprint: dict
    error: str | None
    status: str  # "complete" | "partial" | "failed"
