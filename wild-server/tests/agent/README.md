---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 120c9aab85e3ed979ff6cbda3bbcb633_9affa8eb9c4911f184de525400f8a581
    ReservedCode1: fntON2zO2b0lKlw6hAtNrtLhfE4w7XbQke9+vYIB84mGXsOd7yI3Feh1hzUu5m6TAp5Lo+DvM29lagmWixFeJmS3VAiiLhLTnwMSmENVlgcLXLSfqnpUKt8/+rMaG+C/e+7zcjkPP0oEbKHSzXUvZxBVsVxrCgD8m3iqD48XPOjvkCUR6nVsd1KrAzk=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 120c9aab85e3ed979ff6cbda3bbcb633_9affa8eb9c4911f184de525400f8a581
    ReservedCode2: fntON2zO2b0lKlw6hAtNrtLhfE4w7XbQke9+vYIB84mGXsOd7yI3Feh1hzUu5m6TAp5Lo+DvM29lagmWixFeJmS3VAiiLhLTnwMSmENVlgcLXLSfqnpUKt8/+rMaG+C/e+7zcjkPP0oEbKHSzXUvZxBVsVxrCgD8m3iqD48XPOjvkCUR6nVsd1KrAzk=
---



# agent 包测试

## 用途

验证 WildAgent 核心 Agent 执行链路：LangGraph 图的执行流程、路由决策与结果交付机制。覆盖 Agent 从收到用户请求、生成蓝图/补丁到流式交付给前端的完整主链路，以及 plan 模式的“动态任务 → 结构化要求 → 节点消费 → 验收结果”闭环。

## 覆盖范围

| 测试文件 | 用例 | 作用 |
|---|---:|---|
| `test_agent_graph_execution.py` | 5 | 真实编译图验证 generate/edit/chat 三条分支、公开输入字段与已下线节点 |
| `test_agent_graph_routing.py` | 29 | 意图、复杂度跳过、组件派发与重试预算等条件路由 |
| `test_plan_mode_acceptance.py` | 4 | plan 模式端到端：真实 `interrupt` 审核、阶段进度、逐条业务验收与阻断交付 |
| `test_execution_plan.py` | 21 | 计划契约、结构化要求编译精度、逐条验收与任务状态计算（纯逻辑） |
| `test_architecture_node_smoke.py` | 2 | 真实 architecture 节点无模型冒烟：只打桩模型与检索，其余走真实归一化与 DesignDocument 契约 |
| `test_agent_module_boundaries.py` | 5 | 目录边界：节点入口体积、禁止反向依赖、禁止引用已退休模块 |
| `test_agent_delivery.py` | 5 | 结果交付：重校验覆盖、被拒蓝图不落盘、统一文件引用、保存失败 |
| `test_model_errors.py` | 4 | 模型服务错误分类与终态处理 |
| `test_model_service_block.py` | 5 | 模型服务不可用时的短路与报告 |
| `test_component_prompt.py` | 5 | 组件生成/校验提示词协议 |
| `test_prompt_builders.py` | 5 | 各阶段提示词构建器 |
| `test_web_research_gate.py` | 18 | 受控联网研究的门禁与降级 |
| `test_agent_service_model_reload.py` | 1 | 模型配置热重载 |

## 单独运行

在 `wild-server` 目录下（已激活 `.\.venv\Scripts\activate`）：

```bash
python -m pytest tests/agent -v
```

运行单个文件：

```bash
python -m pytest tests/agent/test_plan_mode_acceptance.py -v
```

## 预期结果与结果解读

- 12 个文件合计 **108 个用例**（`test_execution_plan.py` 与 `test_web_research_gate.py` 含参数化展开），标准环境下应全部 `PASSED`，末尾为 `108 passed`。
- 任一用例失败时，按 `FAILED tests/agent/<文件>::<用例>` 定位。常见原因：
  - 路由或计划契约变化 → 先看 `test_execution_plan.py`、`test_agent_graph_routing.py`；
  - 交付协议变化 → 看 `test_agent_delivery.py`；
  - 节点入口重新变胖（单文件超过 100 行）→ 看 `test_agent_module_boundaries.py`。
- `test_plan_mode_acceptance.py` 使用内存 checkpointer 与确定性 stub，不访问模型、网络或设计仓储，可离线稳定复现。

重跑单条：

```bash
python -m pytest tests/agent/test_execution_plan.py::test_patch_phase_acceptance_never_uses_final_validation -v
```

*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
