"""ws 展示层对图节点的认知必须跟上图本身。

回归背景：编译器重构把建筑链的 ``skeleton`` 换成 ``compile``、加了
``design_convergence`` / ``object_design`` 节点，但 ``ws_agent`` 的
``_OUR_NODES`` 没跟上——新节点的事件在 astream 过滤处被静默 ``continue`` 吞掉，
前端管线展示直接"跳节点"（material_plan 之后直接 design_review / plan）。

三条守卫（图节点全集的事实源是 ``test_plan_graph.py::_EXPECTED_NODES``）：
1. 图上每个节点都能发事件（不在 _OUR_NODES 就会被吞）；
2. 每个可发事件的节点都有中文标签（缺了就给用户看英文裸名）；
3. 每个图节点都有 running 文案（缺了 ``if detail:`` 门会连"开始"事件都不发）。
"""

from app.agent.graph import build_generation_graph
from app.api.ws_agent import _NODE_LABELS, _NODE_START_DETAILS, _OUR_NODES


def _graph_nodes() -> set[str]:
    nodes = set(build_generation_graph().get_graph().nodes)
    nodes -= {"__start__", "__end__"}
    return nodes


def test_ws_agent_tracks_every_graph_node():
    """图上加节点必须同步 _OUR_NODES，否则事件被静默吞掉、前端跳节点。"""

    assert _graph_nodes() <= _OUR_NODES


def test_ws_agent_labels_cover_all_event_nodes():
    """可发事件的节点必须有中文标签，缺了用户看到的是英文裸名。"""

    assert _OUR_NODES <= set(_NODE_LABELS)


def test_ws_agent_start_details_cover_every_graph_node():
    """每个图节点都要有 running 文案；缺了连"节点开始"事件都不发。"""

    assert _graph_nodes() <= set(_NODE_START_DETAILS)


def test_optional_callback_node_still_reported():
    """callback 是按需加进图的可选节点，事件过滤集合里必须常驻。"""

    assert "callback" in _OUR_NODES
    assert "callback" in _NODE_START_DETAILS
