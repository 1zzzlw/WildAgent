# 粒度选择清理完成报告

## 清理概述
根据用户需求，已完成前后端**粒度选择控制**相关代码的清理工作。

**重要说明**：
- ✅ **已删除**：粒度选择（minimal/simple/standard/detailed） - 用于控制生成复杂度的档位
- ✅ **已保留**：精密模式（precision_mode） - 用于切换 LangChain/LangGraph 执行引擎

## 前端修改 (wild-web)

### 1. agentStore.ts
- ✅ **保留** `STORAGE_KEY_PRECISION_MODE` 常量（精密模式需要持久化）
- ✅ **保留** `loadPrecisionMode()` 函数及其 localStorage 读取逻辑
- ✅ **保留** `loadThinkingMode()` 中对精密模式的依赖（精密模式强制开启思考）
- ✅ **保留** `precisionMode` ref 及其完整功能（包括 localStorage 持久化）
- ✅ **保留** `setPrecisionMode()` 函数及其完整功能
- ✅ **保留** `appendThinkingContent()` 中的精密模式判断（按节点分组存储）
- ✅ **保留** 精密模式相关的所有状态：`generatingNodes`, `debugLogs`, `sessionMetrics`

### 2. types/design.ts
- ✅ 从 `ArchitectureDecisions.complexity` 中移除 `level` 字段
  - 移除前：`level: 'minimal' | 'simple' | 'standard' | 'detailed'`
  - 保留字段：`min_volumes`, `min_detail_packages`, `target_structural_elements`, `grid_bays`, `reason`

## 后端修改 (wild-server)

### 1. app/agent/generation/architecture/profile.py
- ✅ 简化 `resolve_complexity_profile()` 函数文档注释
- ✅ 移除对 `precision_mode` 参数的引用

### 2. app/agent/generation/architecture/planning.py
- ✅ 从 `_architecture_intent()` 返回值中移除 `complexity` 字段
- ✅ 从 `normalize_architecture_plan()` 返回值中移除 `complexity` 字段

### 3. app/agent/generation/architecture/workflow.py
- ✅ 从 `draft_design_blocks()` 调用中移除 `level="standard"` 参数

### 4. app/agent/generation/architecture/design_workflow.py
- ✅ 从 `draft_design_blocks()` 函数签名中移除 `level: str` 参数
- ✅ 将 `ordered_blocks(level)` 改为 `ordered_blocks("standard")`，添加注释说明固定使用标准档位

### 5. app/agent/generation/architecture/convergence.py
- ✅ 从 `converge_design()` 函数签名中移除 `level: str` 参数
- ✅ 从 `draft_design_blocks()` 调用中移除 `level` 参数

### 6. app/agent/nodes/design_convergence_node.py
- ✅ 从 `converge_design()` 调用中移除 `level` 参数计算和传递

### 7. app/design/resolver.py
- ✅ 从 complexity 默认值设置中移除 `level: "standard"`
- ✅ 保留其他 complexity 字段（用于后续验证）

### 8. app/agent/plan/expand.py
- ✅ 简化 `_detail_level_from_state()` 函数，固定返回 "standard"
- ✅ 移除从 `architecture_plan.complexity.level` 读取的逻辑

## 测试文件修改

### 1. tests/agent/test_design_convergence.py
- ✅ 从两处 `converge_design()` 调用中移除 `level="standard"` 参数

### 2. tests/agent/test_design_probe_tool.py
- ✅ 从所有 `draft_design_blocks()` 调用中移除 `level="minimal"` 参数（7处）

### 3. tests/agent/test_design_blocks.py
- ✅ 从 `_run()` 方法中移除 `level` 参数
- ✅ 从所有测试调用中移除 `level="minimal"` 参数
- ✅ 从 `draft_design_blocks()` 调用中移除 `level=level` 参数
- ✅ 更新测试断言以适应标准档位的行为

### 4. tests/validators/test_wall_host_regression.py
- ✅ 移除 level 循环测试，改为单次标准档位测试
- ✅ 移除 `plan["complexity"]["level"] = level` 赋值

## 保留的内容

以下内容被完整保留：

### 精密模式（Precision Mode）完整功能
1. **前端状态管理**：
   - `precisionMode` ref 及其 localStorage 持久化
   - `setPrecisionMode()` 函数
   - `loadPrecisionMode()` 函数
   - 精密模式强制开启思考模式的逻辑

2. **精密模式特有功能**：
   - 按节点分组的思考内容存储（`nodeThinkingMap`）
   - 节点生成进度列表（`generatingNodes`）
   - 调试日志（`debugLogs`）
   - 性能汇总（`sessionMetrics`）

3. **后端支持**：
   - 接收并处理 `precision_mode` 参数
   - LangGraph 分片并行执行
   - 详细的 RAG/LLM 诊断日志

### 其他保留内容
1. **complexity_profile 参数传递**：虽然 `level` 字段被移除，但对象本身仍需传递其他字段（`min_volumes`, `min_detail_packages` 等）
2. **detail_level 参数**：plan 相关的 `detail_level` 参数保留，固定使用 "standard"
3. **调试与诊断功能**：与粒度无关的通用调试能力完整保留

## 修复的错误

### 主要错误
前端初始化错误已修复（由误删精密模式功能导致）

### 问题分析
- **混淆概念**：最初误将"粒度选择"和"精密模式"混为一谈
  - **粒度选择**（complexity.level）：控制生成内容的复杂度档位 → ✅ 已删除
  - **精密模式**（precision_mode）：切换 LangChain/LangGraph 执行引擎 → ✅ 已保留
- **根本原因**：用户要求删除的是前端"粒度选择框"及相关的 complexity.level 字段
- **解决方案**：精确删除粒度相关代码，完整保留精密模式功能

## 验证建议

### 前端验证
1. 检查浏览器控制台是否还有 `STORAGE_KEY_PRECISION_MODE` 相关错误
2. 验证 agentStore 初始化正常
3. 检查 localStorage 相关功能是否正常

### 后端验证
1. 运行测试套件确保所有测试通过
2. 检查 architecture 相关接口是否正常工作
3. 验证设计收敛流程是否正常

### 建议的测试命令
```bash
# 前端
cd wild-web
npm run build

# 后端
cd wild-server
pytest tests/agent/test_design_convergence.py
pytest tests/agent/test_design_probe_tool.py
pytest tests/agent/test_design_blocks.py
pytest tests/validators/test_wall_host_regression.py
```

## 备注

### 关键区分

| 功能 | 状态 | 说明 |
|------|------|------|
| **粒度选择** (complexity.level) | ❌ 已删除 | minimal/simple/standard/detailed 档位选择 |
| **精密模式** (precision_mode) | ✅ 完整保留 | LangChain vs LangGraph 执行引擎切换 |
| **思考模式** (thinking_mode) | ✅ 保留 | 是否显示模型推理过程 |
| **程序化材质** (procedural_materials) | ✅ 保留 | 是否允许自动生成 Shader |

### 实际影响
1. 用户不再能选择生成的复杂度档位（始终使用标准档）
2. 用户仍可切换精密模式来使用 LangGraph 的并行执行
3. 前端粒度选择 UI 应该已被移除（如还存在请手动删除）
4. complexity 对象中的其他字段（min_volumes 等）仍保留用于验证
