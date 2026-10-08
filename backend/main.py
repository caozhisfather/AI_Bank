from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import analysis, health
from services.analysis_service import get_analysis_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_analysis_service()
    yield


app = FastAPI(
    title="碳跃智衡 API",
    description="高碳产业园区可信转型融资与动态风险管理算法服务",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(analysis.router, prefix="/api/v1")
