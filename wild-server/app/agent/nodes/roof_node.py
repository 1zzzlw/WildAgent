"""
Layer 1: 屋顶生成节点

输入: user_message, skeleton_summary
输出: roof_fragment (单个roof对象，因为roof是element不是component)
"""
from .base_component_node import create_component_node
from app.agent.component_registry import COMPONENT_REGISTRY

roof_generator = create_component_node(COMPONENT_REGISTRY["roof"])
