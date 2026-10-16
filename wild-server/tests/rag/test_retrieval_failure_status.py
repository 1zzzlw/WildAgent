"""连接异常不能伪装成语义检索零命中。"""
from types import SimpleNamespace
from unittest.mock import Mock

import json
from pathlib import Path
import re

import jsonschema
import pytest

from app.spec.loader import RAGSpecLoader, SpecLoadResult
from app.agent.plan.knowledge_tool import search_knowledge_result


def test_load_result_preserves_failure_type_without_shared_mutable_state():
    loader = object.__new__(RAGSpecLoader)
    loader._load_base_text = Mock(return_value="BASE")
    loader._apply_retrieval_gate = lambda hits, **kwargs: hits
    loader._max_context_chars = 18000
    loader.retrieve_many = Mock(side_effect=ConnectionError("service offline"))
    failed = loader.load_many_result(["wall"], include_base=False)
    assert failed.error_type == "ConnectionError" and failed.hits == ()
    loader.retrieve_many = Mock(return_value=[])
    empty = loader.load_many_result(["wall"], include_base=False)
    assert empty.error_type is None and failed.error_type == "ConnectionError"


def test_component_search_distinguishes_failed_service_from_no_matching_documents(monkeypatch):
    from app.services import agent_service as service_module

    loader = SimpleNamespace(load_many_result=Mock(return_value=SpecLoadResult("", error_type="APIConnectionError")))
    monkeypatch.setattr(service_module, "agent_service", SimpleNamespace(spec_loader=loader))
    result = search_knowledge_result("柱梁连接", kind="beam")
    assert result["error_type"] == "APIConnectionError"
    assert "检索服务调用失败" in result["text"] and "没有检索到内容" not in result["text"]
    assert not result["has_shape_reference"] and result["chunk_ids"] == []
    loader.load_many_result.return_value = SpecLoadResult("")
    empty = search_knowledge_result("柱梁连接", kind="beam")
    assert not empty.get("error_type") and "没有检索到内容" in empty["text"]


@pytest.mark.parametrize("index", range(5))
def test_pavilion_partial_examples_follow_the_actual_wild_schema(index):
    from app.agent.generation.capability import load_engine_schema

    path = Path(__file__).resolve().parents[2] / "storage/knowledge_base/knowledge/components/pavilion-garden-structure.md"
    blocks = re.findall(r"```json\s*\n(.*?)```", path.read_text(encoding="utf-8"), re.S)
    data = json.loads(blocks[index])
    elements = data if isinstance(data, list) else data["elements"]
    materials = data.get("materials", {}) if isinstance(data, dict) else {}
    for entity in elements:
        materials.setdefault(entity["material"], {"baseColor": [0.4, 0.3, 0.2], "roughness": 0.7,
                             "metallic": 0, "albedo": 1, "lightingCondition": "D65_noon"})
    blueprint = {"meta": {"version": "1.0", "type": "building", "name": "local-example"},
                 "geometry": {"elements": elements, "components": []}, "materials": materials, "assets": {}}
    jsonschema.Draft202012Validator(load_engine_schema()).validate(blueprint)
