"""LangGraph durable boundary for a bounded design revision batch."""
from langgraph.func import task

from app.agent.runtime import get_reasoning_callback
from .design_workflow import draft_design_blocks


@task
async def draft_revision_task(payload: dict) -> dict:
    # Persist ordinary failures too: replay should not spend the batch budget again.
    accounting = {"model_calls": 0}
    try:
        patch, diagnostics = await draft_design_blocks(
            **payload, on_reasoning_delta=get_reasoning_callback(), call_accounting=accounting,
        )
        return {"patch": patch, "diagnostics": diagnostics}
    except Exception as exc:
        return {"error": str(exc), "model_calls": accounting["model_calls"]}
