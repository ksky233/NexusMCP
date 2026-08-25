"""CatalogUnitOfWork 的 SQLAlchemy Async Adapter。"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.modules.catalog.adapters.sqlalchemy_repository import (
    SqlAlchemyToolCatalogRepository,
)
from nexusmcp.modules.connectors.adapters.sqlalchemy_repository import (
    SqlAlchemyToolBindingRepository,
)
from nexusmcp.modules.registry.adapters.sqlalchemy_repository import (
    SqlAlchemyUpstreamRepository,
)


class SqlAlchemyCatalogUnitOfWork:
    """每次进入时创建独立 AsyncSession，并让两个 Repository 共享事务。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._catalog: SqlAlchemyToolCatalogRepository | None = None
        self._bindings: SqlAlchemyToolBindingRepository | None = None
        self._upstreams: SqlAlchemyUpstreamRepository | None = None

    @property
    def catalog(self) -> SqlAlchemyToolCatalogRepository:
        if self._catalog is None:
            raise RuntimeError("unit of work must be entered before accessing repositories")
        return self._catalog

    @property
    def bindings(self) -> SqlAlchemyToolBindingRepository:
        if self._bindings is None:
            raise RuntimeError("unit of work must be entered before accessing repositories")
        return self._bindings

    @property
    def upstreams(self) -> SqlAlchemyUpstreamRepository:
        if self._upstreams is None:
            raise RuntimeError("unit of work must be entered before accessing repositories")
        return self._upstreams

    async def __aenter__(self) -> SqlAlchemyCatalogUnitOfWork:
        if self._session is not None:
            raise RuntimeError("unit of work does not support nested entry")
        self._session = self._session_factory()
        self._catalog = SqlAlchemyToolCatalogRepository(self._session)
        self._bindings = SqlAlchemyToolBindingRepository(self._session)
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
            self._catalog = None
            self._bindings = None
            self._upstreams = None

    async def commit(self) -> None:
        await self._require_session().commit()

    async def rollback(self) -> None:
        await self._require_session().rollback()

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("unit of work must be entered before transaction control")
        return self._session


class SqlAlchemyCatalogUnitOfWorkFactory:
    """为每次并发 Command 创建互不共享 Session 的 Unit of Work。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> SqlAlchemyCatalogUnitOfWork:
        return SqlAlchemyCatalogUnitOfWork(self._session_factory)
