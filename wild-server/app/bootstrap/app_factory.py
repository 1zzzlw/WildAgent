"""FastAPI 应用装配；业务模块不导入此模块。"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.exception_handlers import install_exception_handlers
from app.api.middleware import enforce_write_access
from app.api.http import auth, assets, blueprints, designs, health, item_catalog, model_config, observability, sessions
from app.api.websocket.agent import router as websocket_router
from app.bootstrap.lifespan import lifespan


def create_app() -> FastAPI:
    app = FastAPI(version="1.0", lifespan=lifespan)
    install_exception_handlers(app)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    app.middleware("http")(enforce_write_access)
    for router in (auth.router, websocket_router, blueprints.router, sessions.router,
                   assets.router, model_config.router, observability.router,
                   designs.router, item_catalog.router, health.router):
        app.include_router(router)
    return app
