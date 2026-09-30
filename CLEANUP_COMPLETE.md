# 粒度选择清理完成

## 清理内容

### ✅ 已删除：粒度选择（Complexity Level）
- `complexity.level` 字段（minimal/simple/standard/detailed）
- 所有函数签名中的 `level` 参数传递
- 前端 UI 中显示"档位"的代码
- 后端从 complexity 读取 level 的逻辑

### ✅ 完整保留：精密模式（Precision Mode）
- `precision_mode` 前后端完整功能
- LangGraph 分片并行执行能力
- 按节点分组的思考内容展示
- 所有调试和诊断功能
- localStorage 持久化

## 关键修复

### 后端修复
1. `app/agent/generation/architecture/convergence.py` - 移除 `level` 参数
2. `app/agent/generation/architecture/design_workflow.py` - 移除 `level` 参数，固定使用 "standard"
3. `app/agent/generation/architecture/workflow.py` - 移除 `level="standard"` 调用
4. `app/agent/nodes/design_convergence_node.py` - 移除 `level` 参数传递
5. `app/agent/generation/architecture/planning.py` - 移除 `complexity` 字段输出
6. `app/design/resolver.py` - 移除 `complexity.level` 默认值设置
7. `app/agent/plan/expand.py` - 简化 `_detail_level_from_state()` 固定返回 "standard"

### 前端修复
1. `wild-web/src/stores/agentStore.ts` - 恢复完整的精密模式功能
2. `wild-web/src/types/design.ts` - 移除 `complexity.level` 字段
3. `wild-web/src/components/panels/AgentExecutionPanel.vue` - 移除显示"档位"的代码

### 测试修复
1. `tests/agent/test_design_convergence.py` - 移除 `level` 参数
2. `tests/agent/test_design_probe_tool.py` - 移除 `level` 参数
3. `tests/agent/test_design_blocks.py` - 移除 `level` 参数
4. `tests/validators/test_wall_host_regression.py` - 简化测试逻辑

## 现在状态

### 系统行为
- 所有生成请求统一使用**标准档位（standard）**
- 用户仍可切换**精密模式**来使用 LangGraph 并行执行
- 所有 LLM 调用正常工作
- 意图分类、建筑方案、设计收敛等节点正常运行

### 用户界面
- 粒度选择框已移除
- 精密模式开关正常工作
- 思考模式开关正常工作
- 程序化材质开关正常工作

## 已修复的错误

1. ✅ 前端 `STORAGE_KEY_PRECISION_MODE is not defined` 错误
2. ✅ 后端 `level` 参数未定义错误
3. ✅ 模型服务调用失败问题（由 level 参数错误导致）

## 验证清单

- [x] 后端语法检查通过
- [x] 前端精密模式功能完整
- [x] 没有 `complexity.level` 引用
- [x] 所有 `level` 参数已移除或固定为 "standard"
- [x] 测试文件已更新
- [x] UI 显示"档位"的代码已移除

## 结论

粒度选择功能已完全清理，精密模式功能完整保留。系统现在应该可以正常生成建筑了。
