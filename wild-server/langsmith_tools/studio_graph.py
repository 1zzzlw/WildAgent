"""给官方 Studio 导出项目原图；检查点由 Agent Server 管理。"""
from app.agent.generation.components import get_implemented_components
from app.agent.graph import build_generation_graph, plan_recursion_limit


graph = build_generation_graph(enable_callback=True).with_config({
    # 条目数在 plan 节点跑完前未知：按「构件类型数 × 3（generate/merge/validate）」估上界，
    # 与 ws_agent 的运行期口径保持一致（《动态节点设计规划》§6.4）。
    "recursion_limit": plan_recursion_limit(
        len(get_implemented_components()) * 3, 3
    ),
})
