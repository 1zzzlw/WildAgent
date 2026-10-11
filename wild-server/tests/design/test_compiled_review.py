"""图纸预览不复用过期投影，每个标记可在示意或清单中找到。"""
import json
from pathlib import Path
from xml.etree import ElementTree

from app.design.resolver import build_design_document, resolve_design, render_design_svg


def document():
    plan = json.loads((Path(__file__).parents[1]/"fixtures/design_trace_baseline.json").read_text(encoding="utf-8"))["normalized_plan"]
    return build_design_document(plan, session_id="parity", source_request="生成一个别墅")


def test_stale_or_legacy_resolved_view_is_not_rendered():
    doc = document()
    old = resolve_design(doc)
    old.component_markers[0]["id"] = "stale-sentinel"
    old.resolver_version = "legacy"
    assert "stale-sentinel" not in render_design_svg(doc, old)
    old = resolve_design(doc)
    changed = doc.model_copy(update={"revision": doc.revision+1})
    assert f"DesignDocument r{changed.revision}" in render_design_svg(changed, old)


def test_svg_displays_all_drawing_markers_without_compilation():
    doc = document()
    resolved = resolve_design(doc)
    root = ElementTree.fromstring(render_design_svg(doc, resolved))
    shown = {e.get("data-marker-id") for e in root.iter() if e.get("data-marker-id")}
    assert shown == {m["id"] for m in resolved.component_markers}
