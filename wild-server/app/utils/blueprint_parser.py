"""
Blueprint Parser —— LLM 回复解析 + 结构校验 + 文件保存

三个纯函数，职责单一：
  1. extract_blueprint_from_text() — 从 LLM 文本回复中提取 ```json 块
  2. validate_blueprint_schema()  — 轻量结构校验（不替代 spatial_tools 的空间校验）
  3. save_blueprint_file()        — 以时间戳文件名保存到磁盘

路径解析基于本文件位置，不依赖工作目录。
"""
import json
import re
import datetime
import math
from copy import deepcopy
from pathlib import Path

# ---------- 路径常量 ----------
_UTILS_DIR = Path(__file__).resolve().parent    # app/utils/
_APP_DIR = _UTILS_DIR.parent                     # app/
_SERVER_ROOT = _APP_DIR.parent                   # wild-server/
SCENES_DIR = _SERVER_ROOT / "storage" / "scenes"  # 后端自己的存储目录


# ---------- JSON 提取 ----------

def extract_blueprint_from_text(text: str) -> dict | None:
    """从 LLM 回复文本中提取第一个 ```json 代码块并解析为 dict

    支持的格式：
      ```json
      { ... }
      ```

    Returns:
        解析后的 dict，如果未找到或解析失败则返回 None
    """
    match = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def extract_patch_from_text(text: str) -> dict | None:
    """从 LLM 回复文本中提取 ScenePatch JSON

    ScenePatch 格式：
      ```json
      { "operations": [...], "summary": "..." }
      ```

    校验：返回的 dict 必须包含 "operations" 字段且为非空数组。

    Returns:
        解析后的 ScenePatch dict，如果未找到或解析失败或结构不对则返回 None
    """
    data = extract_blueprint_from_text(text)  # 复用 JSON 提取逻辑
    if data is None:
        return None
    if "operations" not in data:
        return None
    ops = data["operations"]
    if not isinstance(ops, list) or len(ops) == 0:
        return None
    # 确保有 summary
    if "summary" not in data:
        data["summary"] = "修改场景"
    return data


# ---------- 结构校验 ----------

def normalize_blueprint_input(blueprint: dict) -> dict:
    """将模型常见简写转换为标准 WILD 1.1 字段。"""
    normalized = deepcopy(blueprint)

    for material in normalized.get("materials", {}).values():
        if not isinstance(material, dict):
            continue
        if "baseColor" not in material:
            base_color = _parse_hex_color(material.get("color"))
            if base_color is not None:
                material["baseColor"] = base_color
        if "baseColor" in material:
            material.setdefault("roughness", 0.8)
            material.setdefault("metallic", 0.0)
            material.setdefault("albedo", 1.0)
            material["lightingCondition"] = "D65_noon"
            material.pop("color", None)

    elements = normalized.get("geometry", {}).get("elements", [])
    for element in elements:
        if not isinstance(element, dict):
            continue
        if element.get("type") == "opening" and element.get("style") in {"door", "window"}:
            role = element["style"]
            element["style"] = "rectangular"
            if element.get("height", 0) <= 0.1:
                element["height"] = 2.1 if role == "door" else 1.2
            if role == "window":
                start = element.get("from")
                if isinstance(start, list) and len(start) == 3 and start[1] <= 0.1:
                    start[1] = 0.9
        elif element.get("type") == "column" and element.get("style") == "round":
            element["style"] = "modern"

    return normalized


def _parse_hex_color(value: object) -> list[float] | None:
    if not isinstance(value, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", value) is None:
        return None
    return [
        int(value[1:3], 16) / 255,
        int(value[3:5], 16) / 255,
        int(value[5:7], 16) / 255,
    ]

def validate_blueprint_schema(blueprint: dict) -> list[str]:
    """轻量级 Blueprint 结构校验

    只检查基本结构完整性（meta/geometry/elements 存在性、ID 唯一性）。
    不做空间关系校验——那是 spatial_tools 的职责，LLM 在生成过程中已调用。

    Returns:
        问题描述列表，空列表表示通过
    """
    issues: list[str] = []

    if not isinstance(blueprint, dict):
        return ["Blueprint 必须是 JSON 对象 (dict)"]

    # meta
    if "meta" not in blueprint:
        issues.append("缺少顶层字段 'meta'")
    else:
        meta = blueprint["meta"]
        if not isinstance(meta, dict):
            issues.append("'meta' 必须是对象")
        else:
            if "version" not in meta:
                issues.append("meta.version 缺失")
            if "type" not in meta:
                issues.append("meta.type 缺失")
            if "name" not in meta:
                issues.append("meta.name 缺失")

    # geometry.elements
    if "geometry" not in blueprint:
        issues.append("缺少顶层字段 'geometry'")
    else:
        geo = blueprint["geometry"]
        if not isinstance(geo, dict):
            issues.append("'geometry' 必须是对象")
        elif "elements" not in geo:
            issues.append("geometry.elements 缺失")
        else:
            elements = geo["elements"]
            if not isinstance(elements, list):
                issues.append("geometry.elements 必须是数组")
            elif len(elements) == 0:
                issues.append("geometry.elements 为空——建筑至少需要一个构件")
            else:
                # ID 唯一性
                ids = [el.get("id", "") for el in elements if isinstance(el, dict)]
                dupes = {eid for eid in ids if ids.count(eid) > 1}
                if dupes:
                    issues.append(f"重复的构件 ID: {dupes}")
                # 每个元素必须有 type
                for el in elements:
                    if isinstance(el, dict) and "type" not in el:
                        issues.append(f"元素缺少 'type' 字段: id={el.get('id', '?')}")

    # materials
    materials = blueprint.get("materials", {})
    if not isinstance(materials, dict):
        issues.append("'materials' 必须是对象")
    else:
        for name, material in materials.items():
            if not isinstance(material, dict):
                issues.append(f"材质 '{name}' 必须是对象")
                continue
            base_color = material.get("baseColor")
            valid_base_color = (
                isinstance(base_color, list)
                and len(base_color) == 3
                and all(
                    isinstance(channel, (int, float))
                    and not isinstance(channel, bool)
                    and math.isfinite(channel)
                    and 0 <= channel <= 1
                    for channel in base_color
                )
            )
            if not valid_base_color:
                issues.append(
                    f"材质 '{name}'.baseColor 必须是 3 个 0–1 数值"
                )

    return issues


# ---------- 文件保存 ----------

def save_blueprint_file(blueprint: dict, directory: Path) -> str:
    """保存 Blueprint 到磁盘（时间戳命名）

    文件名格式: YYYY-MM-DD-HHMMSS.wild
    内容: 格式化 JSON (indent=2, ensure_ascii=False)

    Args:
        blueprint: Blueprint dict
        directory: 保存目录，不存在则自动创建

    Returns:
        保存文件的绝对路径字符串
    """
    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now()
    filename = now.strftime("%Y-%m-%d-%H%M%S") + ".wild"
    file_path = directory / filename
    file_path.write_text(
        json.dumps(blueprint, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return str(file_path.resolve())


def save_blueprint_file_as(blueprint: dict, directory: Path, filename: str) -> str:
    """保存 Blueprint 到磁盘（自定义文件名）

    用于场景持久化——相同文件名会被覆盖，实现同一场景的更新。

    Args:
        blueprint: Blueprint dict
        directory: 保存目录
        filename: 自定义文件名（如 "session_xxx.wild"）

    Returns:
        保存文件的绝对路径字符串
    """
    directory.mkdir(parents=True, exist_ok=True)
    file_path = directory / filename
    file_path.write_text(
        json.dumps(blueprint, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return str(file_path.resolve())
