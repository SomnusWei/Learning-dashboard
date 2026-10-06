"""FastAPI 应用入口。

启动流程：
1. import 所有 models 让 SQLAlchemy 注册元数据
2. 启动时调用 init_database() 建表（幂等）
3. 注册 routers
4. CORS / 异常处理 / 健康检查
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
# 触发 model 注册
from app.models import *  # noqa: F401,F403
from app.routers import (
    auth,
    dashboard,
    formula_songs,
    knowledge_base,
    plans,
    search,
    settings as settings_router,
    study,
    subjects,
    todos,
    wrong_questions,
)
from app.services.init_db import init_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时建表（幂等）
    init_database()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="个人学习工作台 - 后端 API",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 健康检查（无需认证）
@app.get("/health", tags=["health"], summary="健康检查")
def health():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}


@app.get(f"{settings.API_PREFIX}/health", tags=["health"], summary="API 健康检查")
def api_health():
    return {"status": "ok"}


# 业务路由
api_prefix = settings.API_PREFIX
app.include_router(auth.router, prefix=api_prefix)
app.include_router(search.router, prefix=api_prefix)
app.include_router(dashboard.router, prefix=api_prefix)
app.include_router(wrong_questions.router, prefix=api_prefix)
app.include_router(subjects.router, prefix=api_prefix)
app.include_router(plans.router, prefix=api_prefix)
app.include_router(todos.router, prefix=api_prefix)
app.include_router(knowledge_base.router, prefix=api_prefix)
app.include_router(study.router, prefix=api_prefix)
app.include_router(formula_songs.router, prefix=api_prefix)
app.include_router(settings_router.router, prefix=api_prefix)
