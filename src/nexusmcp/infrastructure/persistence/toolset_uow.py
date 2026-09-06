"""跨 Toolsets/Catalog 同一 AsyncSession 的 SQLAlchemy UoW。"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.infrastructure.persistence.toolset_catalog_reader import (
    SqlAlchemyToolsetCatalogReader,
)
from nexusmcp.modules.toolsets.adapters.sqlalchemy_repository import (
    SqlAlchemyToolsetRepository,
)


class SqlAlchemyToolsetUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._toolsets: SqlAlchemyToolsetRepository | None = None
        self._catalog: SqlAlchemyToolsetCatalogReader | None = None

    @property
    def toolsets(self) -> SqlAlchemyToolsetRepository:
        if self._toolsets is None:
            raise RuntimeError("unit of work must be entered before accessing repositories")
        return self._toolsets

    @property
    def catalog(self) -> SqlAlchemyToolsetCatalogReader:
        if self._catalog is None:
            raise RuntimeError("unit of work must be entered before accessing catalog reader")
        return self._catalog

    async def __aenter__(self) -> SqlAlchemyToolsetUnitOfWork:
        if self._session is not None:
            raise RuntimeError("unit of work does not support nested entry")
        self._session = self._session_factory()
        self._toolsets = SqlAlchemyToolsetRepository(self._session)
        self._catalog = SqlAlchemyToolsetCatalogReader(self._session)
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
            self._toolsets = None
            self._catalog = None

    async def commit(self) -> None:
        await self._require_session().commit()

    async def rollback(self) -> None:
        await self._require_session().rollback()

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("unit of work must be entered before transaction control")
        return self._session


class SqlAlchemyToolsetUnitOfWorkFactory:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> SqlAlchemyToolsetUnitOfWork:
        return SqlAlchemyToolsetUnitOfWork(self._session_factory)
