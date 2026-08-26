"""Execution、Approval 与 Audit 共享短事务的 SQLAlchemy UoW。"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.modules.approval.adapters.sqlalchemy_repository import (
    SqlAlchemyApprovalRepository,
)
from nexusmcp.modules.audit.adapters.sqlalchemy_repository import SqlAlchemyAuditRepository
from nexusmcp.modules.execution.adapters.sqlalchemy_repository import (
    SqlAlchemyExecutionAttemptRepository,
    SqlAlchemyToolExecutionRepository,
)


class SqlAlchemyExecutionUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._executions: SqlAlchemyToolExecutionRepository | None = None
        self._attempts: SqlAlchemyExecutionAttemptRepository | None = None
        self._approvals: SqlAlchemyApprovalRepository | None = None
        self._audits: SqlAlchemyAuditRepository | None = None

    @property
    def executions(self) -> SqlAlchemyToolExecutionRepository:
        if self._executions is None:
            raise RuntimeError("unit of work must be entered before accessing repositories")
        return self._executions

    @property
    def approvals(self) -> SqlAlchemyApprovalRepository:
        if self._approvals is None:
            raise RuntimeError("unit of work must be entered before accessing repositories")
        return self._approvals

    @property
    def attempts(self) -> SqlAlchemyExecutionAttemptRepository:
        if self._attempts is None:
            raise RuntimeError("unit of work must be entered before accessing repositories")
        return self._attempts

    @property
    def audits(self) -> SqlAlchemyAuditRepository:
        if self._audits is None:
            raise RuntimeError("unit of work must be entered before accessing repositories")
        return self._audits

    async def __aenter__(self) -> SqlAlchemyExecutionUnitOfWork:
        if self._session is not None:
            raise RuntimeError("unit of work does not support nested entry")
        self._session = self._session_factory()
        self._executions = SqlAlchemyToolExecutionRepository(self._session)
        self._attempts = SqlAlchemyExecutionAttemptRepository(self._session)
        self._approvals = SqlAlchemyApprovalRepository(self._session)
        self._audits = SqlAlchemyAuditRepository(self._session)
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
            self._executions = None
            self._attempts = None
            self._approvals = None
            self._audits = None

    async def commit(self) -> None:
        await self._require_session().commit()

    async def rollback(self) -> None:
        await self._require_session().rollback()

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("unit of work must be entered before transaction control")
        return self._session


class SqlAlchemyExecutionUnitOfWorkFactory:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> SqlAlchemyExecutionUnitOfWork:
        return SqlAlchemyExecutionUnitOfWork(self._session_factory)
