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

验证 WildAgent 核心 Agent 执行链路：LangGraph 图的执行流程、路由决策与结果交付机制。覆盖 Agent 从收到用户请求、生成蓝图/补丁到流式交付给前端的完整主链路。

## 覆盖范围

| 测试文件 | 作用 |
|---|---|
| `test_agent_graph_execution.py` | Agent 图执行：节点执行顺序、状态传递与更新、错误处理与恢复、验证-修复循环、状态持久化 |
| `test_agent_graph_routing.py` | Agent 图路由：意图分类路由（建筑生成/聊天/补丁生成）、条件分支选择、循环退出条件、验证循环路由 |
| `test_agent_delivery.py` | 结果交付：流式蓝图交付、思考面板增量更新、错误消息传递（前端交互体验） |

## 单独运行

在 `wild-server` 目录下（已激活 `.\.venv\Scripts\activate`）：

```bash
python -m pytest tests/agent -v
```

运行单个文件：

```bash
python -m pytest tests/agent/test_agent_graph_execution.py -v
```
## 测试文件详解与结果解读

| 文件 | 用例 | 覆盖点 | 运行命令 |
|---|---|---|---|
| `test_agent_delivery.py` | 5 | Agent 生成结果统一出口：①重校验覆盖初始校验错误；②被拒蓝图永不落盘；③成功交付使用统一文件引用与回复；④长描述蓝图名压缩为短会话标题；⑤保存失败走专属异常 | `python -m pytest tests/agent/test_agent_delivery.py -v` |
| `test_agent_graph_routing.py` | 12 | 意图与组件派发回归：复杂度跳过、edit/generate 路由、fast path 短路、构件建议过滤未知/否定类型、最低配额派发、阳台防重复栏杆、按目标重试预算 | `python -m pytest tests/agent/test_agent_graph_routing.py -v` |
| `test_agent_graph_execution.py` | 3 | 使用真实编译图验证 generate/edit/chat 三条执行分支 | `python -m pytest tests/agent/test_agent_graph_execution.py -v` |

**预期结果与结果怎么看**：
- 三个文件合计 20 个用例，标准环境下应全部 `PASSED`（`-v` 下每个用例一行 `PASSED`，末尾 `20 passed`）。
- 任一用例失败时，按 `FAILED tests/agent/<文件>.py::<函数>` 定位，多为路由逻辑回归或交付协议变化；重跑单条：
  ```bash
  python -m pytest tests/agent/test_agent_delivery.py::test_rejected_blueprint_is_never_saved -v
  ```
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
