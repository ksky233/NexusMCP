"""ToolSearchUnitOfWork 的 SQLAlchemy Async Adapter。"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.modules.tool_search.adapters.sqlalchemy_repository import (
    SqlAlchemyToolSearchEmbeddingRepository,
)


class SqlAlchemyToolSearchUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._embeddings: SqlAlchemyToolSearchEmbeddingRepository | None = None

    @property
    def embeddings(self) -> SqlAlchemyToolSearchEmbeddingRepository:
        if self._embeddings is None:
            raise RuntimeError("unit of work must be entered before accessing repository")
        return self._embeddings

    async def __aenter__(self) -> SqlAlchemyToolSearchUnitOfWork:
        if self._session is not None:
            raise RuntimeError("unit of work does not support nested entry")
        self._session = self._session_factory()
        self._embeddings = SqlAlchemyToolSearchEmbeddingRepository(self._session)
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
            self._embeddings = None

    async def commit(self) -> None:
        await self._require_session().commit()

    async def rollback(self) -> None:
        await self._require_session().rollback()

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("unit of work must be entered before transaction control")
        return self._session


class SqlAlchemyToolSearchUnitOfWorkFactory:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> SqlAlchemyToolSearchUnitOfWork:
        return SqlAlchemyToolSearchUnitOfWork(self._session_factory)
