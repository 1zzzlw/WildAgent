# Design Document: fix-element-elevation

## Overview

当前的 15 步校验流水线在 Step 9 (`validate_collision`) 中能正确检测到 column/stair/furniture 构件底部悬空或穿入楼板的问题，但流水线**没有对应的自动修正步骤**，导致问题被检测后未被修复，最终渲染出柱子悬空、透明穿插等视觉错误。

本设计新增：
- `fix_element_elevations`：`spatial_tools.py` 中的 `@tool` 纯函数，自动将竖向构件底部 Y 对齐到最近楼板顶面
- **Step 9b**：在 `run_validation_pipeline()` 中，当 Step 9 报告悬空/穿插问题时自动触发，并在修正后重检

## Architecture

修改范围限于两个文件，不影响任何其他模块：

```
wild-server/app/tools/spatial_tools.py    ← 新增 fix_element_elevations 工具
wild-server/app/services/agent_service.py ← 在流水线末尾新增 Step 9b 逻辑
```

流水线调用链不变：

```
ws_agent.py → agent_service.query_structured() → run_validation_pipeline()
                                                         ↓
                                               [Step 1~9 原样保留]
                                                         ↓
                                    Step 9 有悬空/穿插警告?
                                         Yes → Step 9b: fix_element_elevations
                                                        + validate_collision [recheck]
                                          No → skip Step 9b
```

## Components and Interfaces

### fix_element_elevations (spatial_tools.py)

```python
@tool
def fix_element_elevations(blueprint: dict) -> str:
    """
    自动修正竖向构件底部 Y 坐标，使其对齐到最近的楼板顶面（含地面 Y=0）。

    修正对象：
      - column：base[1]（柱子底面 Y）
      - stair：from[1]（楼梯起点 Y）
      - furniture：position[1]（家具底面 Y）

    修正阈值：
      - gap > 0.3m（悬空）→ 修正到最近楼板 Y
      - gap < -0.1m（穿入）→ 修正到最近楼板 Y

    参数 blueprint: 完整的 Blueprint dict（直接修改，原地更新）
    返回: 人类可读的修正结果字符串
    """
```

**修正逻辑**：
1. 收集所有 `floor` 构件的 `from[1]` 作为楼板参考高度，加上地面 `Y=0`，去重排序
2. 遍历 `column` / `stair` / `furniture`，获取底部 Y
3. 找最近楼板 Y（`min(ref_ys, key=lambda h: abs(h - bottom_y))`）
4. 计算 `gap = bottom_y - nearest_floor_y`
5. 若 `gap > 0.3` 或 `gap < -0.1`，则将底部 Y 设为 `nearest_floor_y`，记录修改

### agent_service.py — Step 9b

在 `run_validation_pipeline()` 函数末尾（Step 9 之后）新增：

```python
# ── Step 9b: 自动修正竖向构件高程 ──
if r9.has_warning or r9.has_error:
    fix_out = _run_tool(fix_element_elevations, blueprint)
    results.append(PipelineStepResult(...))
    recheck_out = _run_tool(validate_collision, blueprint)
    results.append(PipelineStepResult(..., name="validate_collision [recheck]"))
else:
    skip_step("9b", "fix_element_elevations", "Step 9 碰撞检测无问题")
```

## Data Models

无新数据模型。操作对象是现有 `blueprint: dict`，直接原地修改。

修改的字段路径：
- `geometry.elements[i].base[1]`（type=column）
- `geometry.elements[i].from[1]`（type=stair）
- `geometry.elements[i].position[1]`（type=furniture）

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do.*

### Property 1: 竖向构件高程对齐

*For any* Blueprint 包含若干 floor 构件和若干 column/stair/furniture 构件，其中某些构件底部 Y 与最近楼板的差值超过阈值（gap > 0.3m 或 gap < -0.1m），在调用 `fix_element_elevations` 之后，所有底部 Y 与最近楼板的差值应满足 `-0.1m <= gap <= 0.3m`（即不再悬空也不再穿入）。

**Validates: Requirements 1.2, 1.3, 1.4, 1.5**

### Property 2: 修正输出包含元素信息

*For any* Blueprint 中有被修正的构件，`fix_element_elevations` 的返回字符串应包含每个被修正构件的 ID。

**Validates: Requirements 1.7**

### Property 3: 字段修改隔离性

*For any* Blueprint，调用 `fix_element_elevations` 后，除了 `column.base[1]`、`stair.from[1]`、`furniture.position[1]` 之外，Blueprint 中所有其他字段的值应保持不变。

**Validates: Requirements 3.2**

## Error Handling

- Blueprint 中没有 floor 构件时，参考高度列表默认包含 `Y=0`（地面），修正仍然有效
- 构件缺少坐标字段（base/from/position 为空列表）时，跳过该构件，不修正也不报错
- 非 column/stair/furniture 类型的构件一律跳过

## Testing Strategy

### Unit Tests

- 测试 column 悬空修正：给定 floor Y=0.9，column base Y=1.5，修正后应为 0.9
- 测试 column 穿入修正：给定 floor Y=0.9，column base Y=0.7，修正后应为 0.9
- 测试无楼板时使用 Y=0 作为参考
- 测试无需修正时返回通过消息
- 测试 Step 9b 在 Step 9 有警告时被触发，无警告时被跳过

### Property Tests

使用 `hypothesis` 库（已是项目 Python 测试的标准选择）。

**Property 1 测试**：
```python
# Feature: fix-element-elevation, Property 1: 竖向构件高程对齐
@given(blueprint_with_floating_elements())
def test_elevation_snap_property(blueprint):
    fix_element_elevations.func(blueprint)
    for el in get_elements(blueprint):
        bottom_y = get_bottom_y(el)
        floor_ys = [0.0] + get_floor_ys(blueprint)
        nearest = min(floor_ys, key=lambda h: abs(h - bottom_y))
        gap = bottom_y - nearest
        assert -0.1 <= gap <= 0.3
```

**Property 3 测试**：
```python
# Feature: fix-element-elevation, Property 3: 字段修改隔离性
@given(st.from_type(dict))  # 使用 arbitrary blueprint
def test_field_mutation_isolation(blueprint):
    original = deepcopy(blueprint)
    fix_element_elevations.func(blueprint)
    # 除了允许的字段外，其他所有字段应不变
    for el_before, el_after in zip(original_elements, new_elements):
        for key in el_before:
            if key not in ('base', 'from', 'position'):
                assert el_before[key] == el_after[key]
```

每个属性测试配置最少 100 次迭代。
