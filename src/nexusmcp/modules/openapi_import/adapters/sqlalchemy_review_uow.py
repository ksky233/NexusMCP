"""ImportedOperation Review 的 SQLAlchemy Async Unit of Work。"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.modules.catalog.adapters.sqlalchemy_repository import (
    SqlAlchemyToolCatalogRepository,
)
from nexusmcp.modules.connectors.adapters.sqlalchemy_repository import (
    SqlAlchemyToolBindingRepository,
)
from nexusmcp.modules.openapi_import.adapters.sqlalchemy_repository import (
    SqlAlchemyOpenApiImportRepository,
)
from nexusmcp.modules.registry.adapters.sqlalchemy_repository import (
    SqlAlchemyUpstreamRepository,
)


class SqlAlchemyReviewUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._imports: SqlAlchemyOpenApiImportRepository | None = None
        self._catalog: SqlAlchemyToolCatalogRepository | None = None
        self._bindings: SqlAlchemyToolBindingRepository | None = None
        self._upstreams: SqlAlchemyUpstreamRepository | None = None

    @property
    def imports(self) -> SqlAlchemyOpenApiImportRepository:
        return self._require(self._imports)

    @property
    def catalog(self) -> SqlAlchemyToolCatalogRepository:
        return self._require(self._catalog)

    @property
    def bindings(self) -> SqlAlchemyToolBindingRepository:
        return self._require(self._bindings)

    @property
    def upstreams(self) -> SqlAlchemyUpstreamRepository:
        return self._require(self._upstreams)

    async def __aenter__(self) -> SqlAlchemyReviewUnitOfWork:
        if self._session is not None:
            raise RuntimeError("unit of work does not support nested entry")
        self._session = self._session_factory()
        self._imports = SqlAlchemyOpenApiImportRepository(self._session)
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
        session = self._require(self._session)
        try:
            if session.in_transaction():
                await session.rollback()
        finally:
            await session.close()
            self._session = None
            self._imports = None
            self._catalog = None
            self._bindings = None
            self._upstreams = None

    async def commit(self) -> None:
        await self._require(self._session).commit()

    async def rollback(self) -> None:
        await self._require(self._session).rollback()

    @staticmethod
    def _require[T](value: T | None) -> T:
        if value is None:
            raise RuntimeError("unit of work must be entered before accessing transaction state")
        return value


class SqlAlchemyReviewUnitOfWorkFactory:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> SqlAlchemyReviewUnitOfWork:
        return SqlAlchemyReviewUnitOfWork(self._session_factory)
