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

import ast
from pathlib import Path

from app.agent.graph import build_generation_graph
from app.api.ws_agent import (
    _NODE_LABELS,
    _NODE_START_DETAILS,
    _OUR_NODES,
    _design_schedule_note,
    _public_node_name,
    _thinking_channel,
)

#: `tests/api/` → `tests/` → `wild-server/`
_WS_AGENT_PATH = Path(__file__).resolve().parents[2] / "app" / "api" / "ws_agent.py"


def _graph_nodes() -> set[str]:
    nodes = set(build_generation_graph().get_graph().nodes)
    nodes -= {"__start__", "__end__"}
    return nodes


def _completion_branch_nodes() -> set[str]:
    """``on_chain_end`` 里显式处理过的节点名（AST 扫源码里的 ``node_name == "…"``）。

    这是**第四张展示表**，也是唯一一张不是数据结构、而是一条 ``if/elif`` 链的表，
    所以没有可断言的常量——只能从源码里取。

    它正是编译器重构漏掉的那张：``compile`` / ``design_convergence`` / ``object_design`` /
    ``replanner`` 当时**只补了前三张表**，于是这四个节点有 start 事件、没有 end 事件，
    前端步骤永远停在 running（转圈）。
    """

    tree = ast.parse(_WS_AGENT_PATH.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        left = node.left
        if not (isinstance(left, ast.Name) and left.id == "node_name"):
            continue
        for comparator in node.comparators:
            if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                names.add(comparator.value)
    return names


def test_every_graph_node_has_a_completion_branch():
    """图上每个节点都要有 on_chain_end 分支，否则该步骤永远停在 running。

    只补 ``_OUR_NODES`` / ``_NODE_LABELS`` / ``_NODE_START_DETAILS`` 是不够的：
    少了这条分支，节点会出现但永远不会变成"完成"——用户看到的是"卡住"而不是"跳节点"。
    """

    missing = _graph_nodes() - _completion_branch_nodes()
    assert not missing, (
        f"这些图节点只有开始事件、没有完成事件（前端步骤会一直转圈）: {sorted(missing)}"
    )


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


def test_thinking_channel_is_declared_per_delta_not_guessed_from_node():
    """思考通道靠**后缀表态**，不靠节点名白名单。

    回归背景：原先 `architecture` 在“一律 progress”的白名单里，于是它转发的**整段原始
    CoT** 被当成「执行说明」倒给用户（看起来像"循环思考"）。同一个节点既发进度句又发
    模型 token，按节点名**永远**分不开 —— 所以判据必须落到每一条上。
    """

    assert _thinking_channel("architecture") == "reasoning"
    assert _thinking_channel("architecture:progress") == "progress"
    assert _thinking_channel("plan") == "reasoning"
    assert _thinking_channel("merge:progress") == "progress"
    # 说错后缀就是「模型过程」，不会静默混进执行说明。
    assert _thinking_channel("architecture:reasons") == "reasoning"


def test_design_schedule_note_reports_batches_and_concurrency():
    """设计期的批次/并发必须能被读出来。

    只看产物分不出 "plan 参与了图纸" 没有：串行起草也能写出同一张图。这条口径
    让 UI 与审计都能看到"几批、同批几块"。
    """

    note = _design_schedule_note(
        {
            "plan": {
                "items": [
                    {"id": "draft_massing", "status": "done"},
                    {"id": "draft_facade", "status": "done"},
                    {"id": "draft_roof", "status": "abandoned"},
                ]
            },
            "batches": [
                {"items": ["draft_massing"]},
                {"items": ["draft_structure", "draft_facade", "draft_roof"]},
            ],
        }
    )
    assert "2 批" in note
    assert "最宽 3 并发" in note
    assert "落定 2/3 块" in note


def test_design_schedule_note_is_empty_without_a_design_plan():
    """没有设计期计划就不许编一个出来（老 checkpoint 与物件链都会走到这里）。"""

    assert _design_schedule_note(None) == ""
    assert _design_schedule_note({}) == ""
    assert _design_schedule_note({"plan": None, "batches": []}) == ""
    assert _design_schedule_note({"plan": {"items": []}, "batches": "不是列表"}) == ""


def test_thinking_channel_suffix_is_stripped_from_the_step_node():
    """后缀只表通道，不是步骤名 —— 剥掉后要挂回同一个步骤。"""

    assert _public_node_name("architecture:progress") == "architecture"
    assert _public_node_name("architecture") == "architecture"
    assert _public_node_name("skeleton:progress") == "skeleton"
