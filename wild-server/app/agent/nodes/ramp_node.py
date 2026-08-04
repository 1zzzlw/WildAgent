"""
Layer 1: 坡道组件生成节点
"""
from .base_component_node import create_component_node
from app.agent.component_registry import COMPONENT_REGISTRY

ramp_generator = create_component_node(COMPONENT_REGISTRY["ramp"])
