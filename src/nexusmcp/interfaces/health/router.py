"""进程 Liveness 与依赖 Readiness Endpoint。"""

from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

type ReadinessProbe = Callable[[], Awaitable[bool]]


class HealthResponse(BaseModel):
    status: Literal["ok", "not_ready"]


def create_health_router(readiness_probe: ReadinessProbe) -> APIRouter:
    router = APIRouter(prefix="/health", tags=["health"])

    @router.get("", response_model=HealthResponse)
    @router.get("/live", response_model=HealthResponse)
    async def liveness() -> HealthResponse:
        """只证明进程和事件循环能处理请求，不探测外部依赖。"""

        return HealthResponse(status="ok")

    @router.get("/ready", response_model=HealthResponse)
    async def readiness(response: Response) -> HealthResponse:
        """依赖尚未启动或 PostgreSQL 不可用时返回 503。"""

        if not await readiness_probe():
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return HealthResponse(status="not_ready")
        return HealthResponse(status="ok")

    return router
