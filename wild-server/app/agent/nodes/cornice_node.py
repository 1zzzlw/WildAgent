"""
Layer 1: 檐口组件生成节点
"""
from .base_component_node import create_component_node
from app.agent.component_registry import COMPONENT_REGISTRY

cornice_generator = create_component_node(COMPONENT_REGISTRY["cornice"])
