"""动态组件生成与校验节点工厂入口。

流程：按组件注册信息创建生成节点和校验节点；具体实现位于
``generation.component_workflow``。
"""

from app.agent.generation.component_workflow import (
    create_component_generator,
    create_component_validator,
)

__all__ = ["create_component_generator", "create_component_validator"]
