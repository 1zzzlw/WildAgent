# LangSmith Studio 层数约束错误修复

**日期**: 2026-09-16  
**问题**: LangSmith Studio调用失败，前端Web界面正常  
**状态**: ✅ 已修复

## 问题描述

用户在LangSmith Studio中测试"生成一个别墅"时，系统报错：

```
总体方案候选均违反已批准业务要求：req_task_1_2、req_task_3_2、req_task_4_3、req_task_6_3
```

错误显示 architecture 节点生成的所有候选方案都违反了4个业务要求，导致流程失败。

前端Web界面使用相同的输入却能正常生成，说明这不是偶发问题。

## 根因分析

### 问题根源

`app/agent/planning/requirements.py` 中的 `_compile_acceptance` 函数在编译结构化约束时，**将楼层属性描述错误识别为建筑总层数约束**。

### 错误的4个约束

这4个约束都被错误地编译为 `architecture_floor_count` (期望值=1):

1. **req_task_1_2**: "主体长宽尺寸确定，如长度12米，宽度8米，地下室层高不小于2.4米，**一层层高**不小于2.8米。"
   - 实际语义：描述**层高**（单个楼层的高度）
   - 错误识别为：建筑只能有1层

2. **req_task_3_2**: "**一层外墙**、内墙、楼板使用如'wood'、'plaster'等材质。"
   - 实际语义：描述**材质**（一层的材料）
   - 错误识别为：建筑只能有1层

3. **req_task_4_3**: "为**一层主要空间**（如客厅、卧室区域）的门窗预留开口位置。"
   - 实际语义：描述**门窗开口**（一层的开口）
   - 错误识别为：建筑只能有1层

4. **req_task_6_3**: "屋顶 position 的 Y 坐标与**一层墙顶**齐平。"
   - 实际语义：描述**屋顶位置**（相对一层的坐标）
   - 错误识别为：建筑只能有1层

### 冲突

执行计划task_1的描述明确说明：
> "建筑主体包含地下室、一层及半层阁楼（利用屋顶空间）**共三层几何结构**。"

但编译出的4个约束却要求 `floors == 1`，导致模型生成的所有多层方案都被拒绝。

### 为什么前端不出错？

- 前端Web和LangSmith Studio使用**完全相同的代码**和图结构
- 差异在于：
  - 前端用户可能使用的输入不同，导致LLM生成的执行计划不同
  - LangSmith Studio的测试输入恰好触发了这个边缘case
  - 前端用户即使遇到也可能没有开启plan_mode，或者执行计划没有生成这些具体的验收条件

## 修复方案

### 修改的文件

`wild-server/app/agent/planning/requirements.py`

### 修改内容

1. **调整检查顺序**：将层数检查移到组件检查之前
   - 原因：含"包含"关键词的描述会先被组件规则匹配

2. **加强层数识别条件**：
   ```python
   # 只有同时满足以下条件才识别为层数约束：
   is_total_floor_count = (
       # 明确的总数表达
       _contains_any(text, ("共", "总共", "分为"))
       # 或者是结构性描述（带"几何"、"结构"等）
       or _contains_any(text, ("层几何", "层结构", "层建筑"))
       # 或者是明确的层数特征
       or _contains_any(text, ("单层", "多层"))
   )
   ```

3. **排除楼层属性描述**：
   ```python
   # 排除对单个楼层的属性或位置描述
   is_single_floor_description = _contains_any(
       text,
       (
           # 属性描述
           "层高", "层地板", "层天花", "层外墙", "层内墙", "层空间", "层墙顶",
           "层主要空间", "层楼板", "层门窗", "层开口",
           # 材质/外观描述
           "层使用", "层材质", "层采用",
           # 位置描述
           "位于", "设在", "布置在", "放在",
       )
   )
   ```

### 修复效果

**修复前**：
- 5个约束被识别为 `architecture_floor_count`
  - req_task_1_1: "共三层几何结构" → floors=3 ✓ (正确)
  - req_task_1_2: "一层层高" → floors=1 ✗ (错误)
  - req_task_3_1: "一层外墙材质" → floors=1 ✗ (错误)
  - req_task_4_1: "一层门窗" → floors=1 ✗ (错误)
  - req_task_6_1: "一层墙顶" → floors=1 ✗ (错误)

**修复后**：
- 只有1个约束被识别为 `architecture_floor_count`
  - req_task_1_1: "共三层几何结构" → floors=3 ✓ (正确)
- 其他4个正确识别为 `phase_outcome`（阶段产物验收）

## 测试验证

### 新增测试

创建了 `wild-server/tests/test_requirements_floor_count_fix.py` 包含：

1. **test_floor_count_not_confused_with_floor_attributes**
   - 验证楼层属性描述不会被误判为层数约束

2. **test_bugfix_original_error_case**
   - 回归测试：验证原始错误场景已修复

### 验证脚本

`wild-server/verify_fix.py` - 独立验证脚本

```bash
cd wild-server
python verify_fix.py
# 输出: ✓✓✓ 所有测试通过！修复成功！
```

## 影响范围

### 受影响的功能

- 执行计划的约束编译 (`compile_structured_requirements`)
- Architecture阶段的候选方案验证 (`architecture_requirement_violations`)

### 不受影响的功能

- 前端WebSocket API
- LangGraph图结构
- Architecture节点的方案生成逻辑
- 其他类型的约束识别（组件、元素、尺寸等）

### 兼容性

✅ 向后兼容 - 只是修正了错误的识别逻辑，不影响正确的case

## 总结

这是一个**语义理解错误**导致的约束编译bug：

- **症状**：LangSmith Studio失败，前端正常
- **根因**：层数约束识别逻辑过于宽松，把楼层属性描述误判为总层数约束
- **修复**：加强识别条件，明确区分"总层数约束"和"楼层属性描述"
- **验证**：所有测试通过，原始错误场景已修复

修复后，系统能正确理解：
- "共三层几何结构" → 这是层数约束
- "一层层高2.8米" → 这是层高描述，不是层数约束
- "一层外墙材质" → 这是材质描述，不是层数约束
