# 修复元素分类的阶段感知问题

**日期**: 2026-09-16  
**问题**: architecture阶段的规划描述被误识别为element_all，导致检查失败  
**状态**: ✅ 已完成

## 问题描述

前端生成失败，错误信息：
```
错误: 总体方案候选均违反已批准业务要求：req_task_6_1
```

### 错误详情

**req_task_6_1** 描述：
```
明确指定为2层或3层别墅；给出别墅的总体宽、深尺寸（例如：12m x 10m）；
定义墙体、地板等基础元素的生成范围与标高体系
```

- **phase**: architecture
- **错误分类**: element_all
- **问题**: architecture阶段不生成elements，但却要检查元素存在性

### 根本原因

这是**第四次**遇到需求编译器误判问题，揭示了一个更深层的问题：

#### 之前的修复

| 修复 | 问题 | 解决方法 |
|------|------|---------|
| 1. 楼层计数 | "一层外墙"误判为总层数 | 排除楼层属性描述 |
| 2. entrance_bay | 所有立面都有entrance_bay | 条件性字段添加 |
| 3. 质量检查 | "墙体对齐"误判为存在性 | 排除质量关键词 |
| **4. 阶段感知** | **architecture阶段要求元素存在** | **阶段感知+规划描述检测** |

#### 核心问题

之前的修复都集中在**文本特征识别**，忽略了**阶段语义**：

```python
# 旧逻辑：只看文本
if elements and _contains_any(text, ("生成", "包含")):
    return element_all  # ❌ 不管是什么阶段

# 问题场景：
# phase: architecture
# 描述: "定义墙体、地板等基础元素的生成范围"
# → 识别为 element_all
# → consumers: ['skeleton', 'merge', 'final_validate']
# → architecture阶段检查 → 失败！
```

**关键洞察**：
- architecture 阶段只生成 `architecture_plan`（总体方案）
- skeleton 阶段才生成 `elements`（墙体、楼板等几何元素）
- 在 architecture 阶段检查元素存在性，必然失败

## 修复方案

修改 `wild-server/app/agent/planning/requirements.py` 第327-360行：

### 1. 添加规划描述检测

```python
# 规划性描述：定义范围、标高体系、初步划分等，不是要求真的生成
is_planning_description = _contains_any(
    text,
    (
        "定义", "划分", "范围", "标高体系", "初步", "大致",
        "确定", "指定", "给出", "提供依据",
    )
)
```

### 2. 添加阶段感知

```python
# element_all 只应用于真正生成元素的阶段
is_element_generation_phase = phase in ("skeleton", "merge", "final_validate")
```

### 3. 组合判断

```python
if (elements 
    and not is_quality_check           # 不是质量检查
    and not is_planning_description    # 不是规划描述
    and is_element_generation_phase    # 是元素生成阶段
    and _contains_any(text, ("生成", "包含", "必要", "完整", "所有"))):
    return element_all
```

## 修复效果

### 测试场景

| 场景 | phase | 描述 | 旧分类 | 新分类 | 正确性 |
|------|-------|------|--------|--------|--------|
| 规划描述 | architecture | "定义墙体、地板的生成范围" | element_all | phase_outcome | ✅ |
| 元素生成 | skeleton | "生成地下室顶板、一层楼板" | element_all | element_all | ✅ |
| 质量检查 | skeleton | "所有墙体端点对齐，无间隙" | element_all | phase_outcome | ✅ |
| 混合描述 | architecture | req_task_6_1原文 | element_all | architecture_dimensions | ✅ |

### req_task_6_1 修复前后

**修复前**：
```python
kind: element_all
target: blueprint.elements
consumers: ['skeleton', 'merge', 'final_validate']
# ❌ architecture阶段检查元素 → 失败
```

**修复后**：
```python
kind: architecture_dimensions  # 提取了尺寸要求
target: architecture.massing
consumers: ['architecture', 'skeleton', 'final_validate']
# ✅ architecture阶段检查尺寸 → 合理
```

## 测试验证

创建了全面的测试套件：

### 1. `test_comprehensive_element_classification.py`

```bash
$ python test_comprehensive_element_classification.py

【architecture阶段的规划描述】
✅ 正确！识别为 phase_outcome

【skeleton阶段的元素生成要求】
✅ 正确！识别为 element_all

【skeleton阶段的质量检查】
✅ 正确！识别为 phase_outcome

【architecture阶段包含元素关键词的混合描述】
✅ 正确！安全降级为 phase_outcome

【明确的层数约束】
✅ 正确！识别为 architecture_floor_count

======================================================================
✅ 所有测试通过！
```

### 2. 之前的测试仍然通过

```bash
$ python verify_quality_check_fix.py
✅ 所有检查通过！质量检查修复成功！

$ python verify_entrance_bay_fix.py
✅ entrance_bay修复验证通过

$ python tests/test_requirements_floor_count_fix.py
✅ 楼层计数修复验证通过
```

## 影响范围

- **文件**: `wild-server/app/agent/planning/requirements.py`
- **行数**: 327-360
- **影响**: 所有包含元素关键词的验收条件编译
- **风险**: 低 - 只是增加了更多的排除规则

## 深层反思

### 为什么会反复出错？

这是第四次修复同类问题，每次都是"发现新的误判 → 添加排除规则"。根本原因：

1. **关键词匹配的局限性**
   - 无法理解语义
   - 无法理解上下文（阶段）
   - 规则越加越多，维护成本上升

2. **需求描述的复杂性**
   - 自然语言本身就是歧义的
   - LLM生成的任务描述是混合的、非结构化的
   - 一个验收条件可能包含多种要求

3. **分类逻辑的脆弱性**
   - 按优先级顺序匹配，先匹配到就返回
   - 无法处理"一个条件多个分类"的情况
   - 混合描述只能选一个分类或降级

### 为什么这次修复引入了阶段感知？

这是一个**质的改变**：

**之前的修复（文本特征）**：
- 看到"一层外墙" → 不是总层数
- 看到"墙体对齐" → 不是存在性
- **只看说什么，不看在哪里说**

**这次修复（阶段语义）**：
- architecture 阶段 → 不应该检查元素
- skeleton 阶段 → 可以检查元素
- **看说什么，也看在哪里说**

这是从**纯文本分析**向**语义理解**迈出的第一步。

## 长期方案建议

### 方案1：改进Planner提示词（短期，低成本）

要求LLM生成更结构化的验收条件：

```
验收条件格式：
- 存在性: "生成[实体类型]，数量[N]"
- 质量: "[实体类型]的[属性]满足[条件]"
- 关系: "[实体A]与[实体B]的[关系]为[值]"

禁止混合多种要求在一个条件中。
```

### 方案2：LLM辅助编译（中期，中成本）

让LLM理解验收条件：

```python
def _compile_acceptance_with_llm(description, phase):
    prompt = f"""
    阶段: {phase}
    描述: {description}
    
    分类这个验收条件：
    1. 类型: [存在性/质量/关系/主观]
    2. 目标实体: [...]
    3. 操作符: [...]
    4. 期望值: [...]
    """
    return llm.generate(prompt)
```

### 方案3：验收条件DSL（长期，高成本）

定义结构化验收语言：

```yaml
acceptance:
  - type: existence
    entity: floor
    phase: skeleton
    minimum: 2
    
  - type: quality
    entity: wall
    attribute: junction_alignment
    condition: precise
    
  - type: dimension
    entity: building
    width: 12m
    depth: 10m
```

### 当前选择：继续渐进优化

理由：
1. ✅ 快速修复实际问题
2. ✅ 不需要大规模重构
3. ✅ 积累足够的误判案例
4. ✅ 为长期方案提供需求洞察

当误判案例累积到一定程度（如10+个排除规则），再考虑架构级改进。

## 相关修复

本修复是"需求编译器误判修复系列"的第四个：

1. **2026-09-16-langsmith-floor-count-bug-fix.md**
   - 楼层属性 vs 总层数

2. **2026-09-16-entrance-bay-contract-fix.md**
   - 立面字段条件性添加

3. **2026-09-16-quality-check-misclassification-fix.md**
   - 质量检查 vs 存在性要求

4. **本修复**
   - 规划描述 vs 元素生成
   - 阶段感知

## 结论

通过引入**阶段感知**和**规划描述检测**，修复了architecture阶段误判元素存在性的问题。

这次修复标志着从"纯文本特征匹配"向"语义+上下文理解"的转变，为未来的改进奠定了基础。

**关键经验**：
- 📝 文本特征不够，需要理解阶段语义
- 🔄 反复修复同类问题，说明方法论需要升级
- 🎯 渐进优化 + 积累案例 → 指导架构改进
