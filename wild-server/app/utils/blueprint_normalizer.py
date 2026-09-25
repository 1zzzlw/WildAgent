"""
Blueprint Normalizer - 确定性蓝图修复模块

**设计目标**：
以知识库目录下的 `schema.json` 为后端的单一事实源，确保后端生成的蓝图在交付前端前完全合规。

**核心原则**：
1. 纯函数、无 LLM、幂等
2. 剥离未知字段
3. 修复已知漂移模式
4. 无法修复则丢弃单个构件
5. 返回详细修复报告

🔴 **元素（`geometry.elements`）只迁移不丢弃**：元素是用户点名要交付的几何本体，
静默丢掉一个就等于"生成的物件凭空消失"（`body` 曾因此整类消失，见 `_repair_body`）。
未知类型的元素保留原样，交给 schema / 结构校验去报错——归一化不是类型过滤器。

**主函数**：
- normalize_blueprint_for_delivery(bp) -> (bp, report)
"""

import json
import copy
from pathlib import Path
from typing import Any, Dict, List, Tuple, Set
from loguru import logger

try:
    import jsonschema
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False
    logger.warning("jsonschema 未安装，将跳过最终 schema 校验")

# Schema 加载

# 后端的单一事实源：知识库目录下的 schema.json。
# 它随镜像内置的 storage/knowledge_base 一起分发，后端不依赖任何前端路径
# （前后端分部署）。前端那份在独立 npm 包 wild-core/schema.json（原
# wild-web/wild-lang/ 目录已删除），供其构建期 import；
# 两份内容应保持一致，但不共享路径。
_SERVER_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = _SERVER_ROOT / "storage" / "knowledge_base" / "schema.json"

def load_schema() -> Dict[str, Any]:
    """加载知识库 schema.json（懒加载）"""
    if not SCHEMA_PATH.exists():
        logger.error(f"Schema 文件不存在: {SCHEMA_PATH}")
        return {}
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

_SCHEMA_CACHE: Dict[str, Any] | None = None

def get_schema() -> Dict[str, Any]:
    """获取缓存的 schema"""
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        _SCHEMA_CACHE = load_schema()
    return _SCHEMA_CACHE

# 白名单派生

def _extract_allowed_fields(schema_def: Dict[str, Any]) -> Tuple[Set[str], Set[str]]:
    """从 schema 定义提取允许字段 + 必填字段"""
    props = schema_def.get("properties", {})
    required = set(schema_def.get("required", []))
    allowed = set(props.keys())
    return allowed, required

_COMPONENT_FIELDS_CACHE: Dict[str, Tuple[Set[str], Set[str]]] = {}

#: 构件 ``type`` 值（snake_case）→ schema ``$defs`` 键（camelCase）的映射。
#: 绝大多数是 ``type + "Component"``，只有带下划线的 kind 例外（如
#: ``bay_window`` → ``bayWindowComponent``）。schema 键是 camelCase，而
#: ``type`` 的 ``const`` 值是 snake_case，两者不能直接拼。
_COMPONENT_SCHEMA_KEY_OVERRIDES: Dict[str, str] = {
    "bay_window": "bayWindowComponent",
}


def _component_schema_key(comp_type: str) -> str:
    """构件 type 值 → schema ``$defs`` 键。"""
    return _COMPONENT_SCHEMA_KEY_OVERRIDES.get(comp_type, f"{comp_type}Component")


def get_component_allowed_fields(comp_type: str) -> Tuple[Set[str], Set[str]]:
    """获取组件类型的 (允许字段, 必填字段)"""
    if comp_type in _COMPONENT_FIELDS_CACHE:
        return _COMPONENT_FIELDS_CACHE[comp_type]
    
    schema = get_schema()
    component_schema_key = _component_schema_key(comp_type)
    
    # 查找 $defs 中的定义
    defs = schema.get("$defs", {})
    comp_def = defs.get(component_schema_key, {})
    
    if not comp_def:
        logger.warning(f"未找到组件 schema: {component_schema_key}")
        return set(), set()
    
    allowed, required = _extract_allowed_fields(comp_def)
    _COMPONENT_FIELDS_CACHE[comp_type] = (allowed, required)
    return allowed, required

# 修复报告

class NormalizeReport:
    """修复报告"""
    def __init__(self):
        self.stripped_fields: List[str] = []  # 剥离的未知字段
        self.repaired_fields: List[str] = []  # 修复的字段
        self.dropped_components: List[str] = []  # 丢弃的组件
        self.dropped_elements: List[str] = []  # 丢弃的元素
        self.added_materials: List[str] = []  # 自动添加的材质
        self.fixes_applied: List[str] = []  # 应用的修复工具
        self.schema_errors: List[str] = []  # 最终 schema 校验错误
    
    def summary(self) -> str:
        """生成摘要"""
        parts = []
        if self.stripped_fields:
            parts.append(f"剥离字段: {len(self.stripped_fields)}")
        if self.repaired_fields:
            parts.append(f"修复字段: {len(self.repaired_fields)}")
        if self.dropped_components:
            parts.append(f"丢弃组件: {len(self.dropped_components)}")
        if self.dropped_elements:
            parts.append(f"丢弃元素: {len(self.dropped_elements)}")
        if self.added_materials:
            parts.append(f"添加材质: {len(self.added_materials)}")
        if self.schema_errors:
            parts.append(f"剩余错误: {len(self.schema_errors)}")
        return "; ".join(parts) if parts else "无修复"

# 组件修复

def _strip_unknown_fields(comp: Dict[str, Any], report: NormalizeReport) -> Dict[str, Any]:
    """剥离组件的未知字段"""
    comp_type = comp.get("type")
    if not comp_type:
        return comp
    
    allowed, _required = get_component_allowed_fields(comp_type)
    if not allowed:
        return comp
    
    # 剥离未知字段
    cleaned = {}
    for key, value in comp.items():
        if key in allowed:
            cleaned[key] = value
        else:
            report.stripped_fields.append(f"{comp.get('id', 'unknown')}.{key}")
    
    return cleaned

def _repair_interaction(comp: Dict[str, Any], report: NormalizeReport) -> Dict[str, Any]:
    """修复 interaction 字段"""
    if "interaction" not in comp:
        return comp
    
    interaction = comp["interaction"]
    if not isinstance(interaction, dict):
        return comp
    
    # 修复 openAngle（必须 > 0）
    if "openAngle" in interaction:
        if interaction["openAngle"] <= 0:
            report.repaired_fields.append(f"{comp.get('id')}.interaction.openAngle -> 90")
            interaction["openAngle"] = 90.0
    
    # 修复 hingeSide（只能是 left/right）
    if "hingeSide" in interaction:
        if interaction["hingeSide"] not in ["left", "right"]:
            report.repaired_fields.append(f"{comp.get('id')}.interaction.hingeSide -> left")
            interaction["hingeSide"] = "left"
    
    return comp

def _repair_rail_levels(comp: Dict[str, Any], report: NormalizeReport) -> Dict[str, Any]:
    """修复 railLevels 钳位到 (0, 1]"""
    if comp.get("type") != "railing":
        return comp
    
    if "railLevels" not in comp:
        return comp
    
    levels = comp["railLevels"]
    if not isinstance(levels, list):
        return comp
    
    # 钳位每个值到 (0, 1]
    clamped = []
    for i, level in enumerate(levels):
        if not isinstance(level, (int, float)):
            continue
        if level <= 0:
            clamped.append(0.01)
            report.repaired_fields.append(f"{comp.get('id')}.railLevels[{i}] -> 0.01")
        elif level > 1:
            clamped.append(1.0)
            report.repaired_fields.append(f"{comp.get('id')}.railLevels[{i}] -> 1.0")
        else:
            clamped.append(level)
    
    comp["railLevels"] = clamped
    return comp

def _repair_from_z(comp: Dict[str, Any], report: NormalizeReport) -> Dict[str, Any]:
    """确保 from[2] ≈ 0（贴墙）"""
    if "from" not in comp:
        return comp
    
    from_vec = comp["from"]
    if not isinstance(from_vec, list) or len(from_vec) < 3:
        return comp
    
    if abs(from_vec[2]) > 0.01:
        report.repaired_fields.append(f"{comp.get('id')}.from[2] -> 0")
        from_vec[2] = 0.0
    
    return comp

def _fill_safe_defaults(comp: Dict[str, Any], report: NormalizeReport) -> Dict[str, Any]:
    """为 balcony/canopy/bay_window 填充安全默认值"""
    comp_type = comp.get("type")
    
    if comp_type == "balcony":
        if "slabThickness" not in comp:
            comp["slabThickness"] = 0.15
            report.repaired_fields.append(f"{comp.get('id')}.slabThickness -> 0.15")
    
    elif comp_type == "canopy":
        if "thickness" not in comp:
            comp["thickness"] = 0.05
            report.repaired_fields.append(f"{comp.get('id')}.thickness -> 0.05")
    
    elif comp_type == "bay_window":
        if "projectionDepth" not in comp:
            comp["projectionDepth"] = 0.5
            report.repaired_fields.append(f"{comp.get('id')}.projectionDepth -> 0.5")
    
    return comp

def _validate_required_fields(comp: Dict[str, Any], report: NormalizeReport) -> bool:
    """检查必填字段是否存在"""
    comp_type = comp.get("type")
    if not comp_type:
        return False
    
    _allowed, required = get_component_allowed_fields(comp_type)
    missing = required - set(comp.keys())
    
    if missing:
        comp_id = comp.get("id", "unknown")
        report.dropped_components.append(f"{comp_id} (缺失: {', '.join(missing)})")
        return False
    
    return True

def _repair_components(components: List[Dict[str, Any]], report: NormalizeReport) -> List[Dict[str, Any]]:
    """修复组件列表"""
    repaired = []
    
    for comp in components:
        # 1. 剥离未知字段
        comp = _strip_unknown_fields(comp, report)
        
        # 2. 修复 interaction
        comp = _repair_interaction(comp, report)
        
        # 3. 修复 railLevels
        comp = _repair_rail_levels(comp, report)
        
        # 4. 修复 from[2]
        comp = _repair_from_z(comp, report)
        
        # 5. 填充安全默认值
        comp = _fill_safe_defaults(comp, report)
        
        # 6. 检查必填字段
        if not _validate_required_fields(comp, report):
            continue
        
        repaired.append(comp)
    
    return repaired

# 元素修复

def _repair_column_style(elem: Dict[str, Any], report: NormalizeReport) -> Dict[str, Any]:
    """修复旧版 column style 枚举"""
    if elem.get("type") != "column":
        return elem
    
    if "style" not in elem:
        return elem
    
    style = elem["style"]
    # 旧枚举映射
    style_map = {
        "classical": "corinthian",
        "greek": "doric",
        "roman": "ionic",
    }
    
    if style in style_map:
        new_style = style_map[style]
        elem["style"] = new_style
        report.repaired_fields.append(f"{elem.get('id')}.style: {style} -> {new_style}")
    
    return elem

def _convert_old_column(elem: Dict[str, Any], report: NormalizeReport) -> Dict[str, Any]:
    """转换旧版 column 结构"""
    if elem.get("type") != "column":
        return elem
    
    # 旧版字段: dimensions, radius
    # 新版字段: base, height, bottomRadius, topRadius
    
    if "dimensions" in elem or "radius" in elem:
        # 提取旧字段
        dims = elem.get("dimensions", [0, 0, 0])
        radius = elem.get("radius", 0.3)
        
        # 转换为新字段
        if "base" not in elem:
            elem["base"] = [dims[0], dims[1], dims[2]]
        if "height" not in elem:
            elem["height"] = 3.0
        if "bottomRadius" not in elem:
            elem["bottomRadius"] = radius
        if "topRadius" not in elem:
            elem["topRadius"] = radius
        
        # 移除旧字段
        elem.pop("dimensions", None)
        elem.pop("radius", None)
        
        report.repaired_fields.append(f"{elem.get('id')}: 旧版 column -> 新版")
    
    return elem

#: `body` 的当前取值闭集，与 `wild-core/schema.json::$defs/body` 逐字对齐。
_BODY_BUILD_VALUES: Tuple[str, ...] = ("lean", "athletic", "stout")
_BODY_HEAD_SHAPES: Tuple[str, ...] = ("round", "oval", "angular")
#: `body.ts` 判据是 `if (cloakLength > 0.3)` → **0.3 就是"不披斗篷"**，
#: 也正好是 schema 的下限；旧场景里的 0 因此可以抬到 0.3 而不长出斗篷。
_BODY_CLOAK_MIN: float = 0.3
_BODY_DEFAULT_HEIGHT: float = 1.7


def _finite_number(value: Any, default: float) -> float:
    """把任意输入收敛成有限数字。

    `bool` 是 `int` 的子类，必须显式排除——否则 `hoodUp` 之类的布尔值会被当成
    `1.0` 塞进数值字段，正是"字段语义漂移"的开端。
    """

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return default
    return number


def _repair_body(elem: Dict[str, Any], report: NormalizeReport) -> Dict[str, Any]:
    """把旧版 `body` 元素**迁移**到当前 schema，而不是丢掉它。

    为什么不能丢：`body` 现在是 schema 的合法元素类型（`$defs/body`，已被
    `geometryElement` 的 oneOf 引用），引擎也有自己的 builder
    （`wild-core/src/primitive/registry.ts` 中 `type: 'body'`, status=partial）。
    这里曾经写的是"丢弃旧版 body（非建筑元素）"——那在"body 只是化身装饰"的旧语境下
    说得通，但物件链里 `body` 就是**用户点名要交付的物件本体**：无条件丢弃会让
    "生成一个小人"的产物在交付归一这一步静默消失（批次合并明明报"已并入 1 个元素"，
    收尾归一把它删掉），最终蓝图空掉、`validate_design_brief` 报
    "body 数量 0 少于设计下限 1"，条目被判 abandoned。

    **归一化不是类型过滤器**：真不合法的元素应该由 schema / 结构校验报错
    （《动态节点设计规划》§8.1"能力缺失只标记、不阻断"），而不是在这里悄悄删掉。

    旧值按**引擎自己的中性语义**迁移，所以既有场景的观感不变（`body.ts`：未知
    `build` → 缩放 1 = `athletic`；未知 `headShape` → `[1,1,1]` = `round`；
    `cloakLength <= 0.3` → 不生成斗篷）。
    """

    height = _finite_number(elem.get("height"), _BODY_DEFAULT_HEIGHT)
    if height <= 0:
        height = _BODY_DEFAULT_HEIGHT
    migrated = {
        "height": height,
        "build": (
            elem.get("build") if elem.get("build") in _BODY_BUILD_VALUES else "athletic"
        ),
        "headShape": (
            elem.get("headShape") if elem.get("headShape") in _BODY_HEAD_SHAPES else "round"
        ),
        "armLength": min(max(_finite_number(elem.get("armLength"), 1.0), 0.5), 1.5),
        "legLength": min(max(_finite_number(elem.get("legLength"), 1.0), 0.5), 1.5),
        "cloakLength": min(
            max(_finite_number(elem.get("cloakLength"), _BODY_CLOAK_MIN), _BODY_CLOAK_MIN),
            1.5,
        ),
        "hoodUp": bool(elem.get("hoodUp", False)),
    }
    changed = {key: value for key, value in migrated.items() if elem.get(key) != value}
    if changed:
        report.repaired_fields.append(f"{elem.get('id', 'unknown')}: body 旧值 -> {changed}")
    elem.update(migrated)
    return elem


def _repair_elements(elements: List[Dict[str, Any]], report: NormalizeReport) -> List[Dict[str, Any]]:
    """修复元素列表"""
    from app.utils.rotation import coerce_element_rotation

    repaired = []
    
    for elem in elements:
        elem_type = elem.get("type")
        
        # 修复 column
        if elem_type == "column":
            elem = _repair_column_style(elem, report)
            elem = _convert_old_column(elem, report)
        # 迁移旧版 body（保留几何，理由见 _repair_body）
        elif elem_type == "body":
            elem = _repair_body(elem, report)

        # rotation 单位迁移（所有元素共用）：模型写成度数标量/度数数组时收敛成弧度，
        # 而不是交给校验器把整批判死。与生成批次用的是同一个规则函数。
        if coerce_element_rotation(elem) is not None:
            report.repaired_fields.append(f"rotation 度数→弧度: {elem.get('id', '?')}")
        
        repaired.append(elem)
    
    return repaired

# 几何修复

def _deduplicate_walls(elements: List[Dict[str, Any]], report: NormalizeReport) -> List[Dict[str, Any]]:
    """按渲染使用的平面中心线与标高去除重复墙。"""
    from app.tools.spatial_tools import _wall_centerline_key

    walls = [e for e in elements if e.get("type") == "wall"]
    non_walls = [e for e in elements if e.get("type") != "wall"]

    seen = set()
    deduped = []

    for wall in walls:
        key = _wall_centerline_key(wall)
        if key is None:
            deduped.append(wall)
        elif key not in seen:
            seen.add(key)
            deduped.append(wall)
        else:
            report.repaired_fields.append(f"去重墙: {wall.get('id')}")
    
    return non_walls + deduped

def _normalize_materials(bp: Dict[str, Any], report: NormalizeReport) -> Dict[str, Any]:
    """
    规范化材质定义
    
    1. 收集所有被引用的材质
    2. 为缺失的材质创建默认定义
    """
    materials = bp.get("materials", {})
    if not isinstance(materials, dict):
        materials = {}
        bp["materials"] = materials
    
    # 收集所有材质引用
    referenced_materials = set()
    material_fields = ("material", "frameMaterial", "leafMaterial", "glassMaterial")
    
    geometry = bp.get("geometry", {})
    entities = [
        *(geometry.get("elements", []) or []),
        *(geometry.get("components", []) or []),
    ]
    
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        
        for field in material_fields:
            mat_ref = entity.get(field)
            if isinstance(mat_ref, str) and mat_ref:
                referenced_materials.add(mat_ref)
    
    # 为缺失的材质创建默认定义
    missing_materials = referenced_materials - set(materials.keys())
    
    if missing_materials:
        for mat_id in missing_materials:
            # 根据材质名称推断合理的默认值
            materials[mat_id] = _create_default_material(mat_id)
            report.added_materials.append(mat_id)
            logger.info(f"[归一化] 自动添加缺失材质: {mat_id}")
    
    bp["materials"] = materials
    return bp


def _create_default_material(material_id: str) -> Dict[str, Any]:
    """
    根据材质 ID 创建完整的默认材质定义

    对齐 schema 的 ``materialDef`` 必填字段：``baseColor / roughness / metallic /
    albedo / lightingCondition``，且不允许 ``type`` 字段。之前的实现只返回
    ``{type, baseColor}``，会产出 schema 非法的材质（缺 roughness 等必填项）。
    """
    mat_lower = material_id.lower()
    material: Dict[str, Any] = {
        "baseColor": [0.8, 0.8, 0.8],
        "roughness": 0.8,
        "metallic": 0.0,
        "albedo": 1.0,
        "lightingCondition": "D65_noon",
    }
    
    # 根据常见材质名称模式推断类型和颜色
    if "wood" in mat_lower or "timber" in mat_lower:
        material.update({"baseColor": [0.6, 0.4, 0.2], "roughness": 0.7})  # 木色
    elif "glass" in mat_lower:
        material.update({
            "baseColor": [0.8, 0.9, 1.0], "roughness": 0.1, "opacity": 0.3,
        })
    elif "tile" in mat_lower or "roof" in mat_lower:
        material.update({"baseColor": [0.5, 0.3, 0.2], "roughness": 0.85})  # 瓦片色
    elif "concrete" in mat_lower or "cement" in mat_lower:
        material.update({"baseColor": [0.7, 0.7, 0.7], "roughness": 0.9})  # 混凝土灰
    elif "brick" in mat_lower:
        material.update({"baseColor": [0.7, 0.3, 0.2], "roughness": 0.9})  # 砖红色
    elif "metal" in mat_lower or "steel" in mat_lower:
        material.update({
            "baseColor": [0.8, 0.8, 0.8], "roughness": 0.4, "metallic": 0.8,
        })
    elif "white" in mat_lower:
        material.update({"baseColor": [0.95, 0.95, 0.95]})
    return material


def _normalize_geometry(bp: Dict[str, Any], report: NormalizeReport) -> Dict[str, Any]:
    """几何归一化"""
    geom = bp.get("geometry", {})
    elements = geom.get("elements", [])
    
    # 双墙去重
    elements = _deduplicate_walls(elements, report)
    
    # 复用现有 spatial_tools 修复（如果可用）
    try:
        from app.tools.spatial_tools import fix_wall_junctions, fix_opening_fit
        
        # 如果是 StructuredTool（使用 @tool 装饰器），提取底层函数
        fix_wall_junctions_fn = getattr(fix_wall_junctions, 'func', fix_wall_junctions)
        fix_opening_fit_fn = getattr(fix_opening_fit, 'func', fix_opening_fit)
        
        # 这些工具期望完整 blueprint 并直接修改它
        temp_bp = {"geometry": {"elements": elements}, "materials": bp.get("materials", {})}
        
        # 调用修复函数
        try:
            result = fix_wall_junctions_fn(temp_bp)
            logger.debug(f"[归一化] fix_wall_junctions: {result}")
        except Exception as e:
            logger.warning(f"[归一化] fix_wall_junctions 失败: {e}")
        
        try:
            result = fix_opening_fit_fn(temp_bp)
            logger.debug(f"[归一化] fix_opening_fit: {result}")
        except Exception as e:
            logger.warning(f"[归一化] fix_opening_fit 失败: {e}")
        
        # 提取修复后的 elements
        elements = temp_bp["geometry"]["elements"]
        report.fixes_applied.append("spatial_tools_fixes")
        
    except ImportError:
        logger.debug("[归一化] spatial_tools 不可用，跳过墙体 junction 修复")
    except Exception as e:
        logger.warning(f"[归一化] spatial_tools 修复异常: {e}")
    
    geom["elements"] = elements
    return bp

# Schema 校验

def _validate_against_schema(bp: Dict[str, Any], report: NormalizeReport) -> bool:
    """用 jsonschema 严格校验"""
    if not JSONSCHEMA_AVAILABLE:
        return True
    
    schema = get_schema()
    if not schema:
        return True
    
    try:
        jsonschema.validate(bp, schema)
        return True
    except jsonschema.ValidationError as e:
        report.schema_errors.append(str(e.message))
        return False
    except Exception as e:
        logger.error(f"Schema 校验异常: {e}")
        return False

# 主函数

def normalize_blueprint_for_delivery(bp: Dict[str, Any]) -> Tuple[Dict[str, Any], NormalizeReport]:
    """
    归一化蓝图用于交付前端
    
    Args:
        bp: 原始蓝图
    
    Returns:
        (normalized_bp, report): 归一化后的蓝图 + 修复报告
    """
    report = NormalizeReport()
    bp = copy.deepcopy(bp)  # 不修改原对象
    
    # 1. 复用现有 normalize_blueprint_input（如果可用）
    try:
        from app.utils.blueprint_parser import normalize_blueprint_input
        bp = normalize_blueprint_input(bp)
    except ImportError:
        logger.warning("blueprint_parser 不可用，跳过基础归一化")
    
    # 2. 修复组件
    geom = bp.get("geometry", {})
    if "components" in geom:
        geom["components"] = _repair_components(geom["components"], report)
    
    # 3. 修复元素
    if "elements" in geom:
        geom["elements"] = _repair_elements(geom["elements"], report)
    
    # 4. 材质规范化（为缺失的材质创建默认定义）
    bp = _normalize_materials(bp, report)
    
    # 5. 几何修复
    bp = _normalize_geometry(bp, report)
    
    # 6. 二次收敛兜底（防止几何修复引入新非法值）
    if "components" in geom:
        geom["components"] = _repair_components(geom["components"], report)
    
    # 7. 最终 schema 校验
    _validate_against_schema(bp, report)
    
    logger.info(f"[Normalizer] {report.summary()}")
    
    return bp, report
