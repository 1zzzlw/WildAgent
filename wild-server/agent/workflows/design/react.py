"""图纸起草和修订共用的按需检索循环。"""

from collections.abc import Awaitable, Callable
from typing import Any, NotRequired

from langchain_core.messages import ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from agent.prompts.design_revision import DESIGN_KNOWLEDGE_INSTRUCTION
from agent.runtime import ReasoningCallback
from agent.tools.knowledge import search_design_knowledge
from agent.workflows.design.drafting import _request_draft
from agent.llm.invocation import LlmResult, merge_token_usage


_MAX_SEARCHES = 2


class _DesignState(MessagesState):
    thinking_mode: bool
    reply: NotRequired[LlmResult]


def build_design_request(
    accounting: dict[str, int],
    knowledge_trace: list[dict[str, Any]],
    callback: ReasoningCallback | None,
) -> Callable[..., Awaitable[LlmResult]]:
    """为一张图纸建立子图，起草和后续修订共享同一检索额度。"""

    async def search_with_budget(request, execute):
        call = request.tool_call
        if len(knowledge_trace) >= _MAX_SEARCHES:
            return ToolMessage(
                content="本次图纸的检索额度已用完，请基于已有上下文提交结果。",
                tool_call_id=call["id"],
                name=call["name"],
                status="error",
            )
        # ToolNode 可并发执行同一轮的工具，先占用额度再发起检索。
        query = call["args"].get("query")
        entry = {
            "query": query[:500] if isinstance(query, str) else "",
            "status": "error",
        }
        knowledge_trace.append(entry)
        result = await execute(request)
        if isinstance(result, ToolMessage) and isinstance(result.artifact, dict):
            entry.update(result.artifact)
            if entry["status"] == "matched":
                entry["chars"] = len(result.content)
        return result

    async def model(state: _DesignState) -> dict:
        previous = state.get("reply")
        if previous is not None:
            accounting["model_calls"] += 1
        tools = [search_design_knowledge] if len(knowledge_trace) < _MAX_SEARCHES else []
        reply = await _request_draft(
            state["messages"],
            thinking_mode=state["thinking_mode"],
            on_reasoning_delta=callback,
            tools=tools,
        )
        if previous is not None:
            reply.token_usage = merge_token_usage(previous.token_usage, reply.token_usage)
        message = reply.message
        if message is None:
            return {"reply": reply}
        if message.invalid_tool_calls or (message.tool_calls and not tools):
            # 不把无效工具调用误当成已提交的图纸。
            reply.content = ""
            reply.message = None
            return {"reply": reply}
        return {"reply": reply, "messages": [message]}

    def route(state: _DesignState) -> str:
        reply = state["reply"]
        if reply.message is None or reply.finish_reason in ("length", "max_tokens"):
            return END
        return tools_condition(state)

    builder = StateGraph(_DesignState)
    builder.add_node("model", model)
    builder.add_node(
        "search",
        ToolNode([search_design_knowledge], awrap_tool_call=search_with_budget),
    )
    builder.add_edge(START, "model")
    builder.add_conditional_edges("model", route, {"tools": "search", END: END})
    builder.add_edge("search", "model")
    graph = builder.compile(checkpointer=False)

    async def request_draft(messages, *, thinking_mode):
        if len(knowledge_trace) < _MAX_SEARCHES:
            system, *remaining = messages
            content = system["content"] + "\n\n" + DESIGN_KNOWLEDGE_INSTRUCTION
            messages = [
                {**system, "content": content},
                *remaining,
            ]
        result = await graph.ainvoke(
            {"messages": messages, "thinking_mode": thinking_mode},
            config={"recursion_limit": 2 * _MAX_SEARCHES + 2},
        )
        return result["reply"]

    return request_draft
