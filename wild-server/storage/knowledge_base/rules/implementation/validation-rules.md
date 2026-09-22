---
doc_type: recipe
knowledge_role: relation
doc_scope: generation
knowledge_layer: constraint
entity_type: validator
entity_name: runtime_validation_rules
topic: validation
wild_version: "1.1"
status: supported
authority: engine
primary_terms:
  - 运行时校验
  - validation rule
  - 必填字段
  - ID 唯一性
  - 引用完整性
  - 数值边界
  - 几何约束
  - 坐标系统
synonyms: []
---

# WILD 运行时校验规则

> 定义生成 WILD JSON 后必须通过的校验检查  
> 来源：代码中的 validator、compiler、resolver

本文档列出生成 Blueprint 后**必须通过**的所有校验规则。违反任何规则会导致编译失败或渲染错误。

---

## 1. 基础完整性检查

### 1.1 必填字段

#### 所有构件通用

- ✅ `type` - 必须是有效的构件类型
- ✅ `id` - 必须存在且唯一

#### 按构件类型

按构件类型的必填字段，以各构件参数表中标记为「必需」的为准。

**示例**：

```python
# wall 必填字段
required_fields = ["id", "from", "to", "thickness"]

def validate_wall(wall):
    for field in required_fields:
        if field not in wall:
            raise ValidationError(f"Missing required field: {field}")
```

### 1.2 ID 唯一性

```python
def validate_unique_ids(blueprint):
    all_ids = []
    
    # 收集所有 id
    for element in blueprint["geometry"]["elements"]:
        all_ids.append(element["id"])
    
    for component in blueprint["geometry"].get("components", []):
        all_ids.append(component["id"])
    
    # 检查重复
    duplicates = [id for id in all_ids if all_ids.count(id) > 1]
    if duplicates:
        raise ValidationError(f"Duplicate IDs: {duplicates}")
```

### 1.3 类型有效性

```python
VALID_ELEMENT_TYPES = {
    "wall", "floor", "column", "beam", "roof", 
    "opening", "stair", "furniture", "dense_brick", 
    "body", "primitive"
}

VALID_COMPONENT_TYPES = {
    "door", "window", "railing", "canopy", "balcony",
    "ramp", "bay_window", "cornice", "chimney", "light"
}

def validate_types(blueprint):
    for element in blueprint["geometry"]["elements"]:
        if element["type"] not in VALID_ELEMENT_TYPES:
            raise ValidationError(f"Invalid element type: {element['type']}")
    
    for component in blueprint["geometry"].get("components", []):
        if component["type"] not in VALID_COMPONENT_TYPES:
            raise ValidationError(f"Invalid component type: {component['type']}")
```

---

## 2. 引用完整性检查

### 2.1 parentWall 引用

```python
def validate_parent_wall_references(blueprint):
    elements = blueprint["geometry"]["elements"]
    components = blueprint["geometry"].get("components", [])
    
    # 收集所有 wall id
    wall_ids = {e["id"] for e in elements if e["type"] == "wall"}
    
    # 检查所有需要 parentWall 的组件
    for component in components:
        if "parentWall" in component:
            parent_id = component["parentWall"]
            if parent_id not in wall_ids:
                raise ReferenceError(
                    f"Component '{component['id']}' references non-existent wall '{parent_id}'"
                )
```

### 2.2 其他引用

类似检查：

- `parentFloor` → floor id
- `parentRoof` → roof id
- `material` → 材质库中的键

```python
def validate_material_references(blueprint):
    materials = blueprint.get("materials", {})
    
    # 检查所有构件的材质引用
    for element in blueprint["geometry"]["elements"]:
        if "material" in element:
            mat_name = element["material"]
            if mat_name not in materials:
                raise ReferenceError(
                    f"Element '{element['id']}' references undefined material '{mat_name}'"
                )
```

---

## 3. 数值边界检查

### 3.1 正数约束

```python
def validate_positive_values(blueprint):
    for element in blueprint["geometry"]["elements"]:
        # 厚度必须 > 0
        if "thickness" in element and element["thickness"] <= 0:
            raise ValueError(f"thickness must be > 0 for {element['id']}")
        
        # 宽度、高度必须 > 0
        if "width" in element and element["width"] <= 0:
            raise ValueError(f"width must be > 0 for {element['id']}")
        
        if "height" in element and element["height"] <= 0:
            raise ValueError(f"height must be > 0 for {element['id']}")
        
        # 半径必须 > 0
        if "radius" in element and element["radius"] <= 0:
            raise ValueError(f"radius must be > 0 for {element['id']}")
        
        if "bottomRadius" in element and element["bottomRadius"] <= 0:
            raise ValueError(f"bottomRadius must be > 0 for {element['id']}")
        
        if "topRadius" in element and element["topRadius"] <= 0:
            raise ValueError(f"topRadius must be > 0 for {element['id']}")
```

### 3.2 范围约束

```python
def validate_ranges(blueprint):
    materials = blueprint.get("materials", {})
    
    for name, material in materials.items():
        # 颜色范围 0-1
        if "baseColor" in material:
            for i, v in enumerate(material["baseColor"]):
                if not (0 <= v <= 1):
                    raise ValueError(
                        f"Material '{name}' baseColor[{i}] = {v}, must be in [0, 1]"
                    )
        
        # 粗糙度、金属度、反照率 0-1
        if "roughness" in material and not (0 <= material["roughness"] <= 1):
            raise ValueError(f"Material '{name}' roughness must be in [0, 1]")
        
        if "metallic" in material and not (0 <= material["metallic"] <= 1):
            raise ValueError(f"Material '{name}' metallic must be in [0, 1]")
        
        if "albedo" in material and not (0 <= material["albedo"] <= 1):
            raise ValueError(f"Material '{name}' albedo must be in [0, 1]")
```

---

## 4. 几何约束检查

### 4.1 墙体长度

```python
def validate_wall_length(wall):
    from_pos = wall["from"]
    to_pos = wall["to"]
    
    # 计算长度
    dx = to_pos[0] - from_pos[0]
    dz = to_pos[2] - from_pos[2]
    length = math.sqrt(dx**2 + dz**2)
    
    # 长度不能为 0 或负
    if length < 0.01:  # 最小 1cm
        raise ValueError(
            f"Wall '{wall['id']}' length = {length:.3f}m, must be >= 0.01m"
        )
    
    # 墙高
    height = to_pos[1] - from_pos[1]
    if height <= 0:
        raise ValueError(
            f"Wall '{wall['id']}' height = {height}m, must be > 0"
        )
```

### 4.2 门窗范围

```python
def validate_door_window_range(component, parent_wall):
    # 计算父墙长度
    wall_length = calculate_wall_length(parent_wall)
    wall_height = parent_wall["to"][1] - parent_wall["from"][1]
    
    # 检查水平范围
    along_wall = component["from"][0]
    width = component["width"]
    
    if along_wall < 0:
        raise ValueError(
            f"Component '{component['id']}' from[0] = {along_wall}, must be >= 0"
        )
    
    if along_wall + width > wall_length:
        raise ValueError(
            f"Component '{component['id']}' exceeds wall horizontal range: "
            f"{along_wall + width} > {wall_length}"
        )
    
    # 检查垂直范围（如果有高度）
    if "height" in component:
        bottom_y = component["from"][1]
        height = component["height"]
        wall_bottom = parent_wall["from"][1]
        wall_top = parent_wall["to"][1]
        
        if bottom_y < wall_bottom:
            raise ValueError(
                f"Component '{component['id']}' bottom {bottom_y} < wall bottom {wall_bottom}"
            )
        
        if bottom_y + height > wall_top:
            raise ValueError(
                f"Component '{component['id']}' top {bottom_y + height} > wall top {wall_top}"
            )
```

### 4.3 深度约束

```python
def validate_frame_depth(component, parent_wall):
    wall_thickness = parent_wall["thickness"]
    
    # 门框深度
    if component["type"] == "door":
        frame_depth = component.get("frameDepth", wall_thickness)
        if frame_depth > wall_thickness:
            raise ValueError(
                f"Door '{component['id']}' frameDepth {frame_depth} > "
                f"wall thickness {wall_thickness}"
            )
        
        leaf_depth = component.get("leafDepth", min(0.04, frame_depth))
        if leaf_depth > frame_depth:
            raise ValueError(
                f"Door '{component['id']}' leafDepth {leaf_depth} > "
                f"frameDepth {frame_depth}"
            )
    
    # 窗框深度
    if component["type"] == "window":
        frame_depth = component.get("frameDepth", wall_thickness)
        if frame_depth > wall_thickness:
            raise ValueError(
                f"Window '{component['id']}' frameDepth {frame_depth} > "
                f"wall thickness {wall_thickness}"
            )
        
        glass_depth = component.get("glassDepth", min(0.012, frame_depth))
        if glass_depth > frame_depth:
            raise ValueError(
                f"Window '{component['id']}' glassDepth {glass_depth} > "
                f"frameDepth {frame_depth}"
            )
```

---

## 5. 坐标系统检查

### 5.1 数组长度

```python
def validate_coordinate_arrays(blueprint):
    for element in blueprint["geometry"]["elements"]:
        # from/to 必须是 [x, y, z]
        if "from" in element:
            if not isinstance(element["from"], list) or len(element["from"]) != 3:
                raise ValueError(
                    f"Element '{element['id']}' from must be [x, y, z] array"
                )
        
        if "to" in element:
            if not isinstance(element["to"], list) or len(element["to"]) != 3:
                raise ValueError(
                    f"Element '{element['id']}' to must be [x, y, z] array"
                )
        
        # position 必须是 [x, y, z]
        if "position" in element:
            if not isinstance(element["position"], list) or len(element["position"]) != 3:
                raise ValueError(
                    f"Element '{element['id']}' position must be [x, y, z] array"
                )
```

### 5.2 颜色数组

```python
def validate_color_arrays(blueprint):
    materials = blueprint.get("materials", {})
    
    for name, material in materials.items():
        # baseColor 必须是 [r, g, b]
        if "baseColor" in material:
            if not isinstance(material["baseColor"], list) or len(material["baseColor"]) != 3:
                raise ValueError(
                    f"Material '{name}' baseColor must be [r, g, b] array"
                )
        
        # emissive 必须是 [r, g, b]
        if "emissive" in material:
            if not isinstance(material["emissive"], list) or len(material["emissive"]) != 3:
                raise ValueError(
                    f"Material '{name}' emissive must be [r, g, b] array"
                )
```

---

## 6. 枚举值检查

```python
VALID_COLUMN_STYLES = {
    "doric", "ionic", "corinthian", "modern", "chinese_wooden"
}

VALID_ROOF_TYPES = {
    "gable", "hip", "dome", "flat", "chinese_curved", "chinese_pagoda"
}

VALID_BEAM_CROSS_SECTIONS = {
    "rect", "circular", "i-beam"
}

def validate_enums(blueprint):
    for element in blueprint["geometry"]["elements"]:
        # column.style
        if element["type"] == "column":
            style = element.get("style")
            if style and style not in VALID_COLUMN_STYLES:
                raise ValueError(
                    f"Column '{element['id']}' invalid style '{style}'. "
                    f"Valid: {VALID_COLUMN_STYLES}"
                )
        
        # roof.roofType
        if element["type"] == "roof":
            roof_type = element.get("roofType")
            if roof_type and roof_type not in VALID_ROOF_TYPES:
                raise ValueError(
                    f"Roof '{element['id']}' invalid roofType '{roof_type}'. "
                    f"Valid: {VALID_ROOF_TYPES}"
                )
        
        # beam.crossSection
        if element["type"] == "beam":
            cross_section = element.get("crossSection")
            if cross_section and cross_section not in VALID_BEAM_CROSS_SECTIONS:
                raise ValueError(
                    f"Beam '{element['id']}' invalid crossSection '{cross_section}'. "
                    f"Valid: {VALID_BEAM_CROSS_SECTIONS}"
                )
```

---

## 7. 版本兼容性检查

```python
def validate_version(blueprint):
    version = blueprint["meta"]["version"]
    
    # 当前支持 1.0 和 1.1
    if version not in ["1.0", "1.1"]:
        raise ValueError(
            f"Unsupported WILD version '{version}'. Supported: 1.0, 1.1"
        )
    
    # v1.0 不支持 primitive
    if version == "1.0":
        for element in blueprint["geometry"]["elements"]:
            if element["type"] == "primitive":
                raise ValueError(
                    "primitive type requires WILD v1.1. "
                    "Set meta.version to '1.1'"
                )
```

---

## 8. Schema 校验

### 8.1 使用 schema.json

```python
import json
import jsonschema

def validate_against_schema(blueprint):
    with open("schema.json") as f:
        schema = json.load(f)
    
    try:
        jsonschema.validate(blueprint, schema)
    except jsonschema.ValidationError as e:
        raise ValidationError(f"Schema validation failed: {e.message}")
```

### 8.2 自定义校验

Schema 无法表达的约束（如引用完整性、几何约束）需要自定义校验器。

---

## 9. 校验清单

生成 WILD 后，按顺序执行：

1. **基础完整性**
   - [ ] 所有必填字段都存在？
   - [ ] 所有 id 唯一？
   - [ ] 所有 type 有效？

2. **引用完整性**
   - [ ] 所有 parentWall 引用存在？
   - [ ] 所有 parentFloor 引用存在？
   - [ ] 所有 material 引用存在？

3. **数值边界**
   - [ ] 所有长度/厚度/半径 > 0？
   - [ ] 所有颜色值在 [0, 1]？
   - [ ] 所有材质参数在有效范围？

4. **几何约束**
   - [ ] 墙体长度和高度有效？
   - [ ] 门窗不超出父墙范围？
   - [ ] 深度不超过墙体厚度？

5. **坐标系统**
   - [ ] 所有坐标数组长度正确？
   - [ ] 颜色数组长度正确？

6. **枚举值**
   - [ ] 所有 style/roofType/crossSection 等有效？

7. **版本兼容**
   - [ ] meta.version 正确设置？
   - [ ] 使用的特性与版本匹配？

8. **Schema**
   - [ ] 通过 schema.json 校验？

---

## 10. 错误处理

### 10.1 明确的错误消息

```python
# ❌ 模糊错误
raise ValueError("Invalid value")

# ✅ 明确错误
raise ValueError(
    f"Window '{component['id']}' frameDepth {frame_depth}m exceeds "
    f"parent wall thickness {wall_thickness}m. "
    f"frameDepth must be <= {wall_thickness}m"
)
```

### 10.2 收集所有错误

```python
def validate_blueprint(blueprint):
    errors = []
    
    try:
        validate_unique_ids(blueprint)
    except ValidationError as e:
        errors.append(str(e))
    
    try:
        validate_parent_wall_references(blueprint)
    except ReferenceError as e:
        errors.append(str(e))
    
    # ... 更多检查
    
    if errors:
        raise ValidationError(f"Validation failed with {len(errors)} errors:\n" + "\n".join(errors))
```

---

## 实现来源

- `wild-core/src/primitive/validator.ts`
- `wild-core/wild-core/src/compiler/index.ts`
- `wild-server/app/services/blueprint_service.py`

校验规则与引擎实现保持同步。
