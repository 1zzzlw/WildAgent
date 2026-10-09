"""设计图纸定稿链：收敛 → 人工审核 → 确定性编译。

这三个节点构成"图纸从草稿到蓝图"的完整生命周期，彼此只通过 state 交接：

    design_convergence（把图纸改到确实编得出来）
        → design_review（interrupt 等人工批准 / 要求修订）
        → compile（图纸 → 蓝图，零模型调用）

 **本包不在 ``__init__`` 里 re-export 这三个入口**：它们分别依赖
``app.agent.compiler``（1668 行）、``langgraph.types``、``app.design.*``，
包初始化不该把它们全部拉起来。请从子模块直接导入，例如
``from app.agent.design_flow.compile import compile_node``。
"""
