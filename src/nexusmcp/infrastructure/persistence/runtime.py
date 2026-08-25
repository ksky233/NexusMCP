"""PostgreSQL Engine/Session Factory 的进程 Lifespan 所有者。"""

import asyncio
import logging
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from nexusmcp.infrastructure.persistence.engine import create_engine, create_session_factory

logger = logging.getLogger(__name__)


class DatabaseRuntimePort(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def is_ready(self) -> bool: ...

    def require_session_factory(self) -> async_sessionmaker[AsyncSession]: ...


class DatabaseRuntime:
    """延迟创建 Engine，并确保启动失败或 Shutdown 时释放连接池。"""

    def __init__(
        self,
        database_url: str,
        *,
        echo: bool = False,
        readiness_timeout_seconds: float = 1.0,
    ) -> None:
        if readiness_timeout_seconds <= 0:
            raise ValueError("database readiness timeout must be positive")
        self._database_url = database_url
        self._echo = echo
        self._readiness_timeout_seconds = readiness_timeout_seconds
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    @property
    def is_started(self) -> bool:
        return self._engine is not None

    async def start(self) -> None:
        if self._engine is not None:
            raise RuntimeError("database runtime is already started")
        engine = create_engine(self._database_url, echo=self._echo)
        self._engine = engine
        self._session_factory = create_session_factory(engine)
        try:
            await self._ping()
        except Exception:
            await engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.exception(
                "database_start_failed",
                extra={"event": "database_start_failed", "error_code": "database_unavailable"},
            )
            raise
        logger.info("database_started", extra={"event": "database_started"})

    async def stop(self) -> None:
        engine = self._engine
        self._engine = None
        self._session_factory = None
        if engine is not None:
            await engine.dispose()
            logger.info("database_stopped", extra={"event": "database_stopped"})

    async def is_ready(self) -> bool:
        if self._engine is None:
            return False
        try:
            await self._ping()
        except Exception:
            logger.warning(
                "database_readiness_failed",
                extra={
                    "event": "database_readiness_failed",
                    "error_code": "database_unavailable",
                },
            )
            return False
        return True

    def require_session_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._session_factory is None:
            raise RuntimeError("database runtime is not started")
        return self._session_factory

    async def _ping(self) -> None:
        engine = self._engine
        if engine is None:
            raise RuntimeError("database runtime is not started")
        async with asyncio.timeout(self._readiness_timeout_seconds):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
