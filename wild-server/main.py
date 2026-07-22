from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# 生命周期管理工具
from contextlib import asynccontextmanager
from loguru import logger
from app.api.ws_agent import router as ws_router
from app.api.scenes import router as scenes_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 打印重要信息日志到控制台中
    print_log()
    
    # 启动服务时自动连接所需要的服务
    init_connect()
    
    yield

    # 关闭服务时自动断开连接中的服务  
    close_connect()

def print_log():
    logger.info("服务启动")

def init_connect():
    logger.info("建立连接成功")

def close_connect():
    logger.info("断开服务")

app = FastAPI(
    # FastAPI 的生命周期钩子，用来接管项目启动、关闭前后的逻辑
    lifespan=lifespan
)

# CORS: 允许前端（Vite dev server）跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(ws_router, tags=["ws连接初始化"])
app.include_router(scenes_router, tags=["场景API"])

@app.get("/")
async def root():
    return {"Hello": "World"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        log_level="info",
        reload=True
    )
