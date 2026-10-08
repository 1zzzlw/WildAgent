"""构件域：构件类型注册表、构件节点工厂与共享后处理。

``registry`` 是所有构件类型的**元数据中心**，被 compiler / plan / api / design /
prompts / repair 等多个域读取——它是生成链的对外契约之一。

节点工厂（``create_component_generator`` / ``create_component_validator``）见
:mod:`.workflow`，不在此 re-export：那个模块依赖模型客户端。
"""
from __future__ import annotations

from .processing import validate_and_fix_with_tools
from .registry import (
    COMPONENT_REGISTRY,
    ComponentConfig,
    component_rules_source,
    generic_component_config,
    get_implemented_components,
    resolve_component_suggestions,
)

__all__ = [
    "COMPONENT_REGISTRY",
    "ComponentConfig",
    "component_rules_source",
    "generic_component_config",
    "get_implemented_components",
    "resolve_component_suggestions",
    "validate_and_fix_with_tools",
]
