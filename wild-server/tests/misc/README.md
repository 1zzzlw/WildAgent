---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 120c9aab85e3ed979ff6cbda3bbcb633_9d88b4cf9c4911f19155525400826444
    ReservedCode1: fCq0BCC5QjRIl6y8EiRzHheCCYEDlpXW+VuMg0/hViQspD2TpBmyRWg5ajuarICLyHwZqi0ACHCfN7yrlfoyEPCbonf6+BlmyHwl8qG8mTXJL9OLvfge0oTc+0knEM+XGDKrjFuLhAgMlqg7zCEhDCGKQPsOI5EFHIqq0APraJQranDT2BAXL5Uzb5c=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 120c9aab85e3ed979ff6cbda3bbcb633_9d88b4cf9c4911f19155525400826444
    ReservedCode2: fCq0BCC5QjRIl6y8EiRzHheCCYEDlpXW+VuMg0/hViQspD2TpBmyRWg5ajuarICLyHwZqi0ACHCfN7yrlfoyEPCbonf6+BlmyHwl8qG8mTXJL9OLvfge0oTc+0knEM+XGDKrjFuLhAgMlqg7zCEhDCGKQPsOI5EFHIqq0APraJQranDT2BAXL5Uzb5c=
---



# misc 包测试

## 用途

其他横切能力与辅助工具测试：诊断、就绪检查、推理流、Prompt 组合、场景补丁生成、IP 地理定位、部署预检与 LangGraph 断点恢复，以及 LangGraph 图可视化辅助脚本。

## 覆盖范围

| 测试文件 | 作用 |
|---|---|
| `test_diagnostics.py` | 诊断工具：系统/Agent 运行诊断 |
| `test_readiness.py` | 就绪检查：服务启动就绪探测 |
| `test_reasoning_stream.py` | 推理流：推理过程流式输出 |
| `test_prompt_composition.py` | Prompt 组合：多段 Prompt 组装 |
| `test_scene_patch_generation.py` | 场景补丁生成：ScenePatch 生成链路 |
| `test_ip_geolocation.py` | IP 地理定位：Presence 扩展的 IP 归属地 |
| `test_deployment_preflight.py` | 部署预检：部署前环境检查 |
| `test_langgraph_checkpoint_resume.py` | LangGraph 断点恢复：检查点恢复会话 |
| `show_langgraph_graph.py` | 辅助脚本（非测试）：渲染/展示 LangGraph 图结构 |

## 单独运行

在 `wild-server` 目录下（已激活 `.\.venv\Scripts\activate`）：

```bash
python -m pytest tests/misc -v
```

运行单个文件：

```bash
python -m pytest tests/misc/test_scene_patch_generation.py -v
```
## 测试文件详解与结果解读

| 文件 | 用例 | 覆盖点 | 运行命令 |
|---|---|---|---|
| `test_prompt_composition.py` | 7 | Prompt 组合：spec 注入、用户消息注入、RAG 查询意图数限制、metadata 过滤传递、组件类型、调试保留、系统指令前缀 | `python -m pytest tests/misc/test_prompt_composition.py -v` |
| `test_diagnostics.py` | 7 | 诊断 Schema：蓝图指纹（含空/非法变体）、校验快照生成、节点诊断构建 | `python -m pytest tests/misc/test_diagnostics.py -v` |
| `test_deployment_preflight.py` | 5 | 部署预检：默认不访问供应商、显式真实模式调用供应商、响应文本选择与无效响应处理 | `python -m pytest tests/misc/test_deployment_preflight.py -v` |
| `test_ip_geolocation.py` | 4 | IP 地理位置：掩码计算、代理头信任开关、库缺失回退 | `python -m pytest tests/misc/test_ip_geolocation.py -v` |
| `test_scene_patch_generation.py` | 8 | 场景补丁生成：预检、坐标拾取、推理内补丁优先 | `python -m pytest tests/misc/test_scene_patch_generation.py -v` |
| `test_reasoning_stream.py` | 3 | 推理流：thinking 选项注入、推理内容保留 | `python -m pytest tests/misc/test_reasoning_stream.py -v` |
| `test_readiness.py` | 3 | 服务就绪检查 | `python -m pytest tests/misc/test_readiness.py -v` |
| `test_langgraph_checkpoint_resume.py` | 1 | LangGraph 检查点恢复 | `python -m pytest tests/misc/test_langgraph_checkpoint_resume.py -v` |
| `show_langgraph_graph.py` | 辅助 | 非测试：绘制当前 LangGraph 编译图结构，便于观察节点/边拓扑 | `.\.venv\Scripts\python.exe tests\misc\show_langgraph_graph.py` |

**预期结果与结果怎么看**：
- 常规环境下 8 个 pytest 文件应全部 `PASSED`（合计 36 个用例），末尾 `36 passed`。
- 失败定位：`FAILED tests/misc/<文件>.py::<类名>::<函数>`；Prompt 组合失败多为系统提示模板变更，诊断失败多为 Schema 字段变更。重跑单条：
  ```bash
  python -m pytest tests/misc/test_prompt_composition.py::PromptCompositionTest::test_spec_injected_into_system_prompt -v
  ```
- `show_langgraph_graph.py` 不参与 pytest 收集，直接运行生成图（依赖 graphviz 可视化库，未安装时仅打印拓扑文本）。
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
