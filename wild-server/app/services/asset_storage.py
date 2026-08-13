"""内容寻址的 PBR 纹理集存储。

WILD 只保存 assetId、哈希、来源和 URL；图片本体由该存储层管理。
当前实现写入本地目录，公开 URL 前缀可通过 ASSETS__PUBLIC_BASE_URL
切换到对象存储或 CDN，而不改变 Blueprint 协议。
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from config import config


CHANNELS = {
    "baseColor": "srgb",
    "normal": "linear",
    "roughness": "linear",
    "metalness": "linear",
    "ambientOcclusion": "linear",
}
MATERIAL_CLASSES = {"stone", "concrete", "brick", "wood", "metal", "plaster", "tile", "fabric", "other"}
MATERIAL_ROLES = {
    "facade_primary", "facade_secondary", "structure", "floor", "frame",
    "door", "roof", "ground", "accent",
}
_ASSET_ID_RE = re.compile(r"^pbr_[0-9a-f]{24}$")
_HIDDEN_MARKER = ".library-hidden"


class AssetStorageError(ValueError):
    """上传内容或资产标识不符合约束。"""


def _detect_image(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    raise AssetStorageError("纹理文件必须是 PNG、JPEG 或 WebP 图片")


def _safe_text(value: str, field: str, maximum: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise AssetStorageError(f"{field} 不能为空")
    if len(normalized) > maximum:
        raise AssetStorageError(f"{field} 最长 {maximum} 个字符")
    return normalized


def _safe_terms(values: list[str] | None, field: str, maximum: int = 12) -> list[str]:
    terms: list[str] = []
    for value in values or []:
        normalized = re.sub(r"[^a-z0-9_-]+", "_", str(value).strip().lower()).strip("_")
        if not normalized or normalized in terms:
            continue
        if len(normalized) > 40:
            raise AssetStorageError(f"{field} 单项最长 40 个字符")
        terms.append(normalized)
        if len(terms) > maximum:
            raise AssetStorageError(f"{field} 最多 {maximum} 项")
    return terms


def _positive_pair(value: list[float] | tuple[float, float], field: str) -> list[float]:
    try:
        pair = [float(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise AssetStorageError(f"{field} 必须是两个正数") from exc
    if len(pair) != 2 or any(not 0 < item <= 1000 for item in pair):
        raise AssetStorageError(f"{field} 必须是两个 0–1000 的正数")
    return pair


def _unit_color(value: list[float] | tuple[float, float, float], field: str) -> list[float]:
    try:
        color = [float(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise AssetStorageError(f"{field} 必须是三个 0–1 数字") from exc
    if len(color) != 3 or any(not 0 <= item <= 1 for item in color):
        raise AssetStorageError(f"{field} 必须是三个 0–1 数字")
    return color


class LocalAssetStorage:
    """本地不可变资产目录；相同纹理通道内容自动去重。"""

    def __init__(
        self,
        root_dir: Path,
        public_base_url: str = "/api/assets",
        max_file_bytes: int = 20 * 1024 * 1024,
        max_total_bytes: int = 80 * 1024 * 1024,
    ) -> None:
        self.root_dir = root_dir.resolve()
        self.public_base_url = public_base_url.rstrip("/")
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes

    def prepare_pbr(
        self,
        maps: dict[str, dict[str, Any]],
        *,
        name: str,
        license_name: str,
        source_type: str = "local_upload",
        source_uri: str | None = None,
        material_class: str = "other",
        tags: list[str] | None = None,
        recommended_roles: list[str] | None = None,
        real_world_size_meters: list[float] | tuple[float, float] = (1.0, 1.0),
        roughness: float = 0.8,
        metallic: float = 0.0,
        base_color_tint: list[float] | tuple[float, float, float] = (1.0, 1.0, 1.0),
        normal_scale: float = 1.0,
        uv_scale: list[float] | tuple[float, float] = (1.0, 1.0),
    ) -> dict[str, Any]:
        """校验上传并生成确定性的内容 ID；此步骤不写磁盘。"""
        name = _safe_text(name, "name", 120)
        license_name = _safe_text(license_name, "license", 100)
        source_type = _safe_text(source_type, "source_type", 60)
        material_class = str(material_class or "other").strip().lower()
        if material_class not in MATERIAL_CLASSES:
            raise AssetStorageError(f"material_class 必须是: {', '.join(sorted(MATERIAL_CLASSES))}")
        safe_tags = _safe_terms(tags, "tags")
        safe_roles = _safe_terms(recommended_roles, "recommended_roles")
        unknown_roles = sorted(set(safe_roles) - MATERIAL_ROLES)
        if unknown_roles:
            raise AssetStorageError(f"recommended_roles 包含未知角色: {', '.join(unknown_roles)}")
        real_size = _positive_pair(real_world_size_meters, "real_world_size_meters")
        resolved_uv_scale = _positive_pair(uv_scale, "uv_scale")
        resolved_base_color_tint = _unit_color(base_color_tint, "base_color_tint")
        try:
            roughness = float(roughness)
            metallic = float(metallic)
            normal_scale = float(normal_scale)
        except (TypeError, ValueError) as exc:
            raise AssetStorageError("默认材质参数必须是数字") from exc
        if not 0 <= roughness <= 1 or not 0 <= metallic <= 1:
            raise AssetStorageError("roughness/metallic 必须在 0–1 范围")
        if not 0 <= normal_scale <= 4:
            raise AssetStorageError("normal_scale 必须在 0–4 范围")
        unknown = sorted(set(maps) - set(CHANNELS))
        if unknown:
            raise AssetStorageError(f"不支持的 PBR 通道: {', '.join(unknown)}")
        if "baseColor" not in maps:
            raise AssetStorageError("PBR 纹理集必须包含 baseColor")

        total_bytes = 0
        prepared_maps: dict[str, dict[str, Any]] = {}
        identity_parts: list[str] = []
        for channel in CHANNELS:
            upload = maps.get(channel)
            if upload is None:
                continue
            data = upload.get("data")
            if not isinstance(data, bytes) or not data:
                raise AssetStorageError(f"{channel} 文件为空")
            if len(data) > self.max_file_bytes:
                raise AssetStorageError(f"{channel} 超过单文件大小限制")
            total_bytes += len(data)
            if total_bytes > self.max_total_bytes:
                raise AssetStorageError("纹理集超过总大小限制")
            mime_type, extension = _detect_image(data)
            declared_type = str(upload.get("mime_type") or "").lower()
            if declared_type and declared_type not in {mime_type, "image/jpg"}:
                raise AssetStorageError(
                    f"{channel} 声明类型 {declared_type} 与文件内容 {mime_type} 不一致"
                )
            digest = hashlib.sha256(data).hexdigest()
            filename = f"{channel}{extension}"
            prepared_maps[channel] = {
                "data": data,
                "filename": filename,
                "mimeType": mime_type,
                "sha256": digest,
                "byteSize": len(data),
                "colorSpace": CHANNELS[channel],
            }
            identity_parts.append(f"{channel}:{digest}")

        identity_parts.append(json.dumps({
            "baseColorTint": resolved_base_color_tint,
            "roughness": roughness,
            "metallic": metallic,
            "normalScale": normal_scale,
            "uvScale": resolved_uv_scale,
        }, sort_keys=True, separators=(",", ":")))

        content_hash = hashlib.sha256("\n".join(identity_parts).encode("utf-8")).hexdigest()
        asset_id = f"pbr_{content_hash[:24]}"
        return {
            "assetId": asset_id,
            "contentHash": f"sha256:{content_hash}",
            "name": name,
            "license": license_name,
            "source": {
                "type": source_type,
                **({"uri": source_uri.strip()} if source_uri and source_uri.strip() else {}),
            },
            "classification": {
                "materialClass": material_class,
                "tags": safe_tags,
                "recommendedRoles": safe_roles,
            },
            "realWorldSizeMeters": real_size,
            "defaults": {
                "baseColorTint": resolved_base_color_tint,
                "roughness": roughness,
                "metallic": metallic,
                "normalScale": normal_scale,
                "uvScale": resolved_uv_scale,
            },
            "maps": prepared_maps,
        }

    def register_prepared(self, prepared: dict[str, Any]) -> dict[str, Any]:
        """原子写入已校验资产；已有相同内容时直接返回原清单。"""
        asset_id = str(prepared.get("assetId", ""))
        self._validate_asset_id(asset_id)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        target_dir = self.root_dir / asset_id
        manifest_path = target_dir / "manifest.json"
        if manifest_path.exists():
            (target_dir / _HIDDEN_MARKER).unlink(missing_ok=True)
            return self.get_manifest(asset_id)

        temp_dir = self.root_dir / f".tmp_{asset_id}_{uuid4().hex}"
        temp_dir.mkdir(parents=False, exist_ok=False)
        try:
            public_maps: dict[str, dict[str, Any]] = {}
            for channel, item in prepared["maps"].items():
                filename = item["filename"]
                (temp_dir / filename).write_bytes(item["data"])
                public_maps[channel] = {
                    "encoding": "url",
                    "uri": f"{self.public_base_url}/{asset_id}/files/{filename}",
                    "mimeType": item["mimeType"],
                    "sha256": item["sha256"],
                    "byteSize": item["byteSize"],
                    "colorSpace": item["colorSpace"],
                }
            manifest = {
                "schemaVersion": "1.0",
                "assetId": asset_id,
                "kind": "pbr_texture_set",
                "name": prepared["name"],
                "contentHash": prepared["contentHash"],
                "source": prepared["source"],
                "license": prepared["license"],
                "maps": public_maps,
                "classification": prepared.get("classification", {}),
                "realWorldSizeMeters": prepared.get("realWorldSizeMeters", [1.0, 1.0]),
                "defaults": prepared.get("defaults", {}),
                "createdAt": datetime.now(timezone.utc).isoformat(),
            }
            (temp_dir / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            try:
                temp_dir.rename(target_dir)
            except FileExistsError:
                return self.get_manifest(asset_id)
            return manifest
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

    def register_pbr(self, maps: dict[str, dict[str, Any]], **metadata: Any) -> dict[str, Any]:
        return self.register_prepared(self.prepare_pbr(maps, **metadata))

    def get_manifest(self, asset_id: str) -> dict[str, Any]:
        self._validate_asset_id(asset_id)
        path = self.root_dir / asset_id / "manifest.json"
        if not path.is_file():
            raise FileNotFoundError(asset_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def list_manifests(self) -> list[dict[str, Any]]:
        if not self.root_dir.exists():
            return []
        manifests: list[dict[str, Any]] = []
        for path in self.root_dir.glob("pbr_*/manifest.json"):
            if (path.parent / _HIDDEN_MARKER).exists():
                continue
            try:
                manifests.append(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        return sorted(manifests, key=lambda item: item.get("createdAt", ""), reverse=True)

    def hide_from_library(self, asset_id: str) -> None:
        """从素材库与 AI 候选清单隐藏资产，同时保留旧蓝图引用的文件。"""
        self._validate_asset_id(asset_id)
        asset_dir = self.root_dir / asset_id
        if not (asset_dir / "manifest.json").is_file():
            raise FileNotFoundError(asset_id)
        (asset_dir / _HIDDEN_MARKER).touch(exist_ok=True)

    def resolve_file(self, asset_id: str, filename: str) -> Path:
        self._validate_asset_id(asset_id)
        allowed_names = {
            f"{channel}{extension}"
            for channel in CHANNELS
            for extension in (".png", ".jpg", ".webp")
        }
        if filename not in allowed_names:
            raise AssetStorageError("不允许访问该资产文件")
        path = (self.root_dir / asset_id / filename).resolve()
        expected_parent = (self.root_dir / asset_id).resolve()
        if path.parent != expected_parent:
            raise AssetStorageError("资产路径越界")
        if not path.is_file():
            raise FileNotFoundError(filename)
        return path

    @staticmethod
    def _validate_asset_id(asset_id: str) -> None:
        if not _ASSET_ID_RE.fullmatch(asset_id):
            raise AssetStorageError("assetId 格式无效")


def create_asset_storage() -> LocalAssetStorage:
    server_root = Path(__file__).resolve().parents[2]
    root_dir = Path(config.assets.root_dir)
    if not root_dir.is_absolute():
        root_dir = server_root / root_dir
    if config.assets.backend != "local":
        raise RuntimeError(f"尚未配置资产存储后端: {config.assets.backend}")
    return LocalAssetStorage(
        root_dir,
        public_base_url=config.assets.public_base_url,
        max_file_bytes=config.assets.max_file_bytes,
        max_total_bytes=config.assets.max_total_bytes,
    )


asset_storage = create_asset_storage()
