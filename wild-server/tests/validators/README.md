---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 120c9aab85e3ed979ff6cbda3bbcb633_a07662a39c4911f184de525400f8a581
    ReservedCode1: 27jHAA91o1TrpIqJGvIBgC4ISJ07/Y6ocnqfDr6zMNidvuB7F7OlCbhklAiVUq2Swu5KiCfY8PA1Io0FMTsBbQA9Z3sIsahYlYNqFj6JxOdgC9OE8kPg3sEvc8FbMyo9xhLRyhVuCQUvKwiULKLCut/KMAb2pK123TuWbgL+bZXKc/MKErcMwWPStlc=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 120c9aab85e3ed979ff6cbda3bbcb633_a07662a39c4911f184de525400f8a581
    ReservedCode2: 27jHAA91o1TrpIqJGvIBgC4ISJ07/Y6ocnqfDr6zMNidvuB7F7OlCbhklAiVUq2Swu5KiCfY8PA1Io0FMTsBbQA9Z3sIsahYlYNqFj6JxOdgC9OE8kPg3sEvc8FbMyo9xhLRyhVuCQUvKwiULKLCut/KMAb2pK123TuWbgL+bZXKc/MKErcMwWPStlc=
---



# validators 包测试

## 用途

验证生成结果的校验体系：P0/P1/P2 质量优化、空间几何校验与验证缓存。保证 Agent 产出的 Blueprint/ScenePatch 在结构、事实、推理与空间约束上正确。

## 覆盖范围

| 测试文件 | 作用 |
|---|---|
| `test_p0_implementation.py` | P0 优化：结构自检、查询改写 |
| `test_p1_p2_implementation.py` | P1/P2 优化：事实自检、工具自检、推理自检 |
| `test_spatial_validation.py` | 空间验证：墙体、门窗、尺寸等几何约束校验 |
| `test_spatial_invariants.py` | 空间不变量：跨操作保持的几何不变量 |
| `test_validation_cache.py` | 验证缓存：校验结果缓存与失效 |
| `test_validation_pipeline_repairs.py` | 验证管道修复：校验失败后的自动修复流程 |

## 单独运行

在 `wild-server` 目录下（已激活 `.\.venv\Scripts\activate`）：

```bash
python -m pytest tests/validators -v
```

运行单个文件：

```bash
python -m pytest tests/validators/test_spatial_validation.py -v
```
## 测试文件详解与结果解读

| 文件 | 用例 | 覆盖点 | 运行命令 |
|---|---|---|---|
| `test_spatial_validation.py` | 21 | 空间验证核心：重复墙/重叠柱判模型质量错误、分离结构通过、构件世界坐标投影回父墙、零高楼层墙从楼板补齐、声明高度与端点一致、尺寸修复保留/移除冲突、缺材质引用拒绝、材质别名修复、开口适配墙高、重叠门窗拒绝、平窗重定位/剪枝、凸窗避让、楼板与阳台非碰撞、开敞栏杆墙不吸附、L 形缺角修复/T 形合法、结构梁柱嵌入墙合法、台阶屋顶贴合顶层 | `python -m pytest tests/validators/test_spatial_validation.py -v` |
| `test_p0_implementation.py` | 9 | P0 方案：结构校验器/查询改写器/域配置可导入，域配置加载与实体类型查找等 | `python -m pytest tests/validators/test_p0_implementation.py -v` |
| `test_p1_p2_implementation.py` | 12 | P1/P2：事实/工具/推理自检与混合检索可导入，混合检索初始化与 get_stats 等 | `python -m pytest tests/validators/test_p1_p2_implementation.py -v` |
| `test_spatial_invariants.py` | 2 | 空间不变量：墙包围盒机器可读、不变量保持墙框与楼层标高 | `python -m pytest tests/validators/test_spatial_invariants.py -v` |
| `test_validation_pipeline_repairs.py` | 2 | 校验管线修复：校验问题使用有限根因类别、材质别名在最终引用结果前修复 | `python -m pytest tests/validators/test_validation_pipeline_repairs.py -v` |
| `test_validation_cache.py` | 2 | 验证 merge→final_validate 校验结果复用 | `python -m pytest tests/validators/test_validation_cache.py -v` |

**预期结果与结果怎么看**：
- 六个文件合计 48 个用例，标准环境下应全部 `PASSED`（末尾 `48 passed`）。
- 失败定位：`FAILED tests/validators/<文件>.py::<类名>::<函数>`；`test_spatial_validation.py` 失败多为空间约束规则/修复策略回归，重跑单条：
  ```bash
  python -m pytest tests/validators/test_spatial_validation.py::SpatialValidationTest::test_openings_fit_walls_with_explicit_height -v
  ```
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
