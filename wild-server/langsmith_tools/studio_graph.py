"""给官方 Studio 导出项目原图；检查点由 Agent Server 管理。"""
from agent.utils.components import get_implemented_components
from agent.graph import build_generation_graph
from agent.graph import plan_recursion_limit
from agent.llm.resources import initialize_agent_resources


initialize_agent_resources()
graph = build_generation_graph().with_config({
    # 条目数在 plan 节点跑完前未知：按「构件类型数 × 3（generate/merge/validate）」估上界，
    # 与 application.generation.runner 的运行期口径保持一致。
    "recursion_limit": plan_recursion_limit(
        len(get_implemented_components()) * 3, 3
    ),
})
