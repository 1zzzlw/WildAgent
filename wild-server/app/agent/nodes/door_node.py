"""
Layer 1: 门组件生成节点

输入: user_message, skeleton_summary
输出: door_fragments
"""
from .base_component_node import create_component_node
from app.agent.component_registry import COMPONENT_REGISTRY

door_generator = create_component_node(COMPONENT_REGISTRY["door"])
