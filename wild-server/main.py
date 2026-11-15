"""WildAgent 服务入口，保持 main:app 启动方式。"""
from app.bootstrap.app_factory import create_app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", log_level="info", reload=True)
