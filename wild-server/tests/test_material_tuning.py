import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.agent_service import (
    AgentService,
    _apply_patch_to_blueprint,
    _build_scene_summary,
    _is_material_optimization_request,
    _validate_material_optimization_patch,
    _validate_scene_patch_operations,
)


ASSET_ID = "pbr_0123456789abcdef01234567"


def _blueprint() -> dict:
    image = {
        "encoding": "url",
        "uri": f"/api/assets/{ASSET_ID}/files/baseColor.png",
        "mimeType": "image/png",
        "sha256": "a" * 64,
        "byteSize": 128,
        "colorSpace": "srgb",
    }
    normal_image = {
        **image,
        "uri": f"/api/assets/{ASSET_ID}/files/normal.png",
        "sha256": "c" * 64,
        "colorSpace": "linear",
    }
    return {
        "meta": {"version": "1.1", "type": "building", "name": "material-test"},
        "geometry": {
            "elements": [
                {
                    "id": "wall_front",
                    "type": "wall",
                    "from": [0, 0, 0],
                    "to": [6, 3, 0],
                    "thickness": 0.2,
                    "material": "stone_shared",
                },
                {
                    "id": "wall_back",
                    "type": "wall",
                    "from": [6, 0, 4],
                    "to": [0, 3, 4],
                    "thickness": 0.2,
                    "material": "stone_shared",
                },
            ],
            "components": [],
        },
        "materials": {
            "stone_shared": {
                "baseColor": [1, 1, 1],
                "roughness": 0.55,
                "metallic": 0,
                "albedo": 1,
                "lightingCondition": "D65_noon",
                "textureSet": ASSET_ID,
                "normalScale": 1,
                "uvScale": [1, 1],
            }
        },
        "assets": {
            ASSET_ID: {
                "schemaVersion": "1.0",
                "assetId": ASSET_ID,
                "kind": "pbr_texture_set",
                "name": "Stone",
                "contentHash": "sha256:" + "b" * 64,
                "source": {"type": "local_upload"},
                "license": "CC0",
                "maps": {"baseColor": image, "normal": normal_image},
                "createdAt": "2026-08-10T00:00:00Z",
            }
        },
    }


def _tuning_patch() -> dict:
    return {
        "operations": [{
            "op": "tune_material",
            "id": "wall_front",
            "material_field": "material",
            "new_name": "stone_front_tuned",
            "changes": {
                "roughness": 0.82,
                "normalScale": 1.35,
                "uvScale": [2, 2],
            },
            "rationale": "石材提高粗糙度并缩小纹理尺度。",
        }],
        "summary": "优化前墙石材质感",
    }


def test_tune_material_clones_source_and_preserves_texture_asset():
    blueprint = _blueprint()
    patch_data = _tuning_patch()

    assert _validate_scene_patch_operations(blueprint, patch_data) == []
    assert _validate_material_optimization_patch(
        patch_data,
        ["wall_front"],
    ) == []

    modified = _apply_patch_to_blueprint(blueprint, patch_data)
    tuned = modified["materials"]["stone_front_tuned"]
    assert tuned["textureSet"] == ASSET_ID
    assert tuned["roughness"] == 0.82
    assert tuned["normalScale"] == 1.35
    assert modified["geometry"]["elements"][0]["material"] == "stone_front_tuned"
    assert modified["geometry"]["elements"][1]["material"] == "stone_shared"
    assert blueprint["materials"]["stone_shared"]["roughness"] == 0.55


@pytest.mark.parametrize("changes, expected", [
    ({"textureSet": "pbr_bad"}, "不允许的字段"),
    ({"normalScale": 5}, "0–4"),
    ({"roughness": -0.1}, "0–1"),
    ({"uvScale": [0, 2]}, "正有限数字"),
])
def test_tune_material_rejects_unsafe_or_invalid_changes(changes, expected):
    patch_data = _tuning_patch()
    patch_data["operations"][0]["changes"] = changes
    issues = _validate_scene_patch_operations(_blueprint(), patch_data)
    assert any(expected in issue for issue in issues)


def test_tune_material_rejects_ineffective_normal_scale_and_noop():
    without_normal = _blueprint()
    without_normal["assets"][ASSET_ID]["maps"].pop("normal")
    patch_data = _tuning_patch()
    patch_data["operations"][0]["changes"] = {"normalScale": 1.4}
    issues = _validate_scene_patch_operations(without_normal, patch_data)
    assert any("没有 normal 纹理" in issue for issue in issues)

    patch_data["operations"][0]["changes"] = {"roughness": 0.55}
    issues = _validate_scene_patch_operations(_blueprint(), patch_data)
    assert any("没有产生任何材质参数变化" in issue for issue in issues)


def test_material_mode_rejects_non_tuning_operations_and_unselected_target():
    issues = _validate_material_optimization_patch({
        "operations": [
            {"op": "upsert_asset", "asset_id": ASSET_ID, "asset": {}},
            {**_tuning_patch()["operations"][0], "id": "wall_back"},
        ],
    }, ["wall_front"])

    assert any("只允许 tune_material" in issue for issue in issues)
    assert any("当前选中构件" in issue for issue in issues)


def test_selected_scene_summary_exposes_parameters_but_not_image_url():
    summary = _build_scene_summary(_blueprint(), ["wall_front"])

    assert "当前选中构件: wall_front" in summary
    assert "roughness" in summary
    assert f"asset={ASSET_ID}" in summary
    assert "/api/assets/" not in summary


class _FakeAgent:
    def __init__(self, response):
        self.response = response
        self.payload = None

    async def ainvoke(self, payload, config=None):
        self.payload = payload
        return {"messages": [self.response]}


class _UnusedLLM:
    calls = 0

    async def ainvoke(self, _messages):
        self.calls += 1
        raise AssertionError("不应执行格式恢复")


def _service(response):
    service = AgentService.__new__(AgentService)
    fake_agent = _FakeAgent(response)
    service._build_rag_queries = lambda *_args, **_kwargs: []
    service._agent_for_query = lambda *_args, **_kwargs: fake_agent
    service.llm = _UnusedLLM()
    return service, fake_agent


def test_query_material_optimization_forces_safe_patch_protocol():
    response = SimpleNamespace(
        content=str(_tuning_patch()).replace("'", '"'),
        additional_kwargs={},
        response_metadata={},
    )
    service, fake_agent = _service(response)

    with patch("app.services.agent_service.run_validation_pipeline", return_value=[]):
        result = asyncio.run(service.query_structured(
            "提升这面墙的纹理质感，让石材更真实",
            _blueprint(),
            selection=["wall_front"],
        ))

    assert result.error is None
    operation = result.patch["operations"][0]
    assert operation["op"] == "tune_material"
    assert operation["source_name"] == "stone_shared"
    assert operation["before"] == {
        "roughness": 0.55,
        "normalScale": 1,
        "uvScale": [1, 1],
    }
    prompt = fake_agent.payload["messages"][0]["content"]
    assert "只允许输出 `tune_material`" in prompt
    assert "/api/assets/" not in prompt


def test_query_material_optimization_requires_selection_before_llm_call():
    response = SimpleNamespace(content="", additional_kwargs={}, response_metadata={})
    service, fake_agent = _service(response)

    result = asyncio.run(service.query_structured(
        "优化当前材质纹理质量",
        _blueprint(),
        selection=[],
    ))

    assert "必须先选中" in result.error
    assert fake_agent.payload is None


def test_material_optimization_intent_is_narrow():
    assert _is_material_optimization_request("提升这面墙的纹理质感")
    assert not _is_material_optimization_request("介绍一下 PBR 材质")
    assert not _is_material_optimization_request("把墙体加厚")
