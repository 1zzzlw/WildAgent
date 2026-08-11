"""
Blueprint Parser —— LLM 回复解析 + 结构校验 + 文件保存

主要职责：
  1. extract_blueprint_from_text() — 从 LLM 文本回复中提取 ```json 块
  2. normalize_blueprint_input()  — 兼容模型常见简写并统一为 WILD 1.1 表达
  3. validate_blueprint_schema()  — 轻量结构校验（不替代 spatial_tools 的空间校验）
  4. save_blueprint_file*()       — 将最终 Blueprint 序列化到磁盘

解析、归一化和校验函数不修改调用方传入的数据；保存函数才产生文件系统副作用。
存储路径基于本文件位置计算，不依赖进程启动时的工作目录。
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
_SERVER_ROOT = _APP_DIR.parent                   # wild-server/ 或容器内 /app

# SCENES_DIR 优先从环境变量 WILD_SCENES_DIR 读取，方便在不同部署环境中覆盖。
# 容器内：WORKDIR=/app，挂载 $DEPLOY_DATA_DIR/scenes:/app/storage/scenes，
#          所以默认值 /app/storage/scenes 与 Jenkins 部署脚本一致。
# 本地开发：wild-server/storage/scenes（相对项目根推导）。
import os as _os
SCENES_DIR = Path(_os.environ.get("WILD_SCENES_DIR", "") or (_SERVER_ROOT / "storage" / "scenes"))

# 将 wild-core 暂不支持的模型常见叫法收敛到可渲染的 furniture subtype。
_FURNITURE_SUBTYPE_ALIASES = {
    "sofa": "chair",
    "counter": "table",
}


# ---------- JSON 提取 ----------

def _extract_json_values(text: str):
    """依次提取代码块和普通文本中的完整 JSON 对象或数组。"""
    if not isinstance(text, str) or not text.strip():
        return

    code_blocks = re.findall(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
    decoder = json.JSONDecoder()
    seen: set[str] = set()
    for source in [*code_blocks, text]:
        for match in re.finditer(r'[\{\[]', source):
            try:
                value, end = decoder.raw_decode(source[match.start():])
            except json.JSONDecodeError:
                continue
            if not isinstance(value, (dict, list)):
                continue
            raw = source[match.start():match.start() + end]
            if raw in seen:
                continue
            seen.add(raw)
            yield value


def _extract_json_dicts(text: str):
    """兼容旧调用方，只返回提取结果中的 JSON 对象。"""
    for value in _extract_json_values(text):
        if isinstance(value, dict):
            yield value


def extract_blueprint_from_text(text: str) -> dict | None:
    """从 fenced、未 fenced 或常见包装对象中提取完整 Blueprint。

    部分 OpenAI-compatible 模型会把要求的对象包装成
    ``{"blueprint": {...}}`` 或 ``{"result": {"blueprint": {...}}}``。
    只递归检查少量语义明确的包装字段，避免把 DESIGN_BRIEF 等普通对象误判为
    Blueprint。
    """
    for data in _extract_json_dicts(text):
        blueprint = _find_wrapped_blueprint(data)
        if blueprint is not None:
            return blueprint
    return None


def _find_wrapped_blueprint(data: object, depth: int = 0) -> dict | None:
    """在模型常见包装字段中查找 Blueprint，限制深度避免任意递归。"""
    if not isinstance(data, dict) or depth > 2:
        return None
    if isinstance(data.get("meta"), dict) and isinstance(data.get("geometry"), dict):
        return data

    wrapper_keys = {"blueprint", "skeleton_blueprint", "result", "data", "output"}
    for key, value in data.items():
        if str(key).lower() not in wrapper_keys:
            continue
        nested = _find_wrapped_blueprint(value, depth + 1)
        if nested is not None:
            return nested
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
    for data in _extract_json_values(text):
        patch = _find_wrapped_patch(data)
        if patch is not None:
            return patch
    return None


def _find_wrapped_patch(data: object, depth: int = 0) -> dict | None:
    """提取直接、包装或仅操作数组形式的 ScenePatch。"""
    if depth > 2:
        return None
    if isinstance(data, list):
        if data and all(
            isinstance(operation, dict)
            and isinstance(operation.get("op"), str)
            for operation in data
        ):
            return _normalize_scene_patch({
                "operations": data,
                "summary": "修改场景",
            })
        return None
    if not isinstance(data, dict):
        return None

    operations = data.get("operations")
    if isinstance(operations, list) and operations:
        patch = deepcopy(data)
        patch.setdefault("summary", "修改场景")
        return _normalize_scene_patch(patch)

    wrapper_keys = {
        "patch", "scene_patch", "scenepatch", "result", "data", "output",
    }
    for key, value in data.items():
        if str(key).lower() not in wrapper_keys:
            continue
        nested = _find_wrapped_patch(value, depth + 1)
        if nested is not None:
            return nested
    return None


def _normalize_scene_patch(patch: dict) -> dict:
    """把语义唯一的常见操作别名归一化为正式 ScenePatch 协议。"""
    normalized = deepcopy(patch)
    for operation in normalized.get("operations", []):
        if not isinstance(operation, dict):
            continue
        if operation.get("op") == "add_material":
            operation["op"] = "upsert_material"
            if "name" not in operation:
                material_id = operation.get("material_id") or operation.get("id")
                if isinstance(material_id, str) and material_id:
                    operation["name"] = material_id
            operation.pop("material_id", None)
            operation.pop("id", None)
    return normalized


# ---------- 结构校验 ----------

def normalize_blueprint_input(blueprint: dict) -> dict:
    """将模型常见简写转换为标准 WILD 1.1 字段。

    函数先深拷贝，所以修改返回值不会反向污染 LLM 原始输出。这里只做能够
    确定意图的兼容转换；无法可靠推断的缺失字段留给后续校验器报告。
    """
    normalized = deepcopy(blueprint)

    # ---------- 固定元数据补全 ----------
    # WILD 协议版本、文档类型和兜底名称不需要模型推理。让模型偶发漏掉这些
    # 非几何字段时继续进入昂贵的修复或直接阻断没有收益，因此在结构校验前
    # 确定性补齐；meta 类型本身非法时仍交给校验器报告。
    meta = normalized.get("meta")
    if isinstance(meta, dict):
        if not isinstance(meta.get("version"), str) or not meta["version"].strip():
            meta["version"] = "1.1"
        if not isinstance(meta.get("type"), str) or not meta["type"].strip():
            meta["type"] = "building"
        if not isinstance(meta.get("name"), str) or not meta["name"].strip():
            meta["name"] = "AI生成建筑"

    # ---------- 材质归一化 ----------
    for material in normalized.get("materials", {}).values():
        if not isinstance(material, dict):
            continue
        # 兼容模型常输出的 CSS 十六进制 ``color``，转换成 WILD 的线性范围数组。
        if "baseColor" not in material:
            base_color = _parse_hex_color(material.get("color"))
            if base_color is not None:
                material["baseColor"] = base_color
        if "baseColor" in material:
            # setdefault 保留模型明确给出的 PBR 参数，只补齐缺省值。
            material.setdefault("roughness", 0.8)
            material.setdefault("metallic", 0.0)
            material.setdefault("albedo", 1.0)
            # 当前渲染规范统一按 D65 正午光照解释材质颜色。
            material["lightingCondition"] = "D65_noon"
            # 标准字段已经就绪，删除不属于 WILD 1.1 的简写字段。
            material.pop("color", None)

    # ---------- 构件归一化 ----------
    elements = normalized.get("geometry", {}).get("elements", [])
    for element in elements:
        if not isinstance(element, dict):
            continue
        if element.get("type") == "wall":
            # 模型常用“水平 from/to + height”。WILD 1.1 则用 to.y 表达墙顶。
            start = element.get("from")
            end = element.get("to")
            height = element.get("height")
            if (
                isinstance(start, list)
                and isinstance(end, list)
                and len(start) == 3
                and len(end) == 3
                and isinstance(height, (int, float))
                and not isinstance(height, bool)
                and height > 0
                and abs(end[1] - start[1]) < 1e-6
            ):
                end[1] = start[1] + height
            # 无论能否完成转换都移除旧字段，让校验器暴露不完整坐标。
            element.pop("height", None)
        elif element.get("type") == "opening" and element.get("style") in {"door", "window"}:
            # door/window 是语义角色，不是当前 opening.style 的合法几何枚举。
            role = element["style"]
            element["style"] = "rectangular"
            # 只替换接近零的无效高度，保留模型给出的正常门窗尺寸。
            if element.get("height", 0) <= 0.1:
                element["height"] = 2.1 if role == "door" else 1.2
            if role == "window":
                start = element.get("from")
                # 窗台未给高度时抬到常用的 0.9m；门仍允许从墙底开始。
                if isinstance(start, list) and len(start) == 3 and start[1] <= 0.1:
                    start[1] = 0.9
        elif element.get("type") == "opening" and element.get("style") in {"double", "lattice"}:
            # 旧蓝图把门扇数量或窗格外观写进 opening.style；几何轮廓均为矩形。
            # 新蓝图的详细静态门窗应改用 geometry.components。
            element["style"] = "rectangular"
        elif element.get("type") == "column" and element.get("style") == "round":
            # round 描述截面形状，但不属于柱式枚举；modern 是最接近的兜底值。
            element["style"] = "modern"
        elif element.get("type") == "roof":
            # 兼容模型常用的建筑术语，统一转换为 WILD 1.1 标准枚举值
            roof_type = element.get("roofType")
            if roof_type in {"pitched", "sloped", "gabled"}:
                # pitched/sloped 是通用坡屋顶术语，默认映射为双坡（gable）
                element["roofType"] = "gable"
            elif roof_type in {"hipped"}:
                element["roofType"] = "hip"
            elif roof_type in {"shed", "mono-pitch"}:
                # 单坡屋顶在当前引擎中用 gable + 适当参数模拟
                element["roofType"] = "gable"
        elif element.get("type") == "furniture":
            subtype = element.get("subtype")
            if subtype in _FURNITURE_SUBTYPE_ALIASES:
                # 仅转换上面白名单中的已知别名，不猜测其他未知家具类型。
                element["subtype"] = _FURNITURE_SUBTYPE_ALIASES[subtype]
        elif element.get("type") == "primitive" and element.get("shape") == "box":
            dimensions = element.get("dimensions")
            if isinstance(dimensions, dict):
                # furniture 使用尺寸对象，而 primitive.box 的 WILD 1.1 标准格式是
                # [width, height, depth]。只在三个字段都明确且为正数时兼容转换，
                # 缺字段或非法数值继续交给校验器报告，避免猜测尺寸。
                ordered_dimensions = [
                    dimensions.get("width"),
                    dimensions.get("height"),
                    dimensions.get("depth"),
                ]
                if all(_is_positive_finite_number(value) for value in ordered_dimensions):
                    element["dimensions"] = ordered_dimensions

    # floor 的标准表达是两个三维角点。部分模型稳定输出坐标对象，或只给楼板 ID、
    # 厚度和材质；只要墙体已经明确给出建筑 X/Z 边界及各层底标高，就可以无歧义
    # 地恢复矩形楼板。无法从楼板自身或墙体确定范围时保持原值，让校验器继续报错。
    _normalize_floor_coordinates(elements)

    # ---------- 组合构件 from[1] 修正 ----------
    # 系统约定 component.from[1] 是世界坐标 Y，但模型常误用相对父墙底部的局部偏移。
    # 当 from[1] 明显小于父墙底部 Y（超过 0.5m）时，推断为局部坐标并加上 wallBottom。
    wall_bottom_map: dict[str, float] = {}
    for element in elements:
        if (
            isinstance(element, dict)
            and element.get("type") == "wall"
            and isinstance(element.get("id"), str)
            and isinstance(element.get("from"), list)
            and isinstance(element.get("to"), list)
            and len(element["from"]) == 3
            and len(element["to"]) == 3
        ):
            bottom = min(element["from"][1], element["to"][1])
            if math.isfinite(bottom):
                wall_bottom_map[element["id"]] = bottom

    _WALL_ATTACHED_TYPES = {"door", "window", "canopy", "balcony", "bay_window"}
    components = normalized.get("geometry", {}).get("components", [])
    for component in components:
        if not isinstance(component, dict):
            continue
        if component.get("type") not in _WALL_ATTACHED_TYPES:
            continue
        parent_wall = component.get("parentWall")
        if not isinstance(parent_wall, str) or parent_wall not in wall_bottom_map:
            continue
        wall_bottom = wall_bottom_map[parent_wall]
        if wall_bottom < 1e-6:
            continue  # 一楼墙无需修正
        from_coord = component.get("from")
        if not isinstance(from_coord, list) or len(from_coord) != 3:
            continue
        from_y = from_coord[1]
        if isinstance(from_y, (int, float)) and not isinstance(from_y, bool) and math.isfinite(from_y):
            if from_y < wall_bottom - 0.5:
                # 明确是局部偏移，补正为世界坐标
                component["from"] = [from_coord[0], wall_bottom + from_y, from_coord[2]]

    return normalized


def _parse_hex_color(value: object) -> list[float] | None:
    """把 ``#RRGGBB`` 转成三个 0–1 浮点通道；其他格式返回 None。"""
    if not isinstance(value, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", value) is None:
        return None
    return [
        int(value[1:3], 16) / 255,
        int(value[3:5], 16) / 255,
        int(value[5:7], 16) / 255,
    ]


def _is_finite_vector3(value: object) -> bool:
    """判断值是否为 JSON 可表示的三维有限数值坐标。"""
    return (
        isinstance(value, list)
        and len(value) == 3
        and all(
            isinstance(coordinate, (int, float))
            and not isinstance(coordinate, bool)
            and math.isfinite(coordinate)
            for coordinate in value
        )
    )


def _is_positive_finite_number(value: object) -> bool:
    """判断值是否为可安全用于几何尺寸的正有限数。"""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def _is_positive_vector3(value: object) -> bool:
    """判断值是否为 primitive.box 所需的三个正数尺寸。"""
    return (
        isinstance(value, list)
        and len(value) == 3
        and all(_is_positive_finite_number(dimension) for dimension in value)
    )


_PBR_CHANNEL_COLOR_SPACES = {
    "baseColor": "srgb",
    "normal": "linear",
    "roughness": "linear",
    "metalness": "linear",
    "ambientOcclusion": "linear",
}


def _validate_asset_image(value: object, path: str) -> list[str]:
    """校验 WILD 中的 URL 纹理引用，不允许把新资产内嵌为 Base64。"""
    if not isinstance(value, dict):
        return [f"{path} 必须是 URL 图片引用对象"]
    issues: list[str] = []
    if value.get("encoding") != "url":
        issues.append(f"{path}.encoding 必须是 url")
    uri = value.get("uri")
    valid_uri = (
        isinstance(uri, str)
        and bool(uri.strip())
        and (
            re.fullmatch(r"https?://[^\s]+", uri.strip()) is not None
            or (uri.startswith("/") and not uri.startswith("//"))
        )
    )
    if not valid_uri:
        issues.append(f"{path}.uri 必须是站内绝对路径或 http(s) URL")
    if value.get("mimeType") not in {"image/png", "image/jpeg", "image/webp"}:
        issues.append(f"{path}.mimeType 必须是 PNG/JPEG/WebP")
    digest = value.get("sha256")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        issues.append(f"{path}.sha256 必须是 64 位小写十六进制摘要")
    byte_size = value.get("byteSize")
    if byte_size is not None and (
        not isinstance(byte_size, int) or isinstance(byte_size, bool) or byte_size <= 0
    ):
        issues.append(f"{path}.byteSize 必须是正整数")
    return issues


def _as_finite_vector3(value: object) -> list[int | float] | None:
    """兼容模型常见的 ``[x,y,z]`` 和 ``{x,y,z}`` 坐标表达。"""
    if isinstance(value, (list, tuple)) and len(value) == 3:
        coordinates = list(value)
    elif isinstance(value, dict):
        coordinates = [
            value.get("x", value.get("X")),
            value.get("y", value.get("Y")),
            value.get("z", value.get("Z")),
        ]
    else:
        return None

    if all(
        isinstance(coordinate, (int, float))
        and not isinstance(coordinate, bool)
        and math.isfinite(coordinate)
        for coordinate in coordinates
    ):
        return coordinates
    return None


def _normalize_floor_coordinates(elements: list) -> None:
    """把可确定恢复的矩形楼板坐标统一为 WILD ``from/to``。

    恢复边界优先使用骨架墙体的 X/Z 包围盒，因为骨架 Prompt 明确要求楼板覆盖
    整个建筑底面；楼板标高优先使用自身坐标/显式 elevation，其次按楼板顺序
    对应墙体底标高。没有墙体或有效角点时不创建坐标。
    """
    walls: list[tuple[list[int | float], list[int | float]]] = []
    floors: list[dict] = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        if element.get("type") == "wall":
            start = _as_finite_vector3(element.get("from"))
            end = _as_finite_vector3(element.get("to"))
            if start is not None and end is not None:
                walls.append((start, end))
        elif element.get("type") == "floor":
            floors.append(element)

    wall_bounds: tuple[int | float, int | float, int | float, int | float] | None = None
    wall_levels: list[int | float] = []
    if walls:
        xs = [coordinate for start, end in walls for coordinate in (start[0], end[0])]
        zs = [coordinate for start, end in walls for coordinate in (start[2], end[2])]
        min_x, max_x = min(xs), max(xs)
        min_z, max_z = min(zs), max(zs)
        if max_x - min_x >= 0.1 and max_z - min_z >= 0.1:
            wall_bounds = (min_x, max_x, min_z, max_z)
        wall_levels = sorted({min(start[1], end[1]) for start, end in walls})

    for index, floor in enumerate(floors):
        start = _as_finite_vector3(floor.get("from"))
        end = _as_finite_vector3(floor.get("to"))
        if start is not None and end is not None:
            floor["from"] = start
            floor["to"] = end
            continue

        elevation = None
        if start is not None:
            elevation = start[1]
        elif end is not None:
            elevation = end[1]
        else:
            for field in ("elevation", "baseY", "y"):
                value = floor.get(field)
                if (
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and math.isfinite(value)
                ):
                    elevation = value
                    break
        if elevation is None and wall_levels:
            elevation = wall_levels[min(index, len(wall_levels) - 1)]

        if wall_bounds is None or elevation is None:
            # 没有可靠建筑边界时不根据 ID 或常见尺寸盲猜。
            if start is not None:
                floor["from"] = start
            if end is not None:
                floor["to"] = end
            continue

        min_x, max_x, min_z, max_z = wall_bounds
        floor["from"] = [min_x, elevation, min_z]
        floor["to"] = [max_x, elevation, max_z]
        # 仅在成功生成标准坐标后移除已被吸收的非标准标高字段。
        floor.pop("elevation", None)
        floor.pop("baseY", None)
        floor.pop("y", None)


def validate_blueprint_schema(blueprint: dict) -> list[str]:
    """轻量级 Blueprint 结构校验

    只检查基本结构完整性（meta/geometry/elements 存在性、ID 唯一性）。
    不做空间关系校验——那是 spatial_tools 的职责，LLM 在生成过程中已调用。

    Returns:
        问题描述列表，空列表表示通过
    """
    issues: list[str] = []

    if not isinstance(blueprint, dict):
        # 顶层类型不正确时无法安全继续读取子字段，立即返回。
        return ["Blueprint 必须是 JSON 对象 (dict)"]

    # ---------- 顶层元数据 ----------
    if "meta" not in blueprint:
        issues.append("缺少顶层字段 'meta'")
    else:
        meta = blueprint["meta"]
        if not isinstance(meta, dict):
            issues.append("'meta' 必须是对象")
        else:
            if "version" not in meta:
                issues.append("`meta.version` 缺失")
            if "type" not in meta:
                issues.append("`meta.type` 缺失")
            if "name" not in meta:
                issues.append("`meta.name` 缺失")

    # ---------- 几何容器与构件基本身份 ----------
    if "geometry" not in blueprint:
        issues.append("缺少顶层字段 'geometry'")
    else:
        geo = blueprint["geometry"]
        if not isinstance(geo, dict):
            issues.append("'geometry' 必须是对象")
        else:
            elements = geo.get("elements")
            components = geo.get("components", [])
            if not isinstance(elements, list):
                issues.append("geometry.elements 必须是数组")
                elements = []
            if not isinstance(components, list):
                issues.append("geometry.components 必须是数组")
                components = []
            if len(elements) == 0 and len(components) == 0:
                issues.append("geometry.elements 和 geometry.components 不能同时为空")

            # 基础元素和高级组件共享同一个 ID 命名空间，避免编译后冲突。
            ids = [
                item.get("id", "")
                for item in [*elements, *components]
                if isinstance(item, dict)
            ]
            dupes = {item_id for item_id in ids if item_id and ids.count(item_id) > 1}
            if dupes:
                issues.append(f"重复的构件 ID: {dupes}")

            # 更细的基础元素必填字段由 spatial_tools 中的校验器负责。
            for el in elements:
                if not isinstance(el, dict):
                    issues.append("geometry.elements 中的每一项都必须是对象")
                    continue
                element_id = el.get("id", "?")
                if not el.get("id"):
                    issues.append("元素缺少非空 'id' 字段")
                if "type" not in el:
                    issues.append(f"元素缺少 'type' 字段: id={element_id}")
                if (
                    el.get("type") == "primitive"
                    and el.get("shape") == "box"
                    and not _is_positive_vector3(el.get("dimensions"))
                ):
                    issues.append(
                        f"{element_id}.dimensions 必须是 "
                        "[width, height, depth] 三个正有限数字"
                    )
                for coordinate_field in ("from", "to"):
                    if (
                        coordinate_field in el
                        and not _is_finite_vector3(el[coordinate_field])
                    ):
                        issues.append(
                            f"{element_id}.{coordinate_field} 必须是包含 3 个有限数字的数组"
                        )

            component_required = {
                "door": ("parentWall", "from", "width", "height"),
                "window": ("parentWall", "from", "width", "height"),
                "railing": ("path", "height"),
                "canopy": ("parentWall", "from", "width", "depth", "thickness"),
                "balcony": ("parentWall", "from", "width", "depth", "slabThickness"),
                "ramp": ("from", "to", "width", "thickness"),
                "bay_window": ("parentWall", "from", "width", "height", "projectionDepth"),
                "cornice": ("path", "profile"),
                "chimney": ("position", "width", "depth", "height"),
                "light": ("position",),
            }
            component_allowed = {
                "door": {
                    "type", "id", "parentWall", "from", "width", "height",
                    "frameWidth", "frameDepth", "leafDepth", "frameMaterial", "leafMaterial",
                    "interaction", "openingStyle", "doorStyle", "draggable",
                },
                "window": {
                    "type", "id", "parentWall", "from", "width", "height",
                    "frameWidth", "frameDepth", "glassDepth", "verticalMullions",
                    "horizontalMullions", "frameMaterial", "glassMaterial",
                    "interaction", "draggable",
                },
                "railing": {
                    "type", "id", "path", "height", "postSpacing", "postRadius",
                    "railRadius", "railLevels", "material", "parentFloor", "draggable",
                },
                "canopy": {
                    "type", "id", "parentWall", "from", "width", "depth",
                    "thickness", "supportCount", "supportSize", "material",
                    "supportMaterial", "draggable",
                },
                "balcony": {
                    "type", "id", "parentWall", "from", "width", "depth",
                    "slabThickness", "railingHeight", "postSpacing", "material",
                    "railingMaterial", "draggable",
                },
                "ramp": {
                    "type", "id", "from", "to", "width", "thickness",
                    "railingSides", "railingHeight", "postSpacing", "material",
                    "railingMaterial", "parentFloor", "draggable",
                },
                "bay_window": {
                    "type", "id", "parentWall", "from", "width", "height",
                    "projectionDepth", "frameWidth", "frameDepth", "frameMaterial",
                    "glassMaterial", "draggable",
                },
                "cornice": {
                    "type", "id", "path", "profile", "closedProfile", "material",
                    "parentRoof", "draggable",
                },
                "chimney": {
                    "type", "id", "position", "width", "depth", "height",
                    "wallThickness", "capHeight", "material", "capMaterial",
                    "parentRoof", "draggable",
                },
                "light": {
                    "type", "id", "position", "fixtureType", "lightType", "color",
                    "lowIntensity", "highIntensity", "distance", "angle",
                    "initiallyOn", "bulbRadius", "baseHeight", "height",
                    "shadeRadius", "material", "baseMaterial", "shadeMaterial",
                    "draggable",
                },
            }
            for component in components:
                if not isinstance(component, dict):
                    issues.append("geometry.components 中的每一项都必须是对象")
                    continue
                component_id = component.get("id", "?")
                component_type = component.get("type")
                if not component.get("id"):
                    issues.append("组合构件缺少非空 'id' 字段")
                if component_type not in component_required:
                    issues.append(
                        f"组合构件 {component_id}.type 必须是 "
                        f"{'/'.join(component_required)}"
                    )
                    continue
                unknown_fields = sorted(
                    set(component) - component_allowed[component_type]
                )
                if unknown_fields:
                    issues.append(
                        f"组合构件 {component_id} 包含不支持的字段: {unknown_fields}"
                    )
                for field in component_required[component_type]:
                    if field not in component:
                        issues.append(f"组合构件 {component_id} 缺少字段 '{field}'")
                if component_type in {"door", "window", "canopy", "balcony", "bay_window"}:
                    if not _is_finite_vector3(component.get("from")):
                        issues.append(f"组合构件 {component_id}.from 必须是三维有限数组")
                    positive_fields = {
                        "door": ("width", "height"),
                        "window": ("width", "height"),
                        "canopy": ("width", "depth", "thickness"),
                        "balcony": ("width", "depth", "slabThickness"),
                        "bay_window": ("width", "height", "projectionDepth"),
                    }[component_type]
                    for field in positive_fields:
                        if not _is_positive_finite_number(component.get(field)):
                            issues.append(f"组合构件 {component_id}.{field} 必须是正有限数字")
                    optional_positive_fields = {
                        "door": ("frameDepth", "leafDepth"),
                        "window": ("frameDepth", "glassDepth"),
                        "canopy": (),
                        "balcony": (),
                        "bay_window": ("frameDepth",),
                    }[component_type]
                    for field in optional_positive_fields:
                        if field in component and not _is_positive_finite_number(component.get(field)):
                            issues.append(f"组合构件 {component_id}.{field} 必须是正有限数字")
                elif component_type in {"railing", "cornice"}:
                    path_points = component.get("path")
                    if (
                        not isinstance(path_points, list)
                        or len(path_points) < 2
                        or not all(_is_finite_vector3(point) for point in path_points)
                    ):
                        issues.append(f"组合构件 {component_id}.path 至少需要两个三维有限坐标")
                    if component_type == "railing" and not _is_positive_finite_number(component.get("height")):
                        issues.append(f"组合构件 {component_id}.height 必须是正有限数字")
                elif component_type == "ramp":
                    for field in ("from", "to"):
                        if not _is_finite_vector3(component.get(field)):
                            issues.append(f"组合构件 {component_id}.{field} 必须是三维有限数组")
                    for field in ("width", "thickness"):
                        if not _is_positive_finite_number(component.get(field)):
                            issues.append(f"组合构件 {component_id}.{field} 必须是正有限数字")
                elif component_type in {"chimney", "light"}:
                    if not _is_finite_vector3(component.get("position")):
                        issues.append(f"组合构件 {component_id}.position 必须是三维有限数组")
                    required_numbers = ("width", "depth", "height") if component_type == "chimney" else ()
                    for field in required_numbers:
                        if not _is_positive_finite_number(component.get(field)):
                            issues.append(f"组合构件 {component_id}.{field} 必须是正有限数字")
                    if component_type == "light":
                        if component.get("fixtureType", "bulb") not in {"bulb", "table_lamp"}:
                            issues.append(f"组合构件 {component_id}.fixtureType 必须是 bulb/table_lamp")
                        if component.get("lightType", "point") not in {"point", "spot"}:
                            issues.append(f"组合构件 {component_id}.lightType 必须是 point/spot")

    # ---------- PBR 资产清单 ----------
    assets = blueprint.get("assets", {})
    if not isinstance(assets, dict):
        issues.append("'assets' 必须是对象")
        assets = {}
    else:
        for asset_id, asset in assets.items():
            path = f"assets.{asset_id}"
            if re.fullmatch(r"pbr_[0-9a-f]{24}", str(asset_id)) is None:
                issues.append(f"{path} 的 assetId key 格式无效")
            if not isinstance(asset, dict):
                issues.append(f"{path} 必须是对象")
                continue
            if asset.get("assetId") != asset_id:
                issues.append(f"{path}.assetId 必须与资产 key 一致")
            if asset.get("kind") != "pbr_texture_set":
                issues.append(f"{path}.kind 必须是 pbr_texture_set")
            content_hash = asset.get("contentHash")
            if (
                not isinstance(content_hash, str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", content_hash) is None
            ):
                issues.append(f"{path}.contentHash 格式无效")
            if not isinstance(asset.get("license"), str) or not asset["license"].strip():
                issues.append(f"{path}.license 不能为空")
            maps = asset.get("maps")
            if not isinstance(maps, dict):
                issues.append(f"{path}.maps 必须是对象")
                continue
            if "baseColor" not in maps:
                issues.append(f"{path}.maps.baseColor 缺失")
            unknown_channels = sorted(set(maps) - set(_PBR_CHANNEL_COLOR_SPACES))
            if unknown_channels:
                issues.append(f"{path}.maps 包含不支持的通道: {unknown_channels}")
            for channel, image in maps.items():
                image_path = f"{path}.maps.{channel}"
                issues.extend(_validate_asset_image(image, image_path))
                if (
                    channel in _PBR_CHANNEL_COLOR_SPACES
                    and isinstance(image, dict)
                    and image.get("colorSpace") != _PBR_CHANNEL_COLOR_SPACES[channel]
                ):
                    issues.append(
                        f"{image_path}.colorSpace 必须是 "
                        f"{_PBR_CHANNEL_COLOR_SPACES[channel]}"
                    )

    # ---------- 材质结构与颜色通道 ----------
    materials = blueprint.get("materials", {})
    if not isinstance(materials, dict):
        issues.append("'materials' 必须是对象")
    else:
        for name, material in materials.items():
            if not isinstance(material, dict):
                issues.append(f"材质 '{name}' 必须是对象")
                continue
            base_color = material.get("baseColor")
            # bool 是 int 的子类，必须显式排除，避免 true/false 被当作 1/0。
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
            for field in (
                "roughness", "metallic", "albedo", "opacity", "transmission",
                "clearcoat", "clearcoatRoughness", "sheen",
            ):
                value = material.get(field)
                if value is not None and (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(value)
                    or not 0 <= value <= 1
                ):
                    issues.append(f"材质 '{name}'.{field} 必须是 0–1 有限数字")
            material_class = material.get("materialClass")
            if material_class is not None and material_class not in {
                "standard", "glass", "clearcoat", "fabric",
            }:
                issues.append(
                    f"材质 '{name}'.materialClass 必须是 standard/glass/clearcoat/fabric"
                )
            if material.get("side") not in {None, "front", "double"}:
                issues.append(f"材质 '{name}'.side 必须是 front/double")
            ior = material.get("ior")
            if ior is not None and (
                not isinstance(ior, (int, float))
                or isinstance(ior, bool)
                or not math.isfinite(ior)
                or not 1 <= ior <= 2.333
            ):
                issues.append(f"材质 '{name}'.ior 必须是 1–2.333 有限数字")
            for field in ("thickness", "attenuationDistance", "emissiveIntensity"):
                value = material.get(field)
                if value is not None and (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(value)
                    or value < 0
                ):
                    issues.append(f"材质 '{name}'.{field} 必须是非负有限数字")
            if material_class == "glass":
                if not isinstance(material.get("transmission"), (int, float)) or material.get("transmission", 0) <= 0:
                    issues.append(f"材质 '{name}' 的物理玻璃必须提供 transmission > 0")
                if material.get("opacity", 1) != 1:
                    issues.append(f"材质 '{name}' 的物理玻璃 opacity 必须为 1 或省略")
            texture_set = material.get("textureSet")
            if texture_set is not None and (
                not isinstance(texture_set, str) or texture_set not in assets
            ):
                issues.append(
                    f"材质 '{name}'.textureSet 引用了不存在的资产: {texture_set}"
                )

    return issues


# ---------- 文件保存 ----------

def _safe_name_slug(name: str, max_len: int = 40) -> str:
    """将 meta.name 转换为安全的文件名片段。

    保留中文、字母、数字和下划线，其余字符替换为 _，并截断到 max_len。
    """
    slug = re.sub(r"[^\w\u4e00-\u9fff]", "_", name, flags=re.UNICODE)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:max_len] if slug else "unnamed"


def save_blueprint_file(blueprint: dict, directory: Path) -> str:
    """保存 Blueprint 到磁盘（日期子目录 + 时间戳命名）

    文件路径格式: <directory>/YYYY-MM-DD/HHMMSS_<meta.name>.wild
    内容: 格式化 JSON (indent=2, ensure_ascii=False)

    Args:
        blueprint: Blueprint dict
        directory: 根保存目录，日期子目录自动创建

    Returns:
        保存文件的绝对路径字符串
    """
    now = datetime.datetime.now()
    date_dir = directory / now.strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)

    name_slug = _safe_name_slug(blueprint.get("meta", {}).get("name", ""))
    filename = now.strftime("%H%M%S") + (f"_{name_slug}" if name_slug else "") + ".wild"
    file_path = date_dir / filename
    file_path.write_text(
        json.dumps(blueprint, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return str(file_path.resolve())


def save_blueprint_file_as(blueprint: dict, directory: Path, rel_path: str) -> str:
    """保存 Blueprint 到磁盘（自定义相对路径）

    rel_path 可以是：
      - 旧格式 "session_xxx.wild"（直接放在 directory 下）
      - 新格式 "2026-08-02/session_xxx_名称.wild"（日期子目录）

    相同路径会被覆盖，实现同一会话的持续更新。

    Args:
        blueprint: Blueprint dict
        directory: 根目录（路径边界校验由 API 层负责）
        rel_path: 相对于 directory 的路径

    Returns:
        保存文件的绝对路径字符串
    """
    file_path = directory / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        json.dumps(blueprint, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return str(file_path.resolve())
