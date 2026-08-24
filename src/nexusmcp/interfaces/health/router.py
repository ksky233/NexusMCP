"""进程健康检查 Endpoint。"""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


@router.get("", response_model=HealthResponse)
@router.get("/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    """报告进程和事件循环能够处理请求。"""

    return HealthResponse()


@router.get("/ready", response_model=HealthResponse)
async def readiness() -> HealthResponse:
    """初始就绪检查；真实 Adapter 出现后再增加依赖探针。"""

    return HealthResponse()
