---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 120c9aab85e3ed979ff6cbda3bbcb633_9ce118159c4911f19155525400826444
    ReservedCode1: rptldFiv/MJXfCu7KqGmW8mWrYilpUYaVk8g85Pw4zCcHpl7DG0XGa6eJkdb7BX1KeQI+mCyv/Pkkv+oUe9sZ5U+5+1lF37Jiff6EhOA7iJAgut2e9/SU7FIjCM4SApn0dtI5f0a+7RugBpjufJz+ShQAqpyph8JRDus9+7FSeo1yUzbJHE0tanKM4w=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 120c9aab85e3ed979ff6cbda3bbcb633_9ce118159c4911f19155525400826444
    ReservedCode2: rptldFiv/MJXfCu7KqGmW8mWrYilpUYaVk8g85Pw4zCcHpl7DG0XGa6eJkdb7BX1KeQI+mCyv/Pkkv+oUe9sZ5U+5+1lF37Jiff6EhOA7iJAgut2e9/SU7FIjCM4SApn0dtI5f0a+7RugBpjufJz+ShQAqpyph8JRDus9+7FSeo1yUzbJHE0tanKM4w=
---



# components 包测试

## 用途

验证组件生成链路：Agent 按架构规划生成建筑组件（墙、立面、材质等）的 Blueprint 与 ScenePatch，并保证组件状态可正确合并与重检。

## 覆盖范围

| 测试文件 | 作用 |
|---|---|
| `test_component_blueprint.py` | 组件蓝图：组件级 Blueprint 生成与解析 |
| `test_component_state_reducer.py` | 状态合并：组件状态的红ucer合并逻辑 |
| `test_component_validation_recheck.py` | 验证重检：组件生成后的二次校验 |
| `test_architecture_plan.py` | 架构规划：整体建筑架构方案生成（空间工具联动） |
| `test_facade_recipe.py` | 立面配方：建筑立面生成配方 |
| `test_material_plan.py` | 材质规划：建筑材质方案规划（含 prompt 组装） |

## 单独运行

在 `wild-server` 目录下（已激活 `.\.venv\Scripts\activate`）：

```bash
python -m pytest tests/components -v
```

运行单个文件：

```bash
python -m pytest tests/components/test_architecture_plan.py -v
```
## 测试文件详解与结果解读

| 文件 | 用例 | 覆盖点 | 运行命令 |
|---|---|---|---|
| `test_architecture_plan.py` | 39 | 架构规划核心：最小请求保持单墙、幕墙密集立面不可被模型覆盖、高层示意跳过逐层检查、U 形平面并集周长与阳台槽位、高细节模式骨架编译、洞口/入口附件贴合、楼层数中文语义、商用/公共轮廓排序 | `python -m pytest tests/components/test_architecture_plan.py -v` |
| `test_component_blueprint.py` | 5 | 构件蓝图后端校验：受支持构件通过、id 命名空间统一、未知字段拒绝、门窗深度字段支持、场景补丁增改删 | `python -m pytest tests/components/test_component_blueprint.py -v` |
| `test_component_validation_recheck.py` | 8 | 构件修复重校验：修复后重校验通过、失败不谎报成功、必填 false 不视为缺失、地面/溢出阳台重定位到上层墙、双全宽阳台不同墙、失败不进入 merge | `python -m pytest tests/components/test_component_validation_recheck.py -v` |
| `test_facade_recipe.py` | 4 | 立面配方：从知识库加载幕墙参数、忽略最小示例 JSON、只提取已知键、越界值钳制 | `python -m pytest tests/components/test_facade_recipe.py -v` |
| `test_material_plan.py` | 17 | 材质计划：prompt 目录不含纹理 URL、资产解析仅接受存在且角色兼容、程序化砖需显式选择、幕墙保持中性立面、无 PBR 资产时跳过 LLM | `python -m pytest tests/components/test_material_plan.py -v` |
| `test_component_state_reducer.py` | 1 | 验证并行组件节点可安全写入通用 State 映射 | `python -m pytest tests/components/test_component_state_reducer.py -v` |

**预期结果与结果怎么看**：
- 常规环境下 6 个文件应全部 `PASSED`（合计 74 个用例），末尾输出 `74 passed`。
- 失败定位：`FAILED tests/components/<文件>.py::<类名>::<函数>`；`test_architecture_plan.py` 失败多与规划硬约束（楼层/立面/洞口）有关，重跑单条即可复现：
  ```bash
  python -m pytest tests/components/test_architecture_plan.py::test_curtain_wall_fills_all_facade_slots_regardless_of_quota -v
  ```
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
