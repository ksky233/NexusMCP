"""Approval Repository 与事务 Port。"""

from types import TracebackType
from typing import Protocol, Self

from nexusmcp.modules.approval.domain import ApprovalRequest


class ApprovalRepository(Protocol):
    async def add(self, tenant_id: str, approval: ApprovalRequest) -> None: ...

    async def get_for_update(
        self,
        tenant_id: str,
        approval_id: str,
    ) -> ApprovalRequest | None: ...

    async def get_by_id(
        self,
        tenant_id: str,
        approval_id: str,
    ) -> ApprovalRequest | None: ...

    async def save(self, tenant_id: str, approval: ApprovalRequest) -> None: ...


class ApprovalUnitOfWork(Protocol):
    @property
    def approvals(self) -> ApprovalRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class ApprovalUnitOfWorkFactory(Protocol):
    def __call__(self) -> ApprovalUnitOfWork: ...
