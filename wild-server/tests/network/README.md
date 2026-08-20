---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 120c9aab85e3ed979ff6cbda3bbcb633_9e44b6bd9c4911f184de525400f8a581
    ReservedCode1: izl3CiZPmKsh6bLPuyXZgdAMZcap4Lrcud/TeqVa3MdPDyeHzhpLKWDqNqDBHcu++PXcIEGkpb5avC1WRpnWA8psBGh18NB26er+fl4b7S1ilOVNGYDy9E6LjHPNvMah0d/JwnEEP92rxiFrUENTrOHWkOEplIMiSgCj8qwe8U2kpnAcCWIENJf9XRo=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 120c9aab85e3ed979ff6cbda3bbcb633_9e44b6bd9c4911f184de525400f8a581
    ReservedCode2: izl3CiZPmKsh6bLPuyXZgdAMZcap4Lrcud/TeqVa3MdPDyeHzhpLKWDqNqDBHcu++PXcIEGkpb5avC1WRpnWA8psBGh18NB26er+fl4b7S1ilOVNGYDy9E6LjHPNvMah0d/JwnEEP92rxiFrUENTrOHWkOEplIMiSgCj8qwe8U2kpnAcCWIENJf9XRo=
---



# network 包测试

## 用途

验证后端网络与会话链路：WebSocket 断线重连、会话轮次管理、生成任务服务与生成提交，保证前后端长连接交互的稳定性。

## 覆盖范围

| 测试文件 | 作用 |
|---|---|
| `test_ws_agent_disconnect.py` | WebSocket 断线：断线重连、断线期间状态处理 |
| `test_session_turns.py` | 会话轮次：多轮会话的状态累积与切换 |
| `test_generation_job_service.py` | 生成任务服务：任务队列、状态机与取消 |
| `test_generation_commit.py` | 生成提交：生成结果提交与持久化 |

## 单独运行

在 `wild-server` 目录下（已激活 `.\.venv\Scripts\activate`）：

```bash
python -m pytest tests/network -v
```

运行单个文件：

```bash
python -m pytest tests/network/test_ws_agent_disconnect.py -v
```
## 测试文件详解与结果解读

| 文件 | 用例 | 覆盖点 | 运行命令 |
|---|---|---|---|
| `test_generation_commit.py` | 2 | 原子写入与幂等提交：保存原子且无临时文件残留、生成结果提交使用单一交付条目 | `python -m pytest tests/network/test_generation_commit.py -v` |
| `test_session_turns.py` | 4 | Turn 服务端持久化与中断恢复：蓝图描述压缩但手动会话名优先等 | `python -m pytest tests/network/test_session_turns.py -v` |
| `test_ws_agent_disconnect.py` | 15 | WS 断开场景：断流/提前断开等各类断开下的骨架失败原因保留 | `python -m pytest tests/network/test_ws_agent_disconnect.py -v` |
| `test_generation_job_service.py` | 4 | 生成任务服务：任务状态机与查询 | `python -m pytest tests/network/test_generation_job_service.py -v` |

**预期结果与结果怎么看**：
- 四个文件合计 25 个用例，标准环境下应全部 `PASSED`（末尾 `25 passed`）。
- 失败定位：`FAILED tests/network/<文件>.py::<类名>::<函数>`；原子写入失败多与文件系统/交付协议有关，WS 断开失败多与会话状态清理有关。重跑单条：
  ```bash
  python -m pytest tests/network/test_generation_commit.py::AtomicSaveTest::test_save_is_atomic_and_leaves_no_temp_file -v
  ```
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
