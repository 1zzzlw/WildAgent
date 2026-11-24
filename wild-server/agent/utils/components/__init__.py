"""构件类型注册、能力与声明式配方。

``registry`` 是所有构件类型的**元数据中心**，被 compiler / plan / api / design /
prompts / repair 等多个域读取——它是生成链的对外契约之一。

模型节点工厂与后处理编排位于 ``agent.workflows.execution``。
"""
from __future__ import annotations

from agent.utils.components.registry import COMPONENT_REGISTRY
from agent.utils.components.registry import ComponentConfig
from agent.utils.components.registry import component_rules_source
from agent.utils.components.registry import generic_component_config
from agent.utils.components.registry import get_implemented_components
from agent.utils.components.registry import resolve_component_suggestions

__all__ = [
    "COMPONENT_REGISTRY",
    "ComponentConfig",
    "component_rules_source",
    "generic_component_config",
    "get_implemented_components",
    "resolve_component_suggestions",
]
