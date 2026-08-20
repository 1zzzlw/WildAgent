---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 120c9aab85e3ed979ff6cbda3bbcb633_9b9841ed9c4911f19046525400287e28
    ReservedCode1: 1L0A4bsa/73pV5adEGJPfNgz6rX3GvBNZCTBRrF29E3ZwFyJqRM1Xgz520rym43BAOfly1BtorISt6h18Gt7TRkfb3JVAc2w5xZo6UeA4EnyZKAZ1lADn57O6w5/pAr8DgPQvxTKALPMOOwihdjCrep1RTK8cUjeuGKs6o+fOS107Y9K82YYdIDXkIQ=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 120c9aab85e3ed979ff6cbda3bbcb633_9b9841ed9c4911f19046525400287e28
    ReservedCode2: 1L0A4bsa/73pV5adEGJPfNgz6rX3GvBNZCTBRrF29E3ZwFyJqRM1Xgz520rym43BAOfly1BtorISt6h18Gt7TRkfb3JVAc2w5xZo6UeA4EnyZKAZ1lADn57O6w5/pAr8DgPQvxTKALPMOOwihdjCrep1RTK8cUjeuGKs6o+fOS107Y9K82YYdIDXkIQ=
---



# assets 包测试

## 用途

验证材质与资产相关能力：材质调优、PBR 资产注册与加载、模型客户端兼容性，保证渲染资产与 LLM 模型调用的可靠性。

## 覆盖范围

| 测试文件 | 作用 |
|---|---|
| `test_material_tuning.py` | 材质调优：材质参数优化与推荐 |
| `test_pbr_assets.py` | PBR 资产：资产图注册、存储与 API 访问 |
| `test_model_client_compat.py` | 模型客户端兼容：不同模型后端客户端的兼容行为 |

## 单独运行

在 `wild-server` 目录下（已激活 `.\.venv\Scripts\activate`）：

```bash
python -m pytest tests/assets -v
```

运行单个文件：

```bash
python -m pytest tests/assets/test_pbr_assets.py -v
```
## 测试文件详解与结果解读

| 文件 | 用例 | 覆盖点 | 运行命令 |
|---|---|---|---|
| `test_material_tuning.py` | 11 | 材质调优：安全协议拒绝误伤（暗纹理/照片/含人/程序化纹理不被当作"换色"对象）、只接受明确调优意图、拒绝夸大描述、场景选择缺参照时挂到墙面、独立优化意图按构件收窄、多材质指令收窄、颜色基调意图拒绝、图片意图收窄 | `python -m pytest tests/assets/test_material_tuning.py -v` |
| `test_pbr_assets.py` | 9 | PBR 资产：本地仓库存储与 manifest 一致性、路径/api 解析、上传后可从网络 URL 读取、删除时引用计数、法线贴图后缀与仓库同步、并发上传合并 | `python -m pytest tests/assets/test_pbr_assets.py -v` |
| `test_model_client_compat.py` | 4 | 模型客户端兼容：内容与推理字段双通道、不同模型返回形态兼容 | `python -m pytest tests/assets/test_model_client_compat.py -v` |

**预期结果与结果怎么看**：
- 三个文件合计 21 个用例，标准环境下应全部 `PASSED`（末尾 `21 passed`）。
- 失败定位：`FAILED tests/assets/<文件>.py::<类名>::<函数>`；`test_material_tuning.py` 失败多为调优意图识别规则回归，`test_pbr_assets.py` 失败多为资产仓库路径/计数逻辑回归。重跑单条：
  ```bash
  python -m pytest tests/assets/test_material_tuning.py::MaterialTuningTest::test_dark_texture_is_not_interpreted_as_color_change -v
  ```
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
