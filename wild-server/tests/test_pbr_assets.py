import asyncio
import json
from io import BytesIO
from copy import deepcopy

import pytest
from starlette.datastructures import Headers, UploadFile

from app.api import assets as assets_api
from app.agent.asset_graph import run_asset_workflow
from app.services.agent_service import (
    _apply_patch_to_blueprint,
    _validate_scene_patch_operations,
)
from app.services.asset_storage import AssetStorageError, LocalAssetStorage
from app.utils.blueprint_parser import validate_blueprint_schema


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"pbr-test-payload"


def _storage(tmp_path) -> LocalAssetStorage:
    return LocalAssetStorage(tmp_path / "assets", public_base_url="/api/assets")


def _blueprint() -> dict:
    return {
        "meta": {"version": "1.1", "type": "building", "name": "PBR test"},
        "geometry": {
            "elements": [{
                "id": "wall_1",
                "type": "wall",
                "from": [0, 0, 0],
                "to": [4, 3, 0],
                "thickness": 0.2,
                "material": "plain",
            }],
            "components": [],
        },
        "materials": {
            "plain": {
                "baseColor": [0.8, 0.8, 0.8],
                "roughness": 0.8,
                "metallic": 0,
                "albedo": 1,
                "lightingCondition": "D65_noon",
            }
        },
    }


def test_local_storage_registers_immutable_content_addressed_asset(tmp_path):
    storage = _storage(tmp_path)
    maps = {"baseColor": {"data": PNG_BYTES, "mime_type": "image/png"}}

    first = storage.register_pbr(
        maps,
        name="Stone",
        license_name="CC0",
    )
    second = storage.register_pbr(
        maps,
        name="Stone",
        license_name="CC0",
    )

    assert first == second
    assert first["assetId"].startswith("pbr_")
    assert first["contentHash"].startswith("sha256:")
    assert first["maps"]["baseColor"]["uri"].startswith("/api/assets/pbr_")
    assert first["maps"]["baseColor"]["encoding"] == "url"
    assert first["classification"]["materialClass"] == "other"
    assert first["realWorldSizeMeters"] == [1.0, 1.0]
    assert first["defaults"]["baseColorTint"] == [1.0, 1.0, 1.0]
    assert first["defaults"]["normalScale"] == 1.0
    assert list(first["maps"]) == ["baseColor"]
    assert storage.resolve_file(first["assetId"], "baseColor.png").read_bytes() == PNG_BYTES


def test_local_storage_rejects_non_image_bytes(tmp_path):
    storage = _storage(tmp_path)
    with pytest.raises(AssetStorageError, match="PNG、JPEG 或 WebP"):
        storage.prepare_pbr(
            {"baseColor": {"data": b"not-an-image", "mime_type": "image/png"}},
            name="Invalid",
            license_name="User supplied",
        )


def test_same_image_can_store_reusable_material_parameter_variants(tmp_path):
    storage = _storage(tmp_path)
    maps = {"baseColor": {"data": PNG_BYTES, "mime_type": "image/png"}}

    neutral = storage.register_pbr(
        maps,
        name="Stone Neutral",
        license_name="CC0",
    )
    warm = storage.register_pbr(
        maps,
        name="Stone Warm",
        license_name="CC0",
        base_color_tint=(0.9, 0.7, 0.5),
        roughness=0.65,
    )

    assert neutral["assetId"] != warm["assetId"]
    assert warm["defaults"]["baseColorTint"] == [0.9, 0.7, 0.5]
    assert warm["defaults"]["roughness"] == 0.65
    assert len(storage.list_manifests()) == 2


def test_manifest_urls_follow_current_public_path_and_fill_new_defaults(tmp_path):
    original = LocalAssetStorage(tmp_path / "assets", public_base_url="/old/assets")
    asset = original.register_pbr(
        {"baseColor": {"data": PNG_BYTES, "mime_type": "image/png"}},
        name="Legacy Stone",
        license_name="CC0",
    )
    manifest_path = original.root_dir / asset["assetId"] / "manifest.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["defaults"].pop("baseColorTint", None)
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")

    current = LocalAssetStorage(tmp_path / "assets", public_base_url="/api/assets")
    migrated = current.get_manifest(asset["assetId"])

    assert migrated["maps"]["baseColor"]["uri"] == (
        f"/api/assets/{asset['assetId']}/files/baseColor.png"
    )
    assert migrated["defaults"]["baseColorTint"] == [1.0, 1.0, 1.0]
    assert current.list_manifests()[0]["maps"]["baseColor"]["uri"].startswith("/api/assets/")


def test_hiding_asset_removes_it_from_library_but_keeps_existing_scene_urls(tmp_path):
    storage = _storage(tmp_path)
    maps = {"baseColor": {"data": PNG_BYTES, "mime_type": "image/png"}}
    asset = storage.register_pbr(maps, name="Stone", license_name="CC0")

    storage.hide_from_library(asset["assetId"])

    assert storage.list_manifests() == []
    assert storage.get_manifest(asset["assetId"])["assetId"] == asset["assetId"]
    assert storage.resolve_file(asset["assetId"], "baseColor.png").read_bytes() == PNG_BYTES

    restored = storage.register_pbr(maps, name="Stone", license_name="CC0")
    assert restored["assetId"] == asset["assetId"]
    assert [item["assetId"] for item in storage.list_manifests()] == [asset["assetId"]]


def test_asset_graph_produces_asset_then_material_patch(tmp_path):
    storage = _storage(tmp_path)
    result = asyncio.run(run_asset_workflow(
        {
            "name": "Brick",
            "materialName": "brick_pbr",
            "license": "CC0",
            "roughness": 0.7,
            "metallic": 0,
            "baseColorTint": [0.8, 0.6, 0.4],
            "uvScale": [2, 2],
            "baseRevision": 3,
        },
        {"baseColor": {"data": PNG_BYTES, "mime_type": "image/png"}},
        storage,
    ))

    assert "error" not in result
    assert [step["node"] for step in result["trace"]] == [
        "extract_material_intent",
        "validate_asset",
        "register_asset",
        "propose_wild_patch",
    ]
    patch = result["patch"]
    assert patch["base_revision"] == 3
    assert [operation["op"] for operation in patch["operations"]] == [
        "upsert_asset",
        "upsert_material",
    ]
    assert patch["operations"][1]["material"]["textureSet"] == result["asset"]["assetId"]
    assert patch["operations"][1]["material"]["baseColor"] == [0.8, 0.6, 0.4]
    assert result["asset"]["defaults"]["baseColorTint"] == [0.8, 0.6, 0.4]


def test_pbr_patch_preflight_and_blueprint_schema_close_references(tmp_path):
    storage = _storage(tmp_path)
    result = asyncio.run(run_asset_workflow(
        {"name": "Wood", "materialName": "wood_pbr", "license": "CC0"},
        {"baseColor": {"data": PNG_BYTES, "mime_type": "image/png"}},
        storage,
    ))
    blueprint = _blueprint()
    patch = result["patch"]

    assert _validate_scene_patch_operations(blueprint, patch) == []
    patched = _apply_patch_to_blueprint(blueprint, patch)
    assert validate_blueprint_schema(patched) == []

    dangling = deepcopy(patched)
    dangling["materials"]["wood_pbr"]["textureSet"] = "pbr_000000000000000000000000"
    assert any("不存在的资产" in issue for issue in validate_blueprint_schema(dangling))

    embedded = deepcopy(patched)
    embedded_asset = next(iter(embedded["assets"].values()))
    embedded_asset["maps"]["baseColor"] = {
        "encoding": "base64",
        "mimeType": "image/png",
        "data": "AAAA",
    }
    issues = validate_blueprint_schema(embedded)
    assert any("encoding 必须是 url" in issue for issue in issues)


def test_pbr_upload_api_returns_patch_and_immutable_file(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    monkeypatch.setattr(assets_api, "asset_storage", storage)
    upload = UploadFile(
        BytesIO(PNG_BYTES),
        filename="stone.png",
        headers=Headers({"content-type": "image/png"}),
    )

    response = asyncio.run(assets_api.upload_pbr_asset(
        name="Stone",
        material_name="stone_pbr",
        license_name="CC0",
        base_revision=2,
        base_color=upload,
    ))
    body = json.loads(response.body)

    assert response.status_code == 200
    assert body["patch"]["base_revision"] == 2
    assert body["trace"][-1]["node"] == "propose_wild_patch"
    file_response = asyncio.run(assets_api.get_asset_file(
        body["asset"]["assetId"],
        "baseColor.png",
    ))
    assert file_response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_delete_api_hides_asset_without_deleting_files(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    monkeypatch.setattr(assets_api, "asset_storage", storage)
    asset = storage.register_pbr(
        {"baseColor": {"data": PNG_BYTES, "mime_type": "image/png"}},
        name="Stone",
        license_name="CC0",
    )

    response = asyncio.run(assets_api.hide_asset(asset["assetId"]))

    assert response is None
    assert storage.list_manifests() == []
    assert storage.resolve_file(asset["assetId"], "baseColor.png").is_file()
