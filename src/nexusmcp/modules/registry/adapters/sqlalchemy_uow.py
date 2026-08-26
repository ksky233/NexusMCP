"""Registry 写用例的 SQLAlchemy Async Unit of Work。"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.modules.registry.adapters.sqlalchemy_repository import (
    SqlAlchemyUpstreamRepository,
)


class SqlAlchemyRegistryUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._upstreams: SqlAlchemyUpstreamRepository | None = None

    @property
    def upstreams(self) -> SqlAlchemyUpstreamRepository:
        if self._upstreams is None:
            raise RuntimeError("unit of work must be entered before accessing repositories")
        return self._upstreams

    async def __aenter__(self) -> SqlAlchemyRegistryUnitOfWork:
        if self._session is not None:
            raise RuntimeError("unit of work does not support nested entry")
        self._session = self._session_factory()
        self._upstreams = SqlAlchemyUpstreamRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            if session.in_transaction():
                await session.rollback()
        finally:
            await session.close()
            self._session = None
            self._upstreams = None

    async def commit(self) -> None:
        await self._require_session().commit()

    async def rollback(self) -> None:
        await self._require_session().rollback()

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("unit of work must be entered before transaction control")
        return self._session


class SqlAlchemyRegistryUnitOfWorkFactory:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> SqlAlchemyRegistryUnitOfWork:
        return SqlAlchemyRegistryUnitOfWork(self._session_factory)
