"""保护纹理物理尺寸与内容寻址之间的渲染契约。"""
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.services.asset_storage import LocalAssetStorage


def test_physical_dimensions_distinguish_texture_assets(tmp_path):
    storage = LocalAssetStorage(tmp_path)
    maps = {"baseColor": {"data": base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+iB9sAAAAASUVORK5CYII="
    )}}
    first = storage.prepare_pbr(maps, name="finish", license_name="test", real_world_size_meters=[1, 1])
    same = storage.prepare_pbr(maps, name="finish", license_name="test", real_world_size_meters=[1, 1])
    resized = storage.prepare_pbr(maps, name="finish", license_name="test", real_world_size_meters=[2, 4])
    assert first["assetId"] == same["assetId"]
    assert first["assetId"] != resized["assetId"]
    assert resized["realWorldSizeMeters"] == [2, 4]
    assert first["maps"]["baseColor"]["sha256"] == resized["maps"]["baseColor"]["sha256"]
