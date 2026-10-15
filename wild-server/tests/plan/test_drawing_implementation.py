"""设计自由、逐步实现、组合构件和有证据舍弃的回归。"""
from copy import deepcopy
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.design.resolver import build_design_document, resolve_design, _stable_hash
from app.design.repository import DesignRepository
from app.design.markers import component_markers, assemble_marker_results, implementation_records
from app.agent.plan.expand import expand_design_markers
from app.agent.plan import implementation as impl


def test_stair_protocol_includes_platform_and_railing_before_first_generation():
    from app.agent.generation.capability import load_engine_schema

    protocol = impl._output_protocol(load_engine_schema(), {"stairs": {"type": "stair"}}, "", {})
    fields = json.loads(protocol.split("当前输出字段协议：", 1)[1])
    entities = {e["properties"]["type"]["const"]: e for e in fields["entities"]}
    assert {"stair", "floor", "railing"} <= entities.keys()
    assert "path" in entities["railing"]["required"]
    assert "parentWall" not in entities["railing"]["properties"]
    assert "thickness" in entities["floor"]["properties"]


def test_web_query_uses_design_name_without_repeating_markers_or_python_dicts():
    item = SimpleNamespace(kind="small_window", label="小窗")
    markers = {str(i): {"design": {"description": "小窗", "form": {"sill_height": 1.2}}} for i in range(8)}
    query = impl.web_reference_query(item, markers)
    assert query.startswith('"小窗"')
    assert query.count("小窗") == 1
    assert "small_window" not in query and "sill_height" not in query
    assert "详图" in query


@pytest.mark.parametrize("title,description,expected", [
    ("Small | Wiley", "Small nanoscience research journal", False),
    ("Windows Support", "Windows installation and repair", False),
    ("Yahoo! JAPAN", "Search news and sports", False),
    ("小窗构造详图", "建筑窗框安装节点", True),
    ("小窗", "小窗是某款应用", False),
])
def test_web_reference_requires_component_and_construction_context(title, description, expected):
    assert impl.relevant_web_reference({"title": title, "description": description},
                                      '"小窗" 建筑 构造 详图 installation detail drawing') is expected


def test_web_reference_does_not_confuse_window_with_windows():
    query = '"window" construction installation detail drawing'
    assert not impl.relevant_web_reference({"title": "Windows installation", "description": ""}, query)
    assert impl.relevant_web_reference({"title": "Casement window installation details", "description": ""}, query)


def run(coroutine):
    return asyncio.run(coroutine)


def drawing():
    return build_design_document({
        "concept": "自由设计", "massing": {"shape": "custom", "width": 10, "depth": 8,
            "floors": 1, "modeled_floors": 1, "floor_height": 3},
        "volumes": [{"id": "main", "x": 0, "z": 0, "width": 10, "depth": 8, "start_floor": 1, "end_floor": 1}],
        "structural_grid": {"system": "custom_frame", "x_bays": 2, "z_bays": 2},
        "facades": {f: {"bays": 1, "ground_pattern": ["empty"], "upper_pattern": ["door:custom"]}
                    for f in ("front", "back", "left", "right")},
        "roof": {"type": "wavy_custom", "curvature": 0.7}, "circulation": {"vertical_strategy": "none"},
        "components": [{"id": "lattice", "type": "custom_lattice", "host": "main",
            "description": "中式镂空装饰", "form": {"pattern": "自由曲线"}, "placement": {"position": [0, 3, 0]}}],
        "floor_layouts": [{"description": "扩展的平面布局"}],
    }, session_id="drawing_test", source_request="生成别墅")


def empty_state(document=None):
    document = document or drawing()
    resolved = resolve_design(document)
    return {"design_document": document.model_dump(mode="json"), "resolved_design": resolved.model_dump(mode="json"),
            "drawing_hosts": resolved.projection_elements,
            "skeleton_blueprint": {"meta": {"version": "1.1", "type": "building", "name": "test",
                    "designHash": _stable_hash(document), "designRevision": document.revision},
                "geometry": {"elements": [], "components": []}, "materials": {}, "assets": {}},
            "component_fragments": {}, "component_diagnostics": {}}


def box(entity_id="part"):
    return {"type": "primitive", "id": entity_id, "shape": "box", "position": [0, 0, 0],
            "dimensions": [1, 1, 1]}


def reply(marker_id, entities=None):
    return SimpleNamespace(content=json.dumps({"implementations": [{"id": marker_id,
        "geometry": {"elements": entities if entities is not None else [box()], "components": []},
        "explanation": "由真实元素组合实现"}]}), token_usage={})


def task(state, marker_id="lattice"):
    return next(i for i in expand_design_markers(state).items if marker_id in i.target["marker_ids"])


def patch_services(monkeypatch, outputs, *, shape_reference=True):
    import app.llm.client as client
    import app.llm.invocation as invocation
    import app.agent.plan.knowledge_tool as knowledge
    events = []
    async def model(*args, **kwargs):
        events.append("model")
        return outputs.pop(0)
    async def web(query):
        events.append("web")
        return [{"url": "https://example.com/component", "description": "形态资料"}]
    def rag(*args, **kwargs):
        events.append("rag")
        return {"text": "知识库示例", "has_shape_reference": shape_reference}
    monkeypatch.setattr(client, "create_llm", lambda **kwargs: None)
    monkeypatch.setattr(invocation, "invoke_llm", model)
    monkeypatch.setattr(knowledge, "search_knowledge_result", rag)
    monkeypatch.setattr(impl, "search_web_impl", web)
    return events


def test_invalid_json_keeps_decode_location_and_provider_finish_reason(monkeypatch):
    state = empty_state()
    invalid = '{"implementations":[{"id":"building_body","geometry":{"elements":[{"from":[15,0.45 + 0.12,13]}]}}]}'
    events = patch_services(monkeypatch, [SimpleNamespace(content=invalid, token_usage={}, finish_reason="stop")] * 3)
    updates, status, ids, message, trace = run(impl.run_marker_generate(state, task(state, "building_body")))
    assert status == "aborted" and ids == []
    assert "JSON 格式错误" in message and "第 1 行" in message and "0.45 + 0.12" in message
    assert events == ["rag", "model", "model", "model"]
    attempts = [t for t in trace if t["tool"] == "generate_wild"]
    assert all(t["finish_reason"] == "stop" and t["output"] == invalid for t in attempts)
    assert all("JSON 格式错误" in t["errors"]["building_body"] for t in attempts)
    assert updates["component_fragments"]["generate_1"] == []


@pytest.mark.parametrize("form", [{"description": "双跑楼梯与实体平台"}, "双跑楼梯与实体平台"])
def test_knowledge_query_includes_shape_description(monkeypatch, form):
    import app.agent.plan.knowledge_tool as knowledge
    state = empty_state()
    marker = next(m for m in state["resolved_design"]["component_markers"] if m["id"] == "lattice")
    marker["design"].update(description="二层连接组件", form=form)
    patch_services(monkeypatch, [reply("lattice")])
    queries = []
    def rag(query, **kwargs):
        queries.append(query)
        return {"text": "形态示例", "has_shape_reference": True}
    monkeypatch.setattr(knowledge, "search_knowledge_result", rag)
    updates, status, *_ = run(impl.run_marker_generate(state, task(state)))
    assert status == "succeeded"
    assert len(queries) == 1
    assert "二层连接组件" in queries[0] and "双跑楼梯与实体平台" in queries[0]


@pytest.mark.parametrize("kind,panel_field", [("door", "leafDepth"), ("window", "glassDepth")])
@pytest.mark.parametrize("frame_depth", [0.04, 0.12, None])
def test_panel_thicker_than_frame_is_rejected_before_component_compilation(kind, panel_field, frame_depth):
    base = empty_state()["skeleton_blueprint"]
    base["geometry"]["elements"] = [{"type": "wall", "id": "host", "from": [0, 0, 0],
        "to": [4, 3, 0], "thickness": 0.24}]
    frame = frame_depth if frame_depth is not None else 0.24
    panel = {"type": kind, "id": "panel", "parentWall": "host", "from": [1, 0.5, 0],
             "width": 1, "height": 2, panel_field: frame+0.01}
    if kind == "door":
        panel["interaction"] = {"mode": "swing", "hingeSide": "left", "openAngle": 75}
    if frame_depth is not None:
        panel["frameDepth"] = frame_depth
    marker = {"type": kind, "design": {}}
    row = {"geometry": {"elements": [], "components": [panel]}}
    with pytest.raises(ValueError, match=panel_field+".*frameDepth"):
        impl._accept_group(base, row, marker)
    panel[panel_field] = frame
    candidate, _, record = impl._accept_group(base, row, marker)
    assert record["status"] == "implemented"
    assert candidate["geometry"]["components"] == [panel]


def test_body_repair_receives_host_and_floor_coordinate_errors_together(monkeypatch):
    from app.design.contracts import ComponentInstance
    import app.llm.invocation as invocation
    document = drawing()
    document.decisions.components = [ComponentInstance(id="entry", type="door", host="wall_main_front_L1",
        size={"width": 1, "height": 2}, placement={"offset": 3})]
    state = empty_state(document)
    wall = {"id": "building_body_wall_main_front_L1", "type": "wall", "from": [0, 0, 0],
            "to": [10, 3, 0], "thickness": 0.24}
    wrong = {"id": "slab", "type": "floor", "from": [-5, -0.18, -4], "to": [5, -0.18, 4], "thickness": 0.18}
    outputs = [reply("building_body", [wrong, wall]), reply("building_body", [
        {**wrong, "from": [0, -0.18, 0], "to": [10, -0.18, 8]}, {**wall, "id": "wall_main_front_L1"}])]
    patch_services(monkeypatch, [])
    contexts = []
    async def model(_llm, messages):
        contexts.append(json.loads(messages[1]["content"]))
        return outputs.pop(0)
    monkeypatch.setattr(invocation, "invoke_llm", model)
    updates, status, ids, _, _ = run(impl.run_marker_generate(state, task(state, "building_body")))
    assert status == "succeeded" and set(ids) == {"slab", "wall_main_front_L1"}
    feedback = contexts[1]["validation_feedback"]["building_body"]
    assert "缺少真实墙" in feedback and "主体楼板超出" in feedback
    assert "X/Z" in feedback and "世界" in feedback
    assert implementation_records(updates)["building_body"]["status"] == "implemented"


@pytest.mark.parametrize("error_kind", ["truncated", "arithmetic"])
def test_invalid_json_feedback_is_not_misreported_as_a_missing_array(monkeypatch, error_kind):
    import app.llm.invocation as invocation
    state = empty_state()
    malformed = reply("lattice")
    malformed.content = (malformed.content[:-1] if error_kind == "truncated" else
                         malformed.content.replace("[0, 0, 0]", "[0, 0 + 3, 0]", 1))
    outputs = [malformed, reply("lattice")]
    patch_services(monkeypatch, [])
    contexts = []
    async def model(_llm, messages):
        contexts.append(json.loads(messages[1]["content"]))
        return outputs.pop(0)
    monkeypatch.setattr(invocation, "invoke_llm", model)
    _, status, _, _, _ = run(impl.run_marker_generate(state, task(state)))
    assert status == "succeeded"
    feedback = contexts[1]["validation_feedback"]["lattice"]
    assert "完整 JSON" in feedback and "必须是数组" not in feedback


@pytest.mark.parametrize("level", ["minimal", "simple", "standard", "detailed"])
@pytest.mark.parametrize("empty_bucket", ["elements", "components"])
def test_empty_geometry_object_is_normalized_without_another_model_call(monkeypatch, level, empty_bucket):
    state = empty_state()
    state["design_document"]["decisions"]["complexity"]["level"] = level
    output = reply("lattice")
    payload = json.loads(output.content)
    geometry = payload["implementations"][0]["geometry"]
    if empty_bucket == "elements":
        geometry["components"] = [{"id": "lattice_light", "type": "light", "position": [0, 2, 0]}]
    geometry[empty_bucket] = {}
    output.content = json.dumps(payload)
    original = output.content
    before = deepcopy(state)
    events = patch_services(monkeypatch, [output, output, output])
    updates, status, ids, _, trace = run(impl.run_marker_generate(state, task(state)))
    assert status == "succeeded" and len(ids) == 1
    assert events == ["rag", "model"]
    assert implementation_records(updates)["lattice"]["status"] == "implemented"
    assert state == before and output.content == original
    changes = next(t["format_changes"] for t in trace if t.get("stage") == "generate")
    assert changes == [{"path": f"/implementations/lattice/geometry/{empty_bucket}", "before": {}, "after": []}]
    assert not impl.implementation_errors(impl.implementation_blueprint({**state, **updates}))


@pytest.mark.parametrize("bucket", ["elements", "components"])
@pytest.mark.parametrize("invalid", [{"part": {"id": "part", "type": "primitive"}}, None, "[]", False])
def test_nonempty_or_invalid_geometry_container_is_not_discarded(monkeypatch, bucket, invalid):
    state = empty_state()
    output = reply("lattice")
    payload = json.loads(output.content)
    payload["implementations"][0]["geometry"][bucket] = invalid
    output.content = json.dumps(payload)
    original = output.content
    patch_services(monkeypatch, [output, output, output])
    updates, _, ids, _, trace = run(impl.run_marker_generate(state, task(state)))
    record = implementation_records(updates)["lattice"]
    assert record["status"] == "abandoned" and not ids
    assert f"/geometry/{bucket}" in record["reason"]
    assert not any(t.get("format_changes") for t in trace)
    assert output.content == original


@pytest.mark.parametrize("shape_reference,expected", [
    (True, ["rag", "model"]), (False, ["rag", "web", "model"]),
])
def test_reference_lookup_precedes_generation_and_web_is_only_for_a_shape_gap(monkeypatch, shape_reference, expected):
    state = empty_state()
    events = patch_services(monkeypatch, [reply("lattice")], shape_reference=shape_reference)
    updates, status, _, _, trace = run(impl.run_marker_generate(state, task(state)))
    assert events == expected
    assert status == "succeeded"
    assert implementation_records(updates)["lattice"]["status"] == "implemented"
    assert sum(t.get("model_calls", 0) for t in trace) == 1


def test_basic_native_shape_uses_model_knowledge_without_unnecessary_web(monkeypatch):
    state = empty_state()
    state["resolved_design"]["component_markers"] = [{
        "id": "plain_window", "type": "window", "host": "", "depends_on": [], "design": {}}]
    events = patch_services(monkeypatch, [reply("plain_window")], shape_reference=False)
    updates, status, _, _, _ = run(impl.run_marker_generate(state, task(state, "plain_window")))
    assert status == "succeeded" and events == ["rag", "model"]
    assert implementation_records(updates)["plain_window"]["status"] == "implemented"


def test_revision_preserves_valid_entities_and_sends_only_the_failed_fragment(monkeypatch):
    import app.llm.invocation as invocation
    state = empty_state()
    good, bad = box("stable_part"), {**box("bad_part"), "dimensions": [-1, 1, 1]}
    events = patch_services(monkeypatch, [])
    contexts = []
    async def model(_llm, messages):
        contexts.append(json.loads(messages[1]["content"]))
        return reply("lattice", [good, bad] if len(contexts) == 1 else [box("bad_part")])
    monkeypatch.setattr(invocation, "invoke_llm", model)
    updates, status, ids, _, trace = run(impl.run_marker_generate(state, task(state)))
    assert status == "succeeded" and set(ids) == {"stable_part", "bad_part"}
    assert events == ["rag"] and len(contexts) == 2
    repair = contexts[1]["failed_implementations"]["lattice"]
    assert [e["id"] for e in repair["geometry"]["elements"]] == ["bad_part"]
    assert contexts[1]["accepted_entity_ids"]["lattice"] == ["stable_part"]
    assert [e for e in updates["component_fragments"][task(state).id] if e["id"] == "stable_part"] == [good]
    assert sum(t.get("model_calls", 0) for t in trace) == 2


@pytest.mark.parametrize("origin", [(0, 0), (8, 8), (-12, 15)])
@pytest.mark.parametrize("revision", ["remove_extra", "keep_invalid", "partial_repeat", "change_adopted", "duplicate_repeat", "invalid_repeat"])
def test_body_revision_can_remove_rejected_extra_floor_without_losing_adopted_geometry(monkeypatch, origin, revision):
    document = drawing()
    x, z = origin
    document.decisions.volumes[0].x, document.decisions.volumes[0].z = x, z
    state = empty_state(document)
    original = deepcopy(state["design_document"])
    good = {"id": "interior", "type": "floor", "from": [x, -0.18, z],
            "to": [x+10, -0.18, z+8], "thickness": 0.18}
    stable = {**box("stable_structure"), "position": [x+1, 0.5, z+1]}
    bad = {**good, "id": "unrequested_extra", "from": [x-2, -0.18, z-2], "to": [x+12, -0.18, z+10]}
    revised = {
        "remove_extra": [good, stable], "keep_invalid": [good, stable, bad],
        "partial_repeat": [good], "change_adopted": [{**good, "thickness": 0.2}, stable],
        "duplicate_repeat": [good, stable, stable], "invalid_repeat": [good, {**stable, "dimensions": [True, 1, 1]}],
    }[revision]
    outputs = [reply("building_body", entities) for entities in ([good, stable, bad], revised, revised)]
    events = patch_services(monkeypatch, outputs)
    item = task(state, "building_body")
    updates, status, ids, _, trace = run(impl.run_marker_generate(state, item))
    record = implementation_records(updates)["building_body"]
    assert state["design_document"] == original
    if revision == "remove_extra":
        assert status == "succeeded" and record["status"] == "implemented"
        assert set(ids) == {"interior", "stable_structure"} and len(ids) == 2
        assert updates["component_fragments"][item.id] == [good, stable]
        assert events == ["rag", "model", "model"]
        assert trace[1]["errors"]["building_body"]
        assert trace[2]["errors"] == {}
    else:
        assert status == "aborted" and record["status"] == "abandoned" and not ids
        assert updates["component_fragments"][item.id] == []


def test_repeated_complete_body_is_rechecked_against_required_hosts(monkeypatch):
    patch_services(monkeypatch, [])
    state = empty_state()
    marker = state["resolved_design"]["component_markers"][0]
    stable = box("adopted")
    base = deepcopy(state["skeleton_blueprint"])
    base["geometry"]["elements"] = [stable]
    original = deepcopy(base)
    geometry = {"elements": [stable], "components": []}
    dependent = {"id": "required_window", "type": "window", "host": "wall_main_front_L1",
                 "design": {"size": {"width": 1, "height": 1}},
                 "diagram_host": next(w for w in state["drawing_hosts"] if w["id"] == "wall_main_front_L1"),
                 "entity": {"parentWall": "wall_main_front_L1", "from": [1, 1, 0]}}
    candidate, accepted, rejected, record = impl._accept_fragment(base,
        {"id": "building_body", "geometry": geometry}, marker, geometry, dependent_markers=[dependent])
    assert candidate == original and accepted is None and record is None
    assert "缺少真实墙" in rejected["error"]


def test_repeated_complete_fragment_still_checks_explicit_native_size(monkeypatch):
    patch_services(monkeypatch, [])
    state = empty_state()
    stable = {"id": "adopted_slab", "type": "floor", "from": [0, -0.18, 0],
              "to": [2, -0.18, 2], "thickness": 0.18}
    base = deepcopy(state["skeleton_blueprint"])
    base["geometry"]["elements"] = [stable]
    original = deepcopy(base)
    geometry = {"elements": [stable], "components": []}
    marker = {"id": "platform", "type": "floor", "host": "main", "design": {"size": {"thickness": 0.2}}, "entity": {}}
    candidate, accepted, rejected, record = impl._accept_fragment(base,
        {"id": "platform", "geometry": geometry}, marker, geometry)
    assert candidate == original and accepted is None and record is None
    assert "设计尺寸 thickness=0.2" in rejected["error"]


def test_body_does_not_fail_on_components_owned_by_other_plan_items(monkeypatch):
    state = empty_state()
    row = {"id": "building_body", "geometry": {"elements": [box("foundation")], "components": [
        {"id": "unrequested_window", "type": "window", "parentWall": "missing"}]}}
    events = patch_services(monkeypatch, [SimpleNamespace(content=json.dumps({"implementations": [row]}), token_usage={})])
    updates, status, ids, _, trace = run(impl.run_marker_generate(state, task(state, "building_body")))
    assert status == "succeeded" and ids == ["foundation"]
    assert events == ["rag", "model"]
    assert trace[1]["outside_item_entity_ids"] == ["unrequested_window"]
    assert implementation_records(updates)["building_body"]["status"] == "implemented"


def test_body_failure_stops_before_spending_calls_on_dependents(monkeypatch):
    from app.agent.graph import _after_execute
    state = empty_state()
    events = patch_services(monkeypatch, [reply("building_body", []) for _ in range(3)])
    updates, status, _, _, _ = run(impl.run_marker_generate(state, task(state, "building_body")))
    assert status == "aborted" and updates["status"] == "failed"
    assert "建筑主体" in updates["error"]
    assert _after_execute({**state, **updates}) == "__end__"
    assert events == ["rag", "model", "model", "model"]


@pytest.mark.parametrize("web_failure", ["empty", "error"])
def test_missing_web_reference_still_attempts_model_implementation(monkeypatch, web_failure):
    state = empty_state()
    events = patch_services(monkeypatch, [reply("lattice")], shape_reference=False)
    async def web(_query):
        events.append("web")
        if web_failure == "error":
            raise RuntimeError("网络不可用")
        return []
    monkeypatch.setattr(impl, "search_web_impl", web)
    updates, status, _, _, trace = run(impl.run_marker_generate(state, task(state)))
    assert status == "succeeded" and events == ["rag", "web", "model"]
    assert implementation_records(updates)["lattice"]["status"] == "implemented"
    assert not next(t for t in trace if t["tool"] == "web_search")["ok"]


def test_scoped_context_keeps_actual_host_and_omits_other_design_items(monkeypatch):
    import app.llm.invocation as invocation
    state = empty_state()
    host = {"type": "wall", "id": "wall_main_front_L1", "from": [0, 0, 0], "to": [10, 3, 0], "thickness": 0.2}
    other = {**host, "id": "unrelated_wall", "from": [20, 0, 0], "to": [30, 3, 0]}
    state["skeleton_blueprint"]["geometry"]["elements"] = [host, other]
    state["resolved_design"]["component_markers"] = [{"id": "only_window", "type": "window",
        "host": host["id"], "depends_on": [], "design": {}, "entity": {"parentWall": host["id"]}}]
    patch_services(monkeypatch, [])
    captured = []
    async def model(_llm, messages):
        captured.append(messages)
        return reply("only_window", [])
    monkeypatch.setattr(invocation, "invoke_llm", model)
    run(impl.run_marker_generate(state, task(state, "only_window")))
    context = json.loads(captured[0][1]["content"])
    assert context["existing_blueprint"]["geometry"]["elements"] == [host]
    assert "components" not in context["drawing"] and "roof" not in context["drawing"]
    assert all(e["id"] == host["id"] for e in context["diagram_hosts"])
    from app.agent.generation.capability import load_engine_schema
    assert len(captured[0][0]["content"]) < len(json.dumps(load_engine_schema(), ensure_ascii=False)) / 2


@pytest.mark.parametrize("direction", ["向南倾斜", "向北倾斜"])
def test_roof_context_preserves_global_direction_with_volume_override(direction):
    from app.design.resolver import architecture_plan_from_document
    raw = architecture_plan_from_document(drawing())
    raw["roof"] = {"type": "翼楼单坡屋顶" + direction,
                   "volumes": [{"volume": "main", "type": "单坡屋顶", "overhang": 0.4}]}
    document = build_design_document(raw, session_id="roof_context", source_request="按图纸实现屋顶")
    state = empty_state(document)
    before = deepcopy(state["design_document"])
    marker = next(m for m in state["resolved_design"]["component_markers"] if m["type"] == "roof")
    assert direction not in marker["design"]["type"]
    context = impl._item_context(state, {marker["id"]: marker}, state["skeleton_blueprint"])
    assert direction in context["drawing"]["roof"]["type"]
    assert context["markers"][0]["design"]["type"] == "单坡屋顶"
    assert "components" not in context["drawing"]
    context["drawing"]["roof"]["type"] = "其他参考"
    assert state["design_document"] == before


def test_model_service_failure_preserves_completed_markers_without_claiming_abandonment(monkeypatch):
    import app.llm.invocation as invocation
    document = drawing()
    second = document.decisions.components[0].model_copy(deep=True)
    second.id = "lattice2"
    document.decisions.components.append(second)
    state = empty_state(document)
    patch_services(monkeypatch, [])
    calls = []
    async def model(_llm, messages):
        calls.append(messages)
        if len(calls) > 1:
            raise RuntimeError("测试模型服务不可用")
        return SimpleNamespace(content=json.dumps({"implementations": [
            {"id": "lattice", "geometry": {"elements": [box("stable")]}},
            {"id": "lattice2", "geometry": {"elements": [{**box("invalid"), "dimensions": [-1, 1, 1]}]}}
        ]}), token_usage={})
    monkeypatch.setattr(invocation, "invoke_llm", model)
    updates, status, ids, _, _ = run(impl.run_marker_generate(state, task(state)))
    assert status == "aborted" and ids == ["stable"]
    records = implementation_records(updates)
    assert records["lattice"]["status"] == "implemented" and "lattice2" not in records


@pytest.mark.asyncio
@pytest.mark.parametrize("reasoning_field", ["additional_kwargs", "response_metadata", None])
@pytest.mark.parametrize("node_thinking", [False, True])
async def test_marker_reasoning_stream_is_routed_to_the_current_item(monkeypatch, reasoning_field, node_thinking):
    from app.agent.plan.workflow import _execute_one
    from app.agent.runtime import bind_reasoning_callback, reset_reasoning_callback, get_reasoning_callback
    import app.llm.client as client

    state = {**empty_state(), "thinking_mode": node_thinking}
    patch_services(monkeypatch, [])
    item = task(state)
    events, options = [], []
    class Model:
        async def astream(self, messages):
            if reasoning_field:
                for delta in ("先确定造型。", "再组合实体。"):
                    yield SimpleNamespace(content="", **{reasoning_field: {"reasoning_content": delta}})
            yield SimpleNamespace(content=reply("lattice").content)

    def factory(**kwargs):
        options.append(kwargs)
        return Model()
    monkeypatch.setattr(client, "create_llm", factory)

    async def emit(node, text):
        events.append((node, text))

    token = bind_reasoning_callback(emit)
    try:
        result = await _execute_one(state, item)
        assert get_reasoning_callback() is emit
    finally:
        reset_reasoning_callback(token)
    assert result[2] == "succeeded"
    assert options == [{"enable_thinking": True, "streaming": True}]
    expected = ["先确定造型。", "再组合实体。"] if reasoning_field else []
    assert [text for node, text in events if node == f"plan:{item.id}"] == expected
    assert all(node in {f"plan:{item.id}", f"plan:{item.id}:progress"} for node, _ in events)


@pytest.mark.asyncio
async def test_parallel_item_callbacks_remain_separate_and_restore_parent(monkeypatch):
    import asyncio
    from app.agent.plan.contracts import PlanItem
    from app.agent.plan.workflow import _execute_one, HANDLERS
    from app.agent.runtime import bind_reasoning_callback, reset_reasoning_callback, get_reasoning_callback
    events = []

    async def handler(_state, item):
        await asyncio.sleep(0)
        await get_reasoning_callback()("generate", item.id)
        await asyncio.sleep(0)
        await get_reasoning_callback()("generate", item.id)
        if item.id == "generate_b":
            raise ValueError("测试执行失败")
        return {}, "succeeded", [], "完成", []

    async def emit(node, text):
        events.append((node, text))

    monkeypatch.setitem(HANDLERS, "generate", handler)
    token = bind_reasoning_callback(emit)
    try:
        results = await asyncio.gather(*(_execute_one({}, PlanItem(id=i, op="generate", kind="window"))
                                         for i in ("generate_a", "generate_b")))
        assert get_reasoning_callback() is emit
    finally:
        reset_reasoning_callback(token)
    assert [r[2] for r in results] == ["succeeded", "failed"]
    assert [(n, t) for n, t in events if not n.endswith(":progress")] == [
        ("plan:generate_a", "generate_a"), ("plan:generate_b", "generate_b"),
        ("plan:generate_a", "generate_a"), ("plan:generate_b", "generate_b")]


def test_unknown_design_survives_save_approval_and_plan(tmp_path):
    document = drawing()
    repository = DesignRepository(tmp_path)
    repository.save(document)
    approved, resolved = repository.approve(document.session_id, document.revision)
    assert approved.decisions.roof.type == "wavy_custom"
    assert approved.decisions.roof.model_extra["curvature"] == 0.7
    assert approved.decisions.model_extra["floor_layouts"]
    assert any(m["id"] == "lattice" for m in resolved["component_markers"])
    assert any(i.kind == "custom_lattice" for i in expand_design_markers(empty_state(approved)).items)


def test_first_generation_uses_retrieved_knowledge_once(monkeypatch):
    state = empty_state()
    events = patch_services(monkeypatch, [reply("lattice", [box("part_1"), {**box("part_2"), "position": [2, 0, 0]}])])
    updates, status, ids, _, trace = run(impl.run_marker_generate(state, task(state)))
    assert status == "succeeded" and ids == ["part_1", "part_2"]
    assert events == ["rag", "model"]
    assert sum(t.get("model_calls", 0) for t in trace) == 1
    assert implementation_records(updates)["lattice"]["status"] == "implemented"


@pytest.mark.parametrize("success_stage", [1, 2])
def test_repair_order_reuses_references_without_more_searches(monkeypatch, success_stage):
    state = empty_state()
    outputs = [reply("lattice", [{**box(), "shape": "unrenderable"}]) for _ in range(success_stage)] + [reply("lattice")]
    events = patch_services(monkeypatch, outputs)
    updates, _, _, _, trace = run(impl.run_marker_generate(state, task(state)))
    record = implementation_records(updates)["lattice"]
    assert record["status"] == "implemented"
    stages = [t["stage"] for t in trace if "stage" in t]
    assert stages == ["generate", "repair_1", "repair_2"][:success_stage+1]
    assert events == ["rag"] + ["model"] * (success_stage+1)


def test_discard_only_after_all_stages(monkeypatch):
    state = empty_state()
    events = patch_services(monkeypatch, [reply("lattice", []) for _ in range(3)])
    updates, status, ids, _, trace = run(impl.run_marker_generate(state, task(state)))
    record = implementation_records(updates)["lattice"]
    assert status == "failed" and not ids
    assert record["status"] == "abandoned" and record["reason"]
    assert record["attempted_stages"] == ["generate", "repair_1", "repair_2"]
    assert events == ["rag", "model", "model", "model"]
    assert sum(t.get("model_calls", 0) for t in trace) == 3


def test_invalid_reference_is_rejected():
    state = empty_state()
    component = {"type": "window", "id": "bad", "parentWall": "missing",
                 "from": [1, 1, 0], "width": 1, "height": 1, "style": "fixed"}
    blueprint = state["skeleton_blueprint"]
    blueprint["geometry"]["components"].append(component)
    assert impl.implementation_errors(blueprint)


def test_failed_compile_keeps_dependants_and_drawing(monkeypatch):
    from app.agent.design_flow.compile import compile_node
    state = empty_state()
    state["resolved_design"]["component_markers"].append({"id": "child", "depends_on": ["lattice"]})
    state["component_fragments"] = {"g": [box("p"), {"id": "c", "type": "light", "parentWall": "p"}]}
    state["component_diagnostics"] = {"g": {"elements": ["p"], "components": ["c"], "implementations": {
        "lattice": {"status": "implemented", "entity_ids": ["p"]}, "child": {"status": "implemented", "entity_ids": ["c"]}}}}
    state["terminal_model_error"] = {"user_message": "连接超时"}
    before = deepcopy(state)
    result = run(compile_node(state))
    assert {e["id"] for bucket in ("elements", "components")
            for e in result["merged_blueprint"]["geometry"][bucket]} == {"p", "c"}
    assert result["status"] == "failed"
    assert state == before



def test_dependency_layers_allow_same_type_on_both_sides():
    state = empty_state()
    state["resolved_design"]["component_markers"] = [
        {"id": "a1", "type": "a", "depends_on": []},
        {"id": "b1", "type": "b", "depends_on": ["a1"]},
        {"id": "a2", "type": "a", "depends_on": ["b1"]},
    ]
    plan = expand_design_markers(state)
    assert [i.kind for i in plan.items] == ["a", "b", "a"]
    assert plan.items[2].depends_on == [plan.items[1].id]


def parallel_plan_state():
    state = empty_state()
    state["resolved_design"]["component_markers"] = [
        {"id": "building_body", "type": "building_body", "depends_on": []},
        *[{"id": kind, "type": kind, "depends_on": ["building_body"]}
          for kind in ("window", "door", "roof", "balcony", "canopy")],
        {"id": "railing", "type": "railing", "depends_on": ["balcony"]},
    ]
    state["plan"] = expand_design_markers(state).model_dump(mode="json")
    return state


def test_drawing_body_runs_alone_and_dependents_wait_for_their_host():
    from app.agent.plan.contracts import PlanDocument
    from app.agent.plan.store import refresh_statuses
    from app.agent.plan.workflow import _runnable_batch
    plan = PlanDocument.model_validate(parallel_plan_state()["plan"])
    assert [i.kind for i in _runnable_batch(plan)] == ["building_body"]
    assert plan.items[0].params["execution_mode"] == "serial"
    plan.items[0].status = "done"
    plan = refresh_statuses(plan)
    assert [i.kind for i in _runnable_batch(plan)] == ["window", "door", "roof"]
    assert plan.items[-1].status == "blocked"
    for item in plan.items[1:4]:
        item.status = "done"
    plan = refresh_statuses(plan)
    assert [i.kind for i in _runnable_batch(plan)] == ["balcony", "canopy"]
    plan.items[-1].status = "ready"
    plan = refresh_statuses(plan)
    assert plan.items[-1].status == "blocked"
    assert [i.kind for i in _runnable_batch(plan)] == ["balcony", "canopy"]
    plan.items[4].status = "done"
    plan = refresh_statuses(plan)
    assert [i.kind for i in _runnable_batch(plan)] == ["canopy", "railing"]


@pytest.mark.asyncio
async def test_drawing_execute_rechecks_ready_dependents_after_assembly_retry(monkeypatch):
    from app.agent.plan.workflow import execute_node, HANDLERS
    state = parallel_plan_state()
    for item in state["plan"]["items"][:4]:
        item["status"] = "done"
    for item in state["plan"]["items"][4:]:
        item["status"] = "ready"
    executed = []

    async def handler(_state, item):
        executed.append(item.kind)
        return {}, "succeeded", [], "完成", []

    monkeypatch.setitem(HANDLERS, "generate", handler)
    result = await execute_node(state)
    assert executed == ["balcony", "canopy"]
    assert result["execute_diag"]["parallel_count"] == 2
    assert result["plan"]["items"][-1]["status"] == "blocked"


@pytest.mark.asyncio
async def test_drawing_parallel_batches_reach_model_and_preserve_previous_fragments(monkeypatch):
    import asyncio
    from app.design.contracts import ComponentInstance
    from app.agent.plan.workflow import execute_node, replanner_node
    import app.llm.client as client
    import app.llm.invocation as invocation
    document = drawing()
    patch_services(monkeypatch, [])
    document.decisions.components.extend(ComponentInstance(id=f"detail_{i}", type=f"detail_{i}", host="main")
                                        for i in range(4))
    state = empty_state(document)
    state["component_fragments"] = {"generate_1": [box("body_part")]}
    state["component_diagnostics"] = {"generate_1": {"elements": ["body_part"],
        "implementations": {"building_body": {"status": "implemented", "entity_ids": ["body_part"]}}}}
    state["plan"] = expand_design_markers(state).model_dump(mode="json")
    active = peak = calls = 0
    all_started = asyncio.Event()

    async def model(_llm, messages):
        nonlocal active, peak, calls
        markers = json.loads(messages[1]["content"])["markers"]
        active += 1
        calls += 1
        peak = max(peak, active)
        if active == 3:
            all_started.set()
        try:
            await asyncio.wait_for(all_started.wait(), timeout=2)
            return SimpleNamespace(content=json.dumps({"implementations": [
                {"id": marker["id"], "geometry": {"elements": [
                    {**box(marker["id"] + "_part"), "position": [5, 3.05, 4], "dimensions": [10, 0.1, 8]}
                    if marker["type"] == "roof" else box(marker["id"] + "_part")], "components": []}}
                for marker in markers]}), token_usage={})
        finally:
            active -= 1

    monkeypatch.setattr(client, "create_llm", lambda **kwargs: None)
    monkeypatch.setattr(invocation, "invoke_llm", model)
    for _ in range(2):
        all_started.clear()
        result = await execute_node(state)
        assert result["execute_diag"]["parallel_count"] == 3
        assert result["execute_diag"]["model_calls"] == 3
        assert result["execute_diag"]["run_state"] == "succeeded"
        for key, value in result.items():
            if key in {"component_fragments", "component_diagnostics"}:
                state[key].update(value)
            else:
                state[key] = value
        state.update(await replanner_node(state))
    assert peak == 3 and calls == 6
    assert len(state["component_fragments"]) == 7
    assert state["plan"]["llm_calls"] == 6
    assert all(r["status"] == "implemented" for r in implementation_records(state).values())
    assert not impl.implementation_errors(impl.implementation_blueprint(state))


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_kind", [None, "door"])
async def test_drawing_executes_three_items_concurrently_without_mixing_results(monkeypatch, failed_kind):
    import asyncio
    from app.agent.plan.contracts import PlanDocument
    from app.agent.plan.store import refresh_statuses
    from app.agent.plan.workflow import execute_node, HANDLERS
    from app.agent.runtime import bind_reasoning_callback, reset_reasoning_callback, get_reasoning_callback
    state = parallel_plan_state()
    plan = PlanDocument.model_validate(state["plan"])
    plan.items[0].status = "done"
    state["plan"] = refresh_statuses(plan).model_dump(mode="json")
    expected = {i["id"] for i in state["plan"]["items"][1:4]}
    entered, events = set(), []
    all_started = asyncio.Event()

    async def handler(_state, item):
        entered.add(item.id)
        if len(entered) == 3:
            all_started.set()
        await asyncio.wait_for(all_started.wait(), timeout=2)
        await get_reasoning_callback()("generate", item.kind)
        if item.kind == failed_kind:
            raise ValueError("测试条目失败")
        return {"component_fragments": {item.id: [box(item.kind)]},
                "component_diagnostics": {item.id: {"kind": item.kind}}}, \
            "succeeded", [item.kind], "完成", [{"model_calls": 1}]

    async def emit(node, delta):
        events.append((node, delta))

    monkeypatch.setitem(HANDLERS, "generate", handler)
    token = bind_reasoning_callback(emit)
    try:
        result = await execute_node(state)
        assert get_reasoning_callback() is emit
    finally:
        reset_reasoning_callback(token)
    assert entered == expected
    assert result["execute_diag"]["parallel_count"] == 3
    assert set(result["execute_diag"]["item_ids"]) == expected
    success = {i["id"] for i in state["plan"]["items"][1:4] if i["kind"] != failed_kind}
    assert set(result["component_fragments"]) == success
    assert set(result["component_diagnostics"]) == success
    assert set(result["tool_trace"]) == expected
    assert result["execute_diag"]["model_calls"] == len(success)
    for item in result["plan"]["items"][1:4]:
        assert (f"plan:{item['id']}", item["kind"]) in events
        assert item["run"]["state"] == ("failed" if item["kind"] == failed_kind else "succeeded")
    assert all(i["run"]["state"] == "idle" for i in result["plan"]["items"][4:])
    assert not state["component_fragments"]


def test_full_assembly_delivers_valid_file_with_reported_omission(monkeypatch):
    from app.agent.design_flow.compile import compile_node
    from app.agent.validation.candidate import evaluate_candidate
    document = drawing()
    document.decisions.roof.type = "flat"
    state = empty_state(document)
    plan = expand_design_markers(state)
    state["plan"] = plan.model_dump(mode="json")
    walls = [{k: v for k, v in wall.items() if k != "facing"} | {"thickness": 0.2}
             for wall in state["drawing_hosts"]]
    floor = {"type": "floor", "id": "floor_main", "from": [0, 0, 0], "to": [10, 0, 8], "thickness": 0.2}
    roof = {"type": "roof", "id": "roof_main", "roofType": "flat", "span": 10.4,
            "depth": 8.4, "height": 0.2, "thickness": 0.2, "position": [5, 3, 4]}
    outputs = [reply("building_body", walls + [floor]), reply("roof_main", [roof])]
    outputs.extend(reply("lattice", []) for _ in range(3))
    patch_services(monkeypatch, outputs)
    for item in plan.items:
        updates, _, _, _, _ = run(impl.run_marker_generate(state, item))
        for key in ("component_fragments", "component_diagnostics"):
            state[key].update(updates[key])
    result = run(compile_node(state))
    assert result.get("merged_blueprint"), result
    evaluation = evaluate_candidate(result["merged_blueprint"], design_document=state["design_document"],
                                    design_brief=result["design_brief"])
    assert not evaluation["errors"], [e.output for e in evaluation["errors"]]
    from app.agent.validation.workflow import validate_node
    final = run(validate_node({**state, **result}))
    assert final["status"] == "complete", final
    assert final["final_blueprint"] == result["merged_blueprint"]
    assert evaluation["fulfillment"]["implementation_summary"]["abandoned"] == 1
    assert any(g["target"] == "lattice" and g["actual"] == "舍弃" for g in evaluation["fulfillment"]["gaps"])


def test_no_attempt_omission_cannot_pass_final_gate():
    from app.agent.validation.candidate import evaluate_candidate
    state = empty_state()
    blueprint = state["skeleton_blueprint"]
    blueprint["geometry"]["elements"] = [box()]
    records = {m["id"]: {"status": "abandoned", "entity_ids": [], "reason": "未支持"}
               for m in state["resolved_design"]["component_markers"]}
    evaluation = evaluate_candidate(blueprint, design_document=state["design_document"],
        design_brief={"implementation": {"design_hash": state["resolved_design"]["design_hash"], "records": records}})
    assert any(e.name == "implementation_incomplete" for e in evaluation["errors"])
    for record in records.values():
        record["attempts"] = [{"stage": stage} for stage in ("generate", "repair_1", "repair_2")]
    evaluation = evaluate_candidate(blueprint, design_document=state["design_document"],
        design_brief={"implementation": {"design_hash": state["resolved_design"]["design_hash"], "records": records}})
    assert any(e.name == "implementation_incomplete" and "lattice" in str(e.output) for e in evaluation["errors"])


def test_architecture_node_never_compiles_or_filters_design(monkeypatch):
    monkeypatch.setattr("app.services.agent_service.agent_service.spec_loader.load_many", lambda *_args, **_kwargs: "")
    from app.agent.generation.architecture.workflow import architecture_planner
    from app.agent.generation.architecture import design_workflow
    from app.design.resolver import architecture_plan_from_document
    import app.design.compilation as compilation
    raw = architecture_plan_from_document(drawing())
    raw.pop("design_constraints")
    async def model(*args, **kwargs):
        return SimpleNamespace(content=json.dumps(raw), token_usage=None)
    def forbidden(*args, **kwargs):
        raise AssertionError("architecture 不应运行编译器")
    monkeypatch.setattr(compilation, "compile_document", forbidden)
    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    monkeypatch.setattr(design_workflow, "create_llm", lambda **kwargs: None)
    result = run(architecture_planner({"user_message": "生成别墅"}))
    assert result["design_review_status"] == "pending", result
    assert result["design_document"]["decisions"]["components"][0]["type"] == "custom_lattice"
    assert result["design_document"]["decisions"]["roof"]["type"] == "wavy_custom"


def test_plan_node_creates_empty_container_and_original_design_tasks():
    from app.agent.plan.workflow import plan_node
    result = run(plan_node(empty_state()))
    assert not result["skeleton_blueprint"]["geometry"]["elements"]
    assert any(i["kind"] == "custom_lattice" for i in result["plan"]["items"])
    assert result["drawing_hosts"]


def test_assembly_feedback_reuses_references_without_repeating_lookup(monkeypatch):
    state = empty_state()
    patch_services(monkeypatch, [reply("lattice")])
    item = task(state)
    updates, _, _, _, _ = run(impl.run_marker_generate(state, item))
    state.update(updates)
    old = state["component_diagnostics"][item.id]
    old["prior_implementations"] = dict(old["implementations"])
    old.update(implementations={}, elements=[], components=[])
    state["component_fragments"][item.id] = []
    item.params["assembly_feedback"] = "完整建筑校验发现冲突"
    events = patch_services(monkeypatch, [reply("lattice", [])])
    updates, _, _, _, trace = run(impl.run_marker_generate(state, item))
    assert events == ["model"]
    assert implementation_records(updates)["lattice"]["attempted_stages"] == ["generate", "assembly_revision"]
    assert sum(t.get("model_calls", 0) for t in trace) == 1


def test_compile_failure_keeps_all_original_fragments_without_requeuing(monkeypatch):
    from app.agent.design_flow.compile import compile_node
    from app.agent.validation import candidate
    from app.agent.validation.diagnostics import blueprint_fingerprint
    document = drawing()
    second = document.decisions.components[0].model_copy(deep=True)
    second.id = "lattice2"
    document.decisions.components.append(second)
    state = empty_state(document)
    plan = expand_design_markers(state)
    for item in plan.items:
        rows = [box(marker_id + "_part") for marker_id in item.target["marker_ids"]]
        state["component_fragments"][item.id] = rows
        state["component_diagnostics"][item.id] = {"elements": [e["id"] for e in rows], "components": [],
            "implementations": {marker_id: {"status": "implemented", "entity_ids": [entity["id"]],
                "entity_fingerprint": blueprint_fingerprint([entity]), "attempted_stages": ["generate"]}
                for marker_id, entity in zip(item.target["marker_ids"], rows)}}
        item.status = "done"
    state["plan"] = plan.model_dump(mode="json")
    monkeypatch.setattr(candidate, "evaluate_candidate", lambda *args, **kwargs: {
        "errors": [SimpleNamespace(output="lattice_part 与 lattice2_part 的组合出现冲突")],
        "issues": [{"component_id": "lattice_part", "related_entity_ids": ["lattice2_part"]}]})
    patch_services(monkeypatch, [SimpleNamespace(content="无可用修改", reasoning="")])
    before = deepcopy(state)
    result = run(compile_node(state))
    assert result["plan"]["items"] == state["plan"]["items"]
    assert state == before
    assert result["compile_report"]["repair"]["attempted"]
    assert not result["compile_report"]["repair"]["accepted"]
    assert result["compile_report"]["repair"]["original_blueprint"] == result["merged_blueprint"]
    assert {e["id"] for e in result["merged_blueprint"]["geometry"]["elements"]} >= {"lattice_part", "lattice2_part"}



def test_mutual_design_dependency_is_attempted_together():
    state = empty_state()
    state["resolved_design"]["component_markers"] = [
        {"id": "a", "type": "a", "depends_on": ["b"]},
        {"id": "b", "type": "b", "depends_on": ["a"]},
    ]
    plan = expand_design_markers(state)
    assert len(plan.items) == 1 and plan.items[0].target["marker_ids"] == ["a", "b"]


def test_material_attachment_preserves_designer_role_and_keywords():
    from app.design.resolver import attach_material_plan
    document = drawing()
    document.decisions.components[0].material_role = "custom_metal"
    document.decisions.materials.keywords = ["原始材料意图"]
    material = {"concept": "材料实现", "palette": ["银灰"], "roles": [], "resolvedAssets": {}}
    attached = attach_material_plan(document, material)
    assert attached.decisions.components[0].material_role == "custom_metal"
    assert "原始材料意图" in attached.decisions.materials.keywords


def test_non_json_numeric_output_is_rejected():
    state = empty_state()
    entity = box()
    entity["dimensions"][0] = float("nan")
    state["skeleton_blueprint"]["geometry"]["elements"] = [entity]
    assert any("JSON" in e for e in impl.implementation_errors(state["skeleton_blueprint"]))


def test_web_adapter_returns_sources_and_descriptions(monkeypatch):
    import sys
    requests = []
    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url, params):
            requests.append((url, params))
            return SimpleNamespace(raise_for_status=lambda: None,
                text='<rss><channel><item><title>Small</title><link>https://example.com/journal</link><description>科研期刊</description></item><item><title>构件</title><link>https://example.com/shape</link><description>曲线形态</description></item></channel></rss>')
    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(AsyncClient=Client))
    hits = run(impl.search_web_impl('"构件" 曲线形态'))
    assert requests[0][1]["q"] == '"构件" 曲线形态'
    assert hits == [{"title": "构件", "url": "https://example.com/shape", "description": "曲线形态"}]


@pytest.mark.parametrize("index", [0, 1])
def test_recorded_drawing_keeps_explicit_components_and_numeric_quotas(monkeypatch, index):
    monkeypatch.setattr("app.services.agent_service.agent_service.spec_loader.load_many", lambda *_args, **_kwargs: "")
    from app.agent.generation.architecture.workflow import architecture_planner
    from app.agent.generation.architecture import design_workflow
    raw = json.loads((Path(__file__).parents[1] / "fixtures/architecture_drawing_rejected_outputs.json").read_text(encoding="utf-8"))[index]
    async def model(*args, **kwargs):
        return SimpleNamespace(content=json.dumps(raw), token_usage=None)
    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    monkeypatch.setattr(design_workflow, "create_llm", lambda **kwargs: None)
    result = run(architecture_planner({"user_message": "生成别墅"}))
    assert result.get("design_review_status") == "pending", result
    decisions = result["design_document"]["decisions"]
    assert decisions["component_quota"] == raw["component_quota"]
    assert len(decisions["components"]) == len(raw["components"])


@pytest.mark.parametrize("repaired", [True, False])
def test_full_assembly_failure_repairs_current_fragment_once(monkeypatch, repaired):
    from app.agent.design_flow.compile import compile_node
    document = drawing()
    document.decisions.roof.type = "flat"
    document.decisions.components = []
    state = empty_state(document)
    plan = expand_design_markers(state)
    state["plan"] = plan.model_dump(mode="json")
    walls = [{k: v for k, v in wall.items() if k != "facing"} | {"thickness": 0.2}
             for wall in state["drawing_hosts"]]
    floor = {"type": "floor", "id": "floor_main", "from": [0, 0, 0], "to": [10, 0, 8], "thickness": 0.2}
    roof = {"type": "roof", "id": "roof_main", "roofType": "flat", "span": 10.4,
            "depth": 8.4, "height": 0.2, "thickness": 0.2, "position": [5, 4, 4]}
    outputs = [reply("building_body", walls + [floor]), reply("roof_main", [roof])]
    events = patch_services(monkeypatch, outputs)
    for item in plan.items:
        updates, _, _, _, _ = run(impl.run_marker_generate(state, item))
        for key in updates:
            state[key].update(updates[key])
        item.status = "done"
    state["plan"] = plan.model_dump(mode="json")
    patch_reply = SimpleNamespace(content=json.dumps({"summary": "修复屋面承托标高", "operations": [
        {"op": "update_element", "id": "roof_main", "changes": {"position": [5, 3 if repaired else 4, 4]}}
    ]}), reasoning="")
    repair_events = patch_services(monkeypatch, [patch_reply])
    before = deepcopy(state)
    result = run(compile_node(state))
    report = result["compile_report"]
    assert report["ok"] is repaired, result
    assert report["repair"]["accepted"] is repaired, report
    assert repair_events == ["model"]
    assert result["merged_blueprint"]["geometry"]["elements"], "集中修复不能清空已有建筑"
    roof_after = next(e for e in result["merged_blueprint"]["geometry"]["elements"] if e["id"] == "roof_main")
    assert roof_after["position"] == [5, 3 if repaired else 4, 4]
    assert state == before
    again = run(compile_node({**state, **result}))
    assert repair_events == ["model"], "集中修复最多调用一次，不因再次编译重复调用"
    assert again["merged_blueprint"] == result["merged_blueprint"]
    assert again["plan"]["llm_calls"] == result["plan"]["llm_calls"]



def test_malformed_marker_id_is_revised_instead_of_crashing(monkeypatch):
    state = empty_state()
    bad = SimpleNamespace(content=json.dumps({"implementations": [{"id": []}]}), token_usage={})
    patch_services(monkeypatch, [bad, reply("lattice")])
    updates, status, _, _, _ = run(impl.run_marker_generate(state, task(state)))
    assert status == "succeeded"
    assert implementation_records(updates)["lattice"]["attempted_stages"] == ["generate", "repair_1"]


def test_batch_retry_preserves_other_successful_markers(monkeypatch):
    document = drawing()
    second = document.decisions.components[0].model_copy(deep=True)
    second.id = "lattice2"
    document.decisions.components.append(second)
    state = empty_state(document)
    item = task(state)
    output = SimpleNamespace(content=json.dumps({"implementations": [
        {"id": i, "geometry": {"elements": [box(i+"_part")], "components": []}}
        for i in ("lattice", "lattice2")]}), token_usage={})
    patch_services(monkeypatch, [output])
    updates, _, _, _, _ = run(impl.run_marker_generate(state, item))
    state.update(updates)
    diag = state["component_diagnostics"][item.id]
    stable = deepcopy(diag["implementations"]["lattice2"])
    diag["prior_implementations"] = {"lattice": diag["implementations"].pop("lattice")}
    diag["elements"] = ["lattice2_part"]
    state["component_fragments"][item.id] = [box("lattice2_part")]
    item.params.update(assembly_feedback="完整装配冲突", retry_marker_ids=["lattice"])
    patch_services(monkeypatch, [reply("lattice", [box("new_part")])])
    updates, _, _, _, _ = run(impl.run_marker_generate(state, item))
    records = implementation_records(updates)
    assert records["lattice2"] == stable
    assert records["lattice"]["attempted_stages"] == ["generate", "assembly_revision"]
    assert {e["id"] for e in updates["component_fragments"][item.id]} == {"new_part", "lattice2_part"}



def test_invalid_remaining_building_is_preserved_with_failed_validation():
    from app.agent.validation.workflow import validate_node
    state = empty_state()
    bad = box()
    bad["dimensions"] = [-1, 1, 1]
    state["merged_blueprint"] = deepcopy(state["skeleton_blueprint"])
    state["merged_blueprint"]["geometry"]["elements"] = [bad]
    result = run(validate_node(state))
    assert result["status"] == "failed"
    assert result["validation_error_count"] > 0
    assert result["final_blueprint"] == state["merged_blueprint"]
    assert result["validation_snapshot"]["status"] == "failed"


def test_missing_implementation_marker_still_returns_existing_assembled_geometry(monkeypatch):
    from app.agent.design_flow.compile import compile_node
    state = empty_state()
    state["plan"] = expand_design_markers(state).model_dump(mode="json")
    state["component_fragments"] = {"body": [box()]}
    state["component_diagnostics"] = {"body": {"elements": ["part"], "components": [],
        "implementations": {"building_body": {"status": "implemented", "entity_ids": ["part"]}}}}
    patch_services(monkeypatch, [SimpleNamespace(content="无可用修改", reasoning="")])
    result = run(compile_node(state))
    assert result["status"] == "failed" and "未完成" in result["error"]
    assert result["merged_blueprint"]["geometry"]["elements"] == [box()]


def test_explicit_opening_replaces_one_slot_and_preserves_remaining_slots():
    from app.design.contracts import ComponentInstance, FacadeDecision
    document = drawing()
    document.decisions.facades["front"] = FacadeDecision(bays=3,
        ground_pattern=["window"]*3, upper_pattern=["window"]*3)
    document.decisions.components.append(ComponentInstance(id="window_custom", type="window",
        host="wall_main_front_L1", placement={"bay": 2}))
    markers = component_markers(document)
    windows = [m for m in markers if m["type"] == "window" and m["host"] == "wall_main_front_L1"]
    assert {m["id"] for m in windows} == {"window_custom", "window_main_front_L1_1", "window_main_front_L1_3"}


def test_free_attachment_relation_and_position_survive_design():
    from app.design.contracts import ComponentInstance
    document = drawing()
    document.decisions.components.append(ComponentInstance(id="pendant", type="custom_light",
        host="roof_main", relation={"kind": "hung_from", "target": "roof_main"},
        placement={"offset": -0.3, "sill_height": -0.2}))
    resolved = resolve_design(document)
    marker = next(m for m in resolved.component_markers if m["id"] == "pendant")
    assert "roof_main" in marker["depends_on"]
    assert marker["design"]["relation"]["kind"] == "hung_from"
    assert marker["design"]["placement"]["sill_height"] == -0.2



def test_execution_and_reconciliation_finish_all_assembly_stages(monkeypatch):
    from app.agent.plan import workflow
    from app.agent.plan.workflow import execute_node, replanner_node
    async def sequential_gather(*coroutines):
        return [await c for c in coroutines]
    monkeypatch.setattr(workflow, "asyncio", SimpleNamespace(gather=sequential_gather))
    from app.agent.design_flow.compile import compile_node
    from app.agent.plan.contracts import PlanDocument
    from app.agent.plan.store import poll_runnable
    document = drawing()
    document.decisions.roof.type = "flat"
    document.decisions.components = []
    state = empty_state(document)
    state["plan"] = expand_design_markers(state).model_dump(mode="json")
    walls = [{k: v for k, v in w.items() if k != "facing"} | {"thickness": 0.2} for w in state["drawing_hosts"]]
    floor = {"type": "floor", "id": "floor_main", "from": [0, 0, 0], "to": [10, 0, 8], "thickness": 0.2}
    roof = {"type": "roof", "id": "roof_main", "roofType": "flat", "span": 10.4,
            "depth": 8.4, "height": 0.2, "thickness": 0.2, "position": [5, 4, 4]}
    outputs = [reply("building_body", walls+[floor]), reply("roof_main", [roof]),
               SimpleNamespace(content="无法修复", reasoning="")]
    events = patch_services(monkeypatch, outputs)
    def merge(updates):
        for key, value in updates.items():
            if key in {"component_fragments", "component_diagnostics"}:
                state[key].update(value)
            else:
                state[key] = value
    for _ in range(12):
        plan = PlanDocument.model_validate(state["plan"])
        if poll_runnable(plan):
            merge(run(execute_node(state)))
            merge(run(replanner_node(state)))
        else:
            result = run(compile_node(state))
            merge(result)
            if not result["compile_report"].get("retry_implementation"):
                break
    else:
        raise AssertionError("建筑实现循环未按尝试次数结束")
    assert not result["compile_report"]["ok"], result
    assert implementation_records(state)["roof_main"]["status"] == "implemented"
    assert state["plan"]["llm_calls"] == 3
    roof_task = next(i for i in state["plan"]["items"] if "roof_main" in i["target"]["marker_ids"])
    assert roof_task["status"] == "done"
    assert roof_task["run"]["artifacts"] == ["roof_main"]
    assert any(e["id"] == "roof_main" for e in result["merged_blueprint"]["geometry"]["elements"])
    assert not state["plan"]["give_up"]
    assert events == ["rag", "model", "rag", "model", "model"]


def test_per_volume_roof_override_survives_open_main_roof():
    from app.design.contracts import RoofDecision
    document = drawing()
    document.decisions.roof = RoofDecision(type="none", volumes=[
        {"volume": "main", "type": "custom_curved", "curvature": 0.4}])
    roof = next(m for m in component_markers(document) if m["id"] == "roof_main")
    assert roof["design"]["type"] == "custom_curved"
    assert roof["design"]["curvature"] == 0.4



@pytest.mark.parametrize("malformed", [["balcony"], {"balcony": 1}, 3])
def test_malformed_component_list_returns_to_format_revision(monkeypatch, malformed):
    monkeypatch.setattr("app.services.agent_service.agent_service.spec_loader.load_many", lambda *_args, **_kwargs: "")
    from app.agent.generation.architecture.workflow import architecture_planner
    from app.agent.generation.architecture import design_workflow
    from app.design.resolver import architecture_plan_from_document
    good = architecture_plan_from_document(drawing())
    outputs = [{**good, "components": malformed}, good]
    async def model(*args, **kwargs):
        return SimpleNamespace(content=json.dumps(outputs.pop(0)), token_usage=None)
    monkeypatch.setattr(design_workflow, "invoke_llm", model)
    monkeypatch.setattr(design_workflow, "create_llm", lambda **kwargs: None)
    result = run(architecture_planner({"user_message": "生成别墅"}))
    assert result["design_review_status"] == "pending", result
    assert result["architecture_diag"]["model_calls"] == 2
    assert result["design_document"]["decisions"]["components"][0]["id"] == "lattice"


@pytest.mark.parametrize("failure", ["invalid_json", "timeout", "removal", "partial_improvement"])
def test_one_compile_repair_preserves_source_and_keeps_remaining_errors(monkeypatch, failure):
    from app.agent.design_flow import compile as compiler
    from app.agent.validation import candidate
    import app.llm.invocation as invocation
    state = empty_state()
    state["plan"] = expand_design_markers(state).model_dump(mode="json")
    blueprint = deepcopy(state["skeleton_blueprint"])
    blueprint["geometry"]["elements"] = [box("keep")]
    monkeypatch.setattr(compiler, "_assemble_with_relations", lambda *args: (deepcopy(blueprint), [], {}))
    missing_stair = {"code": "missing_stair", "entity_id": None, "message": "缺少楼梯"}
    bad_size = {"code": "size", "entity_id": "keep", "message": "尺寸不满足图纸"}
    def evaluate(bp, **kwargs):
        issues = [missing_stair]
        if bp["geometry"]["elements"][0]["dimensions"][0] == 1:
            issues.append(bad_size)
        return {"errors": [SimpleNamespace(output=i["message"]) for i in issues],
                "issues": issues, "fulfillment": {"satisfied_ids": ["existing"]}}
    monkeypatch.setattr(candidate, "evaluate_candidate", evaluate)
    patch_data = {"summary": "修复尺寸", "operations": [
        {"op": "update_element", "id": "keep", "changes": {"dimensions": [2, 1, 1]}}]}
    if failure == "removal":
        patch_data["operations"] = [{"op": "remove_element", "id": "keep"}]
    events = patch_services(monkeypatch, [SimpleNamespace(
        content="无法解析" if failure == "invalid_json" else json.dumps(patch_data), reasoning="")])
    if failure == "timeout":
        async def unavailable(*args, **kwargs):
            events.append("model")
            raise TimeoutError("service unavailable")
        monkeypatch.setattr(invocation, "invoke_llm", unavailable)
    result = run(compiler.compile_node(state))
    assert events == ["model"]
    assert result["status"] == "failed"
    assert result["compile_report"]["repair"]["accepted"] is (failure == "partial_improvement")
    assert result["compile_report"]["repair"]["original_blueprint"] == blueprint
    assert result["merged_blueprint"]["geometry"]["elements"][0]["id"] == "keep"
    if failure == "partial_improvement":
        assert result["merged_blueprint"]["geometry"]["elements"][0]["dimensions"][0] == 2
        assert result["compile_report"]["errors"] == ["缺少楼梯"]
    else:
        assert result["merged_blueprint"] == blueprint


def test_abandoned_body_candidate_is_compiled_when_no_accepted_entities_exist():
    from app.agent.design_flow.compile import compile_node
    state = empty_state()
    state["plan"] = expand_design_markers(state).model_dump(mode="json")
    state["component_diagnostics"] = {"body": {
        "implementations": {"building_body": {"status": "abandoned", "entity_ids": [], "reason": "几何校验失败"}},
        "failed_implementations": {"building_body": {"geometry": {"elements": [box("raw_body")], "components": []}}}}}
    state["terminal_model_error"] = {"user_message": "模型超时"}
    result = run(compile_node(state))
    assert result["merged_blueprint"]["geometry"]["elements"] == [box("raw_body")]
    assert not result["compile_report"].get("repair")
    assert result["status"] == "failed"


def test_compile_repair_streams_reasoning_through_graph_callback(monkeypatch):
    import app.llm.invocation as invocation
    from app.agent.runtime import bind_reasoning_callback, reset_reasoning_callback
    deltas = []

    async def emit(node, delta):
        deltas.append((node, delta))

    async def streaming(llm, messages, *, on_reasoning_delta):
        await on_reasoning_delta("修订尺寸")
        return await invocation.invoke_llm(llm, messages)

    monkeypatch.setattr(invocation, "stream_llm", streaming)
    token = bind_reasoning_callback(emit)
    try:
        test_one_compile_repair_preserves_source_and_keeps_remaining_errors(monkeypatch, "partial_improvement")
    finally:
        reset_reasoning_callback(token)
    assert ("compile", "修订尺寸") in deltas
    assert any(node == "compile:progress" for node, _ in deltas)
