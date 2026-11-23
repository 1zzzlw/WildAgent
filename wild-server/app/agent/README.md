# Agent 目录与职责

`app/agent` 负责 LangGraph 编排、模型设计与修订。确定性的设计解析、蓝图编译、空间计算和校验放在 `app/domain`；模型连接和检索实现放在 `app/infrastructure`；任务生命周期与结果保存由 `app/application/generation` 管理。

```text
agent/
├── graph.py                  # 注册节点、连接边和条件路由
├── state.py                  # 持久化图状态与状态合并
├── runtime.py                # 不写入 checkpoint 的资源引用和请求回调
├── nodes/                    # 图节点薄入口
├── workflows/
│   ├── intent/               # 意图分类
│   ├── design/               # 建筑和物件共用的图纸生成
│   ├── material/             # 材质选择
│   ├── planning/             # 动态任务规划与重规划
│   ├── execution/            # 构件实现与处理
│   ├── assembly/             # 装配与编译阶段编排
│   ├── validation/           # 校验流程与模型诊断
│   ├── editing/              # 场景 Patch 生成
│   ├── repair/               # 基于失败证据的模型修订
│   ├── knowledge/            # 问答与受控研究
│   ├── vision/               # 离线视觉审核和候选修订
│   └── assets/               # 独立 PBR 资源工作流
├── prompts/                  # 各阶段提示词构建器
└── tools/                    # 按需诊断工具和 LangChain 工具包装
```

阅读主链从 `graph.py` 开始，通过 `nodes/*_node.py` 进入对应工作流。建筑和物件共用 `architecture → material_plan → plan → execute / replanner → compile → final_validate`。Plan 根据已确认图纸展开任务并准备初始蓝图。

图纸与材质通过设计契约校验、保存并确定版本后自动继续。`design_ready` 事件用于展示，不创建人工审核中断。节点进度只说明流程走到哪里，不能代替业务验收和视觉确认；校验失败时可保留已有可编辑实体，同时明确返回失败状态。

离线视觉审核通过 `python -m app.agent.workflows.vision.workflow` 启动，调用 `app.agent.tools.vision.proxy_evaluate` 读取蓝图并生成 `proxy.json`。该工具也可直接从 Python 调用。人工审核仍以对应版本的渲染截图为依据。

依赖约定：

- `graph.py` 调用节点，节点从所属工作流包的公开入口导入；包在 `__init__.py` 的 `__all__` 中列出公开名称。
- 工作流可调用领域计算和基础设施，不反向导入 API、应用用例或 bootstrap。
- `domain` 不导入 Agent、API、应用层或基础设施，也不创建模型和数据库资源。
- 确定性校验实现在 `domain/validation`；`agent/tools/spatial.py` 只包装模型可调用的工具。
- 模型客户端和知识加载器由 `bootstrap/resources.py` 显式创建，`runtime.py` 保存稳定引用。
- 新功能优先复用现有工作流与通用计算入口，不在节点、提示词中复制几何规则。

外部请求先进入 `application/generation/runner.py`。执行上下文、流事件投影、结果交付分别位于 `context.py`、`streaming.py`、`finalize.py`；持久化任务和断线补发位于 `jobs.py`。REST 业务用例位于 `application`，HTTP 状态码与响应格式在 `api` 适配。
