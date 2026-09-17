# 修复entrance_bay契约验证错误

**日期**: 2026-09-16  
**问题**: 所有立面都被分配了entrance_bay字段，导致非前立面违反设计契约  
**状态**: ✅ 已完成

## 问题描述

前端生成失败，错误信息：
```
错误: 总体方案不满足设计契约：entrance_bay 不能超出 bays
```

### 根本原因

在 `normalize_architecture_plan()` 函数中，第591行使用了：
```python
entrance_bay = base.get("entrance_bay", 1)
```

这导致所有立面（front/back/left/right）都被赋予了 `entrance_bay` 字段的默认值1，但根据设计契约，只有 **front 立面** 应该有 `entrance_bay` 字段。

## 修复方案

修改 `wild-server/app/agent/generation/architecture/planning.py` 第582-608行：

```python
# 修复前（会给所有立面添加entrance_bay）
entrance_bay = base.get("entrance_bay", 1)

# 修复后（只有front立面且明确存在entrance_bay时才添加）
entrance_bay = base.get("entrance_bay")  # 不提供默认值
if entrance_bay is not None:
    facade_data["entrance_bay"] = entrance_bay
    # ...自动计算中间位置
```

### 核心改动

1. **检查字段是否存在**：使用 `base.get("entrance_bay")` 而不是提供默认值
2. **条件性添加**：只有当 `entrance_bay` 不为 `None` 时，才将其添加到 `facade_data`
3. **保留原有逻辑**：自动计算中间位置的逻辑保持不变

## 测试验证

创建了 `wild-server/verify_entrance_bay_fix.py`：

```python
# 测试场景：
# - front 立面有 entrance_bay：应保留
# - 其他立面无 entrance_bay：不应添加
# - entrance_bay 为0时：应处理为中间位置
```

测试结果：
```
✓ Front facade correctly has entrance_bay
✓ Back facade correctly has NO entrance_bay
✓ Left facade correctly has NO entrance_bay  
✓ Right facade correctly has NO entrance_bay
```

## 影响范围

- **文件**: `wild-server/app/agent/generation/architecture/planning.py`
- **行数**: 582-608
- **影响**: 所有立面归一化逻辑
- **风险**: 低 - 修复明确违反契约的行为

## 后续工作

无需额外工作，修复完成且通过验证。
