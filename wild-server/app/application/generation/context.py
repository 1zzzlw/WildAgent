"""一次生成执行的临时上下文，进度数据与持久化图状态分离。"""
from dataclasses import dataclass, field
from typing import Any
from app.application.generation.events import EventSink
from app.application.generation.events import _emit_agent_step
from app.application.generation.events import _emit_debug_log
from app.application.generation.events import _emit_thinking_delta
from app.application.generation.events import _emit_thinking_status
from app.application.generation.progress import _public_node_name
from app.application.generation.progress import _thinking_channel


@dataclass
class GenerationExecution:
    sink: EventSink
    data: dict
    request_id: str = ""
    session_id: str = ""
    message: str = ""
    current_blueprint: dict | None = None
    selection: list[str] = field(default_factory=list)
    detail_level: str = "minimal"
    thinking_mode: bool = False
    initial_state: dict = field(default_factory=dict)
    component_configs: dict = field(default_factory=dict)
    graph_config: dict = field(default_factory=dict)
    all_diags: dict = field(default_factory=dict)
    final_state: dict | None = None
    resolved_intent: str | None = None
    node_outputs: dict = field(default_factory=dict)
    total_tokens: dict = field(default_factory=dict)
    node_starts: dict = field(default_factory=dict)
    node_started_isos: dict = field(default_factory=dict)
    suggested_components: list = field(default_factory=list)
    observed_state: dict = field(default_factory=dict)
    retained_blueprint: dict | None = None
    execution_error: str | None = None
    graph: Any = None

    async def send_step(self,
        stage: str,
        node: str,
        status: str,
        label: str,
        detail: str,
    ):
        await _emit_agent_step(
            self.sink, self.request_id, self.session_id,
            stage=stage, node=node, status=status, label=label, detail=detail,
        )


    async def send_debug(self, category: str, data_obj: dict):
        await _emit_debug_log(
            self.sink, self.request_id, self.session_id, category=category, data=data_obj,
        )


    async def send_thinking_delta(self, node_name: str, delta: str):
        """实时推送节点的思考内容给前端（带节点标识）。通道判据见 :func:`_thinking_channel`。"""
        await _emit_thinking_delta(
            self.sink,
            self.request_id,
            self.session_id,
            node=_public_node_name(node_name),
            channel=_thinking_channel(node_name),
            delta=delta,
        )


    async def send_thinking_status(self, status: str, content: str = ''):
        await _emit_thinking_status(
            self.sink, self.request_id, self.session_id, status=status, content=content,
        )

