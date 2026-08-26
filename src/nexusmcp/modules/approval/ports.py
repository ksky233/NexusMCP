"""Approval 持久化 Port。"""

from typing import Protocol

from nexusmcp.modules.approval.domain import ApprovalRequest


class ApprovalRepository(Protocol):
    async def add(self, tenant_id: str, approval: ApprovalRequest) -> None: ...

    async def get_for_update(
        self,
        tenant_id: str,
        approval_id: str,
    ) -> ApprovalRequest | None: ...

    async def save(self, tenant_id: str, approval: ApprovalRequest) -> None: ...
