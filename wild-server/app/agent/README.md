# Agent 代码入口

`app/agent` 负责工作流编排与生成业务；共享模型调用在 `app/llm`，输入与事件协议在 `app/contracts`，设计数据在 `app/design`。

## 先看这三个文件

| 文件 | 职责 |
|---|---|
| [graph.py](graph.py) | 注册节点和路由，决定流程怎么走 |
| [state.py](state.py) | 公开输入、完整 State，以及分片合并规则 |
| [runtime.py](runtime.py) | 请求期间的回调与上下文，不写入 checkpoint |

`nodes/` 只保留图节点的薄入口。找到导入目标后，进入对应业务包阅读；节点名称和 trace 名称保持一致。

## 当前主流程

```text
classifier
  ├─ chat → END
  ├─ patch → END
  ├─ architecture → material_plan → design_review → plan
  └─ object_design → material_plan → design_review → skeleton → plan

plan → execute ⇄ replanner → 建筑 compile / 物件合并 → final_validate
```

设计审核可以返回设计节点修订。建筑任务按已批准图纸展开，物件任务保留模型分组策略。模型服务故障或分类输出不合法时提前结束；不要把节点完成当成建筑质量验收通过。

## 业务包

| 包 | 负责什么 | 主要入口 |
|---|---|---|
| `intent/` | 意图、目标类型和形制标签的识别与解析 | [workflow.py](intent/workflow.py) |
| `generation/architecture/` | 建筑设计与设计契约检查 | [workflow.py](generation/architecture/workflow.py) |
| `generation/objects/` | 单个物件的设计 | [workflow.py](generation/objects/workflow.py) |
| `generation/material/` | 材质意图与材质计划 | [workflow.py](generation/material/workflow.py) |
| `generation/skeleton/` | 物件分支的骨架阶段 | [workflow.py](generation/skeleton/workflow.py) |
| `generation/component/`、`generation/spatial/` | 构件生成与空间关系工具 | [component/workflow.py](generation/component/workflow.py) |
| `design_flow/` | 设计审核与已有分片的最终装配 | [review.py](design_flow/review.py)、[compile.py](design_flow/compile.py) |
| `plan/` | 任务展开、执行、对账与重规划 | [workflow.py](plan/workflow.py) |
| `knowledge/` | 问答、检索上下文和受控资料研究 | [chat_workflow.py](knowledge/chat_workflow.py) |
| `validation/`、`repair/` | 候选校验与受限修复 | [validation/workflow.py](validation/workflow.py)、[repair/workflow.py](repair/workflow.py) |
| `compiler/` | 设计编译的底层实现，由 `app/design/compilation.py` 调用 | [compile.py](compiler/compile.py) |
| `prompts/` | 生成与执行阶段的提示词构建器 | [planning.py](prompts/planning.py) |
| `assets/`、`vision/` | 独立资产流程与离线视觉评价，不属于建筑主图 | [assets/graph.py](assets/graph.py)、[vision/workflow.py](vision/workflow.py) |

## 共享代码放在哪里

- 粒度选项与归一化：[app/contracts/generation_options.py](../contracts/generation_options.py)。
- 意图的目标类型判断：[intent/target_kind.py](intent/target_kind.py)，不再放在建筑生成包。
- 设计契约、图纸投影与构件关系：[app/design/](../design/)。
- 模型创建、调用与异常协议：[app/llm/](../llm/)。
- 文档加载与检索：[app/spec/](../spec/) 和 [app/rag/](../rag/)。
- 持久化任务、事件分发与最终保存：[app/services/](../services/)。

特定业务的 Prompt 留在所属包，如 `intent/prompt.py`。意图包不再集中转导实现，分类调用方直接导入具体模块；其他业务包仍保留实际使用的公开接口。

## 依赖规则

1. `graph.py` 通过 `nodes/` 调用业务入口；节点之间不互相导入。
2. 业务包不反向导入 `nodes/` 或 `graph.py`。
3. `intent/` 不依赖具体建筑生成实现；公共输入设置不放进生成算法。
4. State 字段、图节点名称和事件协议保持稳定，移动文件不能改变这些运行契约。

从前端请求到渲染的阅读顺序见 [代码阅读路线](../../../docs/代码阅读路线.md)，详细符号位置见 [项目索引](../../../docs/项目索引.md)。
