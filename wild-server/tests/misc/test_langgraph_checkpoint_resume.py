import tempfile
import unittest
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph


class CounterState(TypedDict):
    value: int


class LangGraphCheckpointResumeTest(unittest.IsolatedAsyncioTestCase):
    async def test_resume_skips_completed_nodes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "graph.sqlite3"
            calls = {"first": 0, "second": 0}
            should_fail = True

            async def first_node(state: CounterState):
                calls["first"] += 1
                return {"value": state["value"] + 1}

            async def second_node(state: CounterState):
                nonlocal should_fail
                calls["second"] += 1
                if should_fail:
                    should_fail = False
                    raise RuntimeError("模拟服务中断")
                return {"value": state["value"] + 1}

            builder = StateGraph(CounterState)
            builder.add_node("first", first_node)
            builder.add_node("second", second_node)
            builder.add_edge(START, "first")
            builder.add_edge("first", "second")
            builder.add_edge("second", END)

            async with AsyncSqliteSaver.from_conn_string(str(database_path)) as saver:
                await saver.setup()
                graph = builder.compile(checkpointer=saver)
                config = {"configurable": {"thread_id": "restart-test"}}

                with self.assertRaisesRegex(RuntimeError, "模拟服务中断"):
                    await graph.ainvoke({"value": 0}, config)

                snapshot = await graph.aget_state(config)
                self.assertEqual(snapshot.next, ("second",))

                result = await graph.ainvoke(None, config)

            self.assertEqual(result["value"], 2)
            self.assertEqual(calls, {"first": 1, "second": 2})


if __name__ == "__main__":
    unittest.main()
