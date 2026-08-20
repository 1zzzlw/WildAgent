---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 120c9aab85e3ed979ff6cbda3bbcb633_9c32ec329c4911f19155525400826444
    ReservedCode1: BeDJb5gqCFJGZ3QzIx30UGPI+ch6eXeDGx1YLHvz9aNN6a/aotLStRENiqI7ypZ6MX1dROLpGOnRTyuNsJwkko2KJDgKsPEX0qQuzz9YlMiVPJEb6V9x76LtrjR0EqRLS0l2eO7snryD14kqS6N4+Pf6Gop+6jUfQYrdQZYREnFjZa+bF+nBodM3AzM=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 120c9aab85e3ed979ff6cbda3bbcb633_9c32ec329c4911f19155525400826444
    ReservedCode2: BeDJb5gqCFJGZ3QzIx30UGPI+ch6eXeDGx1YLHvz9aNN6a/aotLStRENiqI7ypZ6MX1dROLpGOnRTyuNsJwkko2KJDgKsPEX0qQuzz9YlMiVPJEb6V9x76LtrjR0EqRLS0l2eO7snryD14kqS6N4+Pf6Gop+6jUfQYrdQZYREnFjZa+bF+nBodM3AzM=
---



# blueprint 包测试

## 用途

验证 Blueprint（用户手绘/上传的平面图）处理链路：文本归一化、结构化文本提取与材质验证。保证输入图纸能被正确解析并转化为 Agent 可用的结构化数据。

## 覆盖范围

| 测试文件 | 作用 |
|---|---|
| `test_blueprint_normalizer.py` | Blueprint 归一化：文本清洗与标准化格式 |
| `test_blueprint_text_extraction.py` | 文本提取：从 Blueprint 解析房间、尺寸、门窗等结构化信息 |
| `test_blueprint_material_validation.py` | 材质验证：Blueprint 材质标注与空间工具的联动校验 |

## 单独运行

在 `wild-server` 目录下（已激活 `.\.venv\Scripts\activate`）：

```bash
python -m pytest tests/blueprint -v
```

运行单个文件：

```bash
python -m pytest tests/blueprint/test_blueprint_normalizer.py -v
```
## 测试文件详解与结果解读

| 文件 | 用例 | 覆盖点 | 运行命令 |
|---|---|---|---|
| `test_blueprint_material_validation.py` | 14 | 材质与几何归一化/拒绝：hex 颜色与墙高简写归一化、家具别名归一化、基本盒体尺寸归一化、非法尺寸/缺 base_color 拒绝、合法颜色与程序化砖材质接受、程序化字段非法拒绝、程序化与图片纹理互斥、非法坐标拒绝、楼板坐标从墙足迹与楼层推断、无坐标又无足迹的楼板保持非法 | `python -m pytest tests/blueprint/test_blueprint_material_validation.py -v` |
| `test_blueprint_normalizer.py` | 6 | 蓝图归一化：剥离未知字段、交互修复、z 轴修复、墙体去重、旧 column 转换、幂等 | `python -m pytest tests/blueprint/test_blueprint_normalizer.py -v` |
| `test_blueprint_text_extraction.py` | 9 | 蓝图/补丁文本提取：无围栏蓝图在推理 JSON 后找到、补丁提取不依赖蓝图形态、常见模型包装器内找到、同行围栏+operation 数组、add_material 别名归一化、归一化填充确定性 metadata、非法容器类型保留给 schema 错误、推理标记跳过规划提及 | `python -m pytest tests/blueprint/test_blueprint_text_extraction.py -v` |

**预期结果与结果怎么看**：
- 三个文件合计 29 个用例，标准环境下应全部 `PASSED`（末尾 `29 passed`）。
- 失败定位：`FAILED tests/blueprint/<文件>.py::<类名>::<函数>`。材质验证失败多为规则变更，文本提取失败多为提取正则/包装器形态变化。重跑单条：
  ```bash
  python -m pytest tests/blueprint/test_blueprint_material_validation.py::BlueprintMaterialValidationTest::test_missing_base_color_is_rejected -v
  ```
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
