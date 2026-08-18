"""
Blueprint Normalizer - 确定性蓝图修复模块

**设计目标**：
以前端 wild_schema.json 为单一事实源，确保后端生成的蓝图在交付前端前完全合规。

**核心原则**：
1. 纯函数、无 LLM、幂等
2. 剥离未知字段
3. 修复已知漂移模式
4. 无法修复则丢弃单个构件
5. 返回详细修复报告

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

# ─────────────────────────────────────────────────────────────
# Schema 加载
# ─────────────────────────────────────────────────────────────

# Vendored 副本：从 wild-web/wild-lang/schema.json 复制
SCHEMA_PATH = Path(__file__).parent / "wild_schema.json"

def load_schema() -> Dict[str, Any]:
    """加载 vendored schema.json（懒加载）"""
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

# ─────────────────────────────────────────────────────────────
# 白名单派生
# ─────────────────────────────────────────────────────────────

def _extract_allowed_fields(schema_def: Dict[str, Any]) -> Tuple[Set[str], Set[str]]:
    """从 schema 定义提取允许字段 + 必填字段"""
    props = schema_def.get("properties", {})
    required = set(schema_def.get("required", []))
    allowed = set(props.keys())
    return allowed, required

_COMPONENT_FIELDS_CACHE: Dict[str, Tuple[Set[str], Set[str]]] = {}

def get_component_allowed_fields(comp_type: str) -> Tuple[Set[str], Set[str]]:
    """获取组件类型的 (允许字段, 必填字段)"""
    if comp_type in _COMPONENT_FIELDS_CACHE:
        return _COMPONENT_FIELDS_CACHE[comp_type]
    
    schema = get_schema()
    component_schema_key = f"{comp_type}Component"
    
    # 查找 $defs 中的定义
    defs = schema.get("$defs", {})
    comp_def = defs.get(component_schema_key, {})
    
    if not comp_def:
        logger.warning(f"未找到组件 schema: {component_schema_key}")
        return set(), set()
    
    allowed, required = _extract_allowed_fields(comp_def)
    _COMPONENT_FIELDS_CACHE[comp_type] = (allowed, required)
    return allowed, required

# ─────────────────────────────────────────────────────────────
# 修复报告
# ─────────────────────────────────────────────────────────────

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

# ─────────────────────────────────────────────────────────────
# 组件修复
# ─────────────────────────────────────────────────────────────

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

# ─────────────────────────────────────────────────────────────
# 元素修复
# ─────────────────────────────────────────────────────────────

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

def _repair_elements(elements: List[Dict[str, Any]], report: NormalizeReport) -> List[Dict[str, Any]]:
    """修复元素列表"""
    repaired = []
    
    for elem in elements:
        elem_type = elem.get("type")
        
        # 丢弃旧版 body（非建筑元素）
        if elem_type == "body":
            report.dropped_elements.append(f"{elem.get('id', 'unknown')} (body 不是建筑元素)")
            continue
        
        # 修复 column
        if elem_type == "column":
            elem = _repair_column_style(elem, report)
            elem = _convert_old_column(elem, report)
        
        repaired.append(elem)
    
    return repaired

# ─────────────────────────────────────────────────────────────
# 几何修复
# ─────────────────────────────────────────────────────────────

def _deduplicate_walls(elements: List[Dict[str, Any]], report: NormalizeReport) -> List[Dict[str, Any]]:
    """双墙去重"""
    walls = [e for e in elements if e.get("type") == "wall"]
    non_walls = [e for e in elements if e.get("type") != "wall"]
    
    # 简单去重：相同 from/to 的墙只保留一个
    seen = set()
    deduped = []
    
    for wall in walls:
        key = (tuple(wall.get("from", [])), tuple(wall.get("to", [])))
        if key not in seen:
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
    根据材质 ID 创建合理的默认材质定义
    
    Args:
        material_id: 材质 ID（如 "tile", "door_wood", "glass"）
        
    Returns:
        材质定义字典
    """
    mat_lower = material_id.lower()
    
    # 根据常见材质名称模式推断类型和颜色
    if "wood" in mat_lower or "timber" in mat_lower:
        return {
            "type": "standard",
            "baseColor": [0.6, 0.4, 0.2]  # 木色
        }
    elif "glass" in mat_lower:
        return {
            "type": "standard",
            "baseColor": [0.8, 0.9, 1.0],
            "opacity": 0.3
        }
    elif "tile" in mat_lower or "roof" in mat_lower:
        return {
            "type": "standard",
            "baseColor": [0.5, 0.3, 0.2]  # 瓦片色
        }
    elif "concrete" in mat_lower or "cement" in mat_lower:
        return {
            "type": "standard",
            "baseColor": [0.7, 0.7, 0.7]  # 混凝土灰
        }
    elif "brick" in mat_lower:
        return {
            "type": "standard",
            "baseColor": [0.7, 0.3, 0.2]  # 砖红色
        }
    elif "metal" in mat_lower or "steel" in mat_lower:
        return {
            "type": "standard",
            "baseColor": [0.8, 0.8, 0.8],
            "metallic": 0.8
        }
    elif "white" in mat_lower:
        return {
            "type": "standard",
            "baseColor": [0.95, 0.95, 0.95]
        }
    else:
        # 通用默认材质
        return {
            "type": "standard",
            "baseColor": [0.8, 0.8, 0.8]
        }


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

# ─────────────────────────────────────────────────────────────
# Schema 校验
# ─────────────────────────────────────────────────────────────

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

# ─────────────────────────────────────────────────────────────
# 主函数
# ─────────────────────────────────────────────────────────────

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
