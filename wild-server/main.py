"""WildAgent 服务入口，统一在 8000 提供编辑器与 Agent。"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from agent.llm.resources import initialize_agent_resources
from agent.runtime import agent_runtime
from app.bootstrap.app_factory import create_app
from app.bootstrap.lifespan import lifespan as editor_lifespan
from app.infrastructure.storage.assets import asset_storage
from integration.ai_edits import is_verified_ai_edit
from integration.api import designs, health, model_config, observability, websocket
from integration.generation.jobs import generation_job_service
from integration.generation.runner import run_generation


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with editor_lifespan(app):
        agent_runtime.list_asset_manifests = asset_storage.list_manifests
        await asyncio.to_thread(initialize_agent_resources)
        try:
            await generation_job_service.startup(run_generation)
            yield
        finally:
            await generation_job_service.shutdown()


app = create_app(lifespan=lifespan)
app.state.stop_account_jobs = generation_job_service.stop_account_jobs
app.state.delete_session_jobs = generation_job_service.delete_session_jobs
app.state.verify_ai_edit = is_verified_ai_edit

for router in (websocket.router, designs.router, model_config.router, observability.router, health.router):
    app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", port=8000, log_level="info", reload=True)
