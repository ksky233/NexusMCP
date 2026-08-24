"""Tool Catalog 上下文拥有的出站 Port。"""

from collections.abc import Sequence
from typing import Protocol

from nexusmcp.modules.catalog.domain import ToolDefinition


class ToolRepository(Protocol):
    async def list_by_tenant(self, tenant_id: str) -> Sequence[ToolDefinition]: ...

    async def get_published_by_name(
        self,
        tenant_id: str,
        canonical_name: str,
    ) -> ToolDefinition | None: ...
