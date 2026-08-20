---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 120c9aab85e3ed979ff6cbda3bbcb633_9facd7b69c4911f19155525400826444
    ReservedCode1: +0Yh3iIfqWcKL3MeRnZJxJSAMwswSGlt7UPRC011XL3hYOLRw2mmGeQr2VtupUa3uV4eCOQLWEVmamH9tb7EoIkcdiAkuOVqQQ2ZQXcYfv/VsNpPuOvnAPIKAwp7VXopjegNctQRFsG+wzuVEyv4qRUwh0HgCa00+P2OcM7q8avze5KzCwwbVcJ/Sac=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 120c9aab85e3ed979ff6cbda3bbcb633_9facd7b69c4911f19155525400826444
    ReservedCode2: +0Yh3iIfqWcKL3MeRnZJxJSAMwswSGlt7UPRC011XL3hYOLRw2mmGeQr2VtupUa3uV4eCOQLWEVmamH9tb7EoIkcdiAkuOVqQQ2ZQXcYfv/VsNpPuOvnAPIKAwp7VXopjegNctQRFsG+wzuVEyv4qRUwh0HgCa00+P2OcM7q8avze5KzCwwbVcJ/Sac=
---



# repair 包测试

## 用途

验证定向修复机制：当校验发现 Blueprint/ScenePatch 缺陷时，Agent 通过回调节点、修复工具与精确合并对图纸进行定向修复。

## 覆盖范围

| 测试文件 | 作用 |
|---|---|
| `test_callback_targeted_repair.py` | 回调定向修复：验证-修复循环中回调节点的修复行为 |
| `test_targeted_repair_tools.py` | 定向修复工具：修复工具集的能力与边界 |
| `test_merge_precision.py` | 合并精度：修复结果与原始 Blueprint 的精确合并 |
| `test_skeleton_blueprint_recovery.py` | 骨架恢复：从残缺/失败结果恢复骨架蓝图 |

## 单独运行

在 `wild-server` 目录下（已激活 `.\.venv\Scripts\activate`）：

```bash
python -m pytest tests/repair -v
```

运行单个文件：

```bash
python -m pytest tests/repair/test_targeted_repair_tools.py -v
```
## 测试文件详解与结果解读

| 文件 | 用例 | 覆盖点 | 运行命令 |
|---|---|---|---|
| `test_targeted_repair_tools.py` | 10 | 定向修复工具：动作解析跳过规划数组、同实体多错误保留、立面超额暴露附着开口为修复目标、模型动作只改失败实体、patch 修复门深度、add 只限缺失设计类型、remove 只限相关超额 id、不可碰通过实体/身份字段、材质工具要求已定义材质、修复必须收敛错误 | `python -m pytest tests/repair/test_targeted_repair_tools.py -v` |
| `test_merge_precision.py` | 9 | 合并精度：命名"阳台栏杆"不引入阳台构件、嵌入栏杆满足最小值而非独立最大值、嵌入阳台栏杆不重复构件、缺二层与楼梯触发实现契约失败等 | `python -m pytest tests/repair/test_merge_precision.py -v` |
| `test_callback_targeted_repair.py` | 5 | 回调路由到校验而非重新 merge 等 | `python -m pytest tests/repair/test_callback_targeted_repair.py -v` |
| `test_skeleton_blueprint_recovery.py` | 3 | 骨架蓝图恢复：token 用量合并等 | `python -m pytest tests/repair/test_skeleton_blueprint_recovery.py -v` |

**预期结果与结果怎么看**：
- 四个文件合计 27 个用例，标准环境下应全部 `PASSED`（末尾 `27 passed`）。
- 失败定位：`FAILED tests/repair/<文件>.py::<类名>::<函数>`；`test_targeted_repair_tools.py` 失败多为修复动作权限/收敛规则回归，重跑单条：
  ```bash
  python -m pytest tests/repair/test_targeted_repair_tools.py::TargetedRepairToolsTest::test_repair_must_reduce_errors_without_introducing_new_issue -v
  ```
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
