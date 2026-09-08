"""给官方 Studio 导出项目原图；检查点由 Agent Server 管理。"""
from app.agent.component_registry import get_implemented_components
from app.agent.graph import build_generation_graph, generation_recursion_limit


graph = build_generation_graph(enable_callback=True).with_config({
    # 覆盖普通模式和 Plan 模式的默认预算；与示例的 max_retries=3 对齐。
    "recursion_limit": generation_recursion_limit(
        len(get_implemented_components()), 3, plan_mode=True
    ),
})
