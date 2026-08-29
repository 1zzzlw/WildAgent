# floor_plan/ — 平面方案离线工具

这个目录用于在不启动前后端、不调用大模型的情况下检查 `FloorPlanIR v2`。

## 生成内置示例

在 `wild-server` 目录执行：

```powershell
.\.venv\Scripts\python.exe scripts\floor_plan\preview_floor_plan.py
```

默认写入 `storage/sessions/floor_plan_preview.svg`。内置示例同时包含室内门和立面门窗，因此红色门线、蓝色窗线都应实际出现在建筑轮廓上，而不只是出现在图例中。控制台的 `平面来源` 应为 `model`；如果是 `deterministic_fallback`，继续查看打印出的回退原因。

## 检查自己的 JSON

输入文件需包含 `massing` 和 `spatial_plan`：

```powershell
.\.venv\Scripts\python.exe scripts\floor_plan\preview_floor_plan.py --input .\my_plan.json --output .\storage\sessions\my_plan.svg
```

字段解释、坐标规则和预览颜色见 [建筑平面生成与确认](../../../docs/agent/FLOOR_PLAN_GENERATION_MVP.md)。

多层方案可一次输出全部楼层：

```powershell
.\.venv\Scripts\python.exe scripts\floor_plan\preview_floor_plan.py --input .\my_plan.json --output .\storage\sessions\my_plan.svg --all-levels
```

结果会按 `my_plan_L1.svg`、`my_plan_L2.svg` 命名。输入中如果包含 `volumes` 和 `facades`，脚本会和在线审核图一样使用逐层体量边界并绘制外门窗。
