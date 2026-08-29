"""受控风格包注册表：风格参数来自版本化 JSON，不来自自由模型坐标。"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


STYLE_PACKAGE_DIR = Path(__file__).resolve().parents[3] / "storage" / "style_packages"
_ALLOWED_ROOFS = {"gable", "hip", "dome", "flat", "chinese_curved", "chinese_pagoda"}
_ALLOWED_COLUMNS = {"doric", "ionic", "corinthian", "modern", "chinese_wooden"}


class StylePackageError(ValueError):
    pass


def _number(value: object, minimum: float, maximum: float, fallback: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return fallback
    return max(minimum, min(maximum, float(value)))


def _validate_package(raw: object, source: Path) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise StylePackageError(f"{source.name} 必须是 JSON 对象")
    package_id = str(raw.get("id") or "").strip()
    if not package_id or package_id != source.stem:
        raise StylePackageError(f"{source.name} 的 id 必须与文件名一致")
    roof = raw.get("roof") if isinstance(raw.get("roof"), dict) else {}
    roof_type = str(roof.get("type") or "flat")
    if roof_type not in _ALLOWED_ROOFS:
        raise StylePackageError(f"{source.name} 使用了不支持的屋顶类型 {roof_type}")
    decor = raw.get("decor") if isinstance(raw.get("decor"), dict) else {}
    columns = decor.get("facade_columns") if isinstance(decor.get("facade_columns"), dict) else {}
    column_style = str(columns.get("style") or "modern")
    if column_style not in _ALLOWED_COLUMNS:
        raise StylePackageError(f"{source.name} 使用了不支持的柱式 {column_style}")
    palette = raw.get("palette") if isinstance(raw.get("palette"), dict) else {}
    safe_palette: dict[str, list[float]] = {}
    for material_id in ("wall_finish", "roof", "accent", "glass", "metal"):
        color = palette.get(material_id)
        if isinstance(color, list) and len(color) == 3:
            safe_palette[material_id] = [
                _number(channel, 0.0, 1.0, 0.5) for channel in color
            ]
    return {
        "schema_version": "1.0",
        "id": package_id,
        "name": str(raw.get("name") or package_id)[:40],
        "description": str(raw.get("description") or "")[:240],
        "keywords": [str(item).lower() for item in raw.get("keywords", []) if str(item).strip()][:20],
        "tags": [str(item).lower() for item in raw.get("tags", []) if str(item).strip()][:20],
        "roof": {
            "type": roof_type,
            "height_ratio": _number(roof.get("height_ratio"), 0.01, 0.5, 0.12),
            "eave_curve_height": _number(roof.get("eave_curve_height"), 0.0, 3.0, 0.0),
        },
        "palette": safe_palette,
        "decor": {
            "cornice": {
                "enabled": bool((decor.get("cornice") or {}).get("enabled", True)),
                "width": _number((decor.get("cornice") or {}).get("width"), 0.05, 0.8, 0.2),
                "height": _number((decor.get("cornice") or {}).get("height"), 0.05, 0.6, 0.15),
            },
            "entrance_canopy": {
                "enabled": bool((decor.get("entrance_canopy") or {}).get("enabled", True)),
                "depth": _number((decor.get("entrance_canopy") or {}).get("depth"), 0.5, 3.0, 1.3),
                "thickness": _number((decor.get("entrance_canopy") or {}).get("thickness"), 0.08, 0.5, 0.15),
            },
            "facade_columns": {
                "enabled": bool(columns.get("enabled", False)),
                "style": column_style,
                "count": int(_number(columns.get("count"), 0, 8, 2)),
                "radius": _number(columns.get("radius"), 0.08, 0.5, 0.16),
            },
        },
    }


class StyleRegistry:
    def __init__(self, directory: Path = STYLE_PACKAGE_DIR):
        self.directory = Path(directory)

    def list(self) -> list[dict[str, Any]]:
        packages = [self._load(path) for path in sorted(self.directory.glob("*.json"))]
        if not packages:
            raise StylePackageError(f"没有可用风格包：{self.directory}")
        return packages

    def get(self, package_id: str) -> dict[str, Any]:
        safe_id = str(package_id).strip().lower()
        if not safe_id or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for char in safe_id):
            raise StylePackageError("风格包 ID 无效")
        path = self.directory / f"{safe_id}.json"
        if not path.is_file():
            raise StylePackageError(f"风格包不存在：{safe_id}")
        return self._load(path)

    def infer(self, text: str, default: str = "modern") -> str:
        normalized = str(text or "").lower()
        ranked = sorted(
            (
                (
                    sum(len(keyword) + 4 for keyword in package["keywords"] if keyword in normalized),
                    str(package["id"]),
                )
                for package in self.list()
            ),
            key=lambda item: (-item[0], item[1]),
        )
        return ranked[0][1] if ranked and ranked[0][0] > 0 else default

    def recommend(
        self,
        text: str,
        architecture_plan: dict[str, Any] | None = None,
        *,
        limit: int = 4,
        include_id: str = "",
    ) -> list[dict[str, Any]]:
        """按需求和已确认体量推荐风格，避免把全注册表当成固定单选题。"""

        normalized = str(text or "").lower()
        plan = architecture_plan if isinstance(architecture_plan, dict) else {}
        massing = plan.get("massing") if isinstance(plan.get("massing"), dict) else {}
        features = {
            str(plan.get("profile") or "").lower(),
            str(massing.get("shape") or "").lower(),
        }
        if plan.get("curtain_wall"):
            features.update({"curtain_wall", "glass"})
        if str(plan.get("profile") or "") == "high_rise":
            features.add("high_rise")
        packages = self.list()
        scored: list[tuple[int, int, str, dict[str, Any]]] = []
        for package in packages:
            keyword_score = sum(
                len(keyword) + 8
                for keyword in package["keywords"]
                if keyword and keyword in normalized
            )
            feature_score = sum(4 for tag in package["tags"] if tag in features)
            is_default = 1 if package["id"] == "modern" else 0
            scored.append((keyword_score + feature_score, is_default, str(package["id"]), package))
        scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
        selected = [
            item[3]
            for item in scored[:max(1, min(len(scored), int(limit)))]
        ]
        if include_id and all(item["id"] != include_id for item in selected):
            included = next((item for item in packages if item["id"] == include_id), None)
            if included:
                selected[-1] = included
        return selected

    @staticmethod
    def public_options(packages: list[dict[str, Any]]) -> list[dict[str, str]]:
        return [
            {"id": str(item["id"]), "name": str(item["name"]), "description": str(item["description"])}
            for item in packages
        ]

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StylePackageError(f"无法读取风格包 {path.name}: {exc}") from exc
        return deepcopy(_validate_package(raw, path))


style_registry = StyleRegistry()
