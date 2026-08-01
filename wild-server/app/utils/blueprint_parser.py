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
_SERVER_ROOT = _APP_DIR.parent                   # wild-server/
SCENES_DIR = _SERVER_ROOT / "storage" / "scenes"  # 后端自己的存储目录

# 将 wild-core 暂不支持的模型常见叫法收敛到可渲染的 furniture subtype。
_FURNITURE_SUBTYPE_ALIASES = {
    "sofa": "chair",
    "counter": "table",
}


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
    # 非贪婪匹配保证回复中有多个代码块时只读取第一个 json 块。
    match = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
    if not match:
        return None
    try:
        # 这里只负责 JSON 语法解析，Blueprint 结构由后续校验函数检查。
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
    # ScenePatch 和 Blueprint 使用相同的代码块格式，因此复用底层 JSON 提取。
    data = extract_blueprint_from_text(text)
    if data is None:
        return None
    if "operations" not in data:
        return None
    ops = data["operations"]
    if not isinstance(ops, list) or len(ops) == 0:
        return None
    # summary 只用于向用户说明修改内容；缺失时补一个稳定默认值。
    if "summary" not in data:
        data["summary"] = "修改场景"
    return data


# ---------- 结构校验 ----------

def normalize_blueprint_input(blueprint: dict) -> dict:
    """将模型常见简写转换为标准 WILD 1.1 字段。

    函数先深拷贝，所以修改返回值不会反向污染 LLM 原始输出。这里只做能够
    确定意图的兼容转换；无法可靠推断的缺失字段留给后续校验器报告。
    """
    normalized = deepcopy(blueprint)

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
        elif element.get("type") == "column" and element.get("style") == "round":
            # round 描述截面形状，但不属于柱式枚举；modern 是最接近的兜底值。
            element["style"] = "modern"
        elif element.get("type") == "furniture":
            subtype = element.get("subtype")
            if subtype in _FURNITURE_SUBTYPE_ALIASES:
                # 仅转换上面白名单中的已知别名，不猜测其他未知家具类型。
                element["subtype"] = _FURNITURE_SUBTYPE_ALIASES[subtype]

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
                issues.append("meta.version 缺失")
            if "type" not in meta:
                issues.append("meta.type 缺失")
            if "name" not in meta:
                issues.append("meta.name 缺失")

    # ---------- 几何容器与构件基本身份 ----------
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
                # 空字符串也参与重复检查，因此多个缺失 ID 会形成明确问题。
                ids = [el.get("id", "") for el in elements if isinstance(el, dict)]
                dupes = {eid for eid in ids if ids.count(eid) > 1}
                if dupes:
                    issues.append(f"重复的构件 ID: {dupes}")
                # 更细的逐类型必填字段由 spatial_tools 中的校验器负责。
                for el in elements:
                    if not isinstance(el, dict):
                        continue
                    element_id = el.get("id", "?")
                    if "type" not in el:
                        issues.append(f"元素缺少 'type' 字段: id={element_id}")
                    for coordinate_field in ("from", "to"):
                        if (
                            coordinate_field in el
                            and not _is_finite_vector3(el[coordinate_field])
                        ):
                            issues.append(
                                f"{element_id}.{coordinate_field} 必须是包含 3 个有限数字的数组"
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
    # 保存函数假定调用方已经完成结构与空间校验，不在这里重复校验。
    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now()
    # 秒级时间戳适合普通生成流程；同一秒重复保存时会覆盖同名文件。
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
    # filename 的合法性和路径边界由 API 调用层负责；本函数只执行序列化。
    file_path = directory / filename
    # write_text 默认覆盖同名文件，这正是同一会话持续保存场景所需的语义。
    file_path.write_text(
        json.dumps(blueprint, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return str(file_path.resolve())
