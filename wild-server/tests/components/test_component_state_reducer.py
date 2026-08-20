"""验证并行组件节点可安全写入通用 State 映射。"""

import unittest

from langgraph.graph import END, START, StateGraph

from app.agent.graph_state import GenerationState


async def _door_branch(_state: GenerationState) -> dict:
    return {
        "component_fragments": {"door": [{"id": "door_1"}]},
        "component_diagnostics": {"door_gen_diag": {"fragment_count": 1}},
    }


async def _window_branch(_state: GenerationState) -> dict:
    return {
        "component_fragments": {"window": [{"id": "window_1"}]},
        "component_diagnostics": {"window_gen_diag": {"fragment_count": 1}},
    }


class ComponentStateReducerTest(unittest.IsolatedAsyncioTestCase):
    async def test_parallel_updates_are_merged_without_field_whitelists(self) -> None:
        builder = StateGraph(GenerationState)
        builder.add_node("door", _door_branch)
        builder.add_node("window", _window_branch)
        builder.add_edge(START, "door")
        builder.add_edge(START, "window")
        builder.add_edge("door", END)
        builder.add_edge("window", END)

        result = await builder.compile().ainvoke({"user_message": "parallel"})

        self.assertEqual(result["component_fragments"]["door"][0]["id"], "door_1")
        self.assertEqual(result["component_fragments"]["window"][0]["id"], "window_1")
        self.assertEqual(set(result["component_diagnostics"]), {
            "door_gen_diag",
            "window_gen_diag",
        })


if __name__ == "__main__":
    unittest.main()
