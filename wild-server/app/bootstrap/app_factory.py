"""FastAPI 应用装配；业务模块不导入此模块。"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.exception_handlers import install_exception_handlers
from app.api.middleware import enforce_write_access
from app.api.http import admin, assets, auth, blueprints, item_catalog, sessions
from app.bootstrap.lifespan import lifespan as editor_lifespan


def create_app(*, lifespan=editor_lifespan) -> FastAPI:
    app = FastAPI(version="1.0", lifespan=lifespan)
    install_exception_handlers(app)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    app.middleware("http")(enforce_write_access)
    for router in (admin.router, auth.router, blueprints.router, sessions.router,
                   assets.router, item_catalog.router):
        app.include_router(router)
    return app
