"""Registry 上下文拥有的持久化 Port。"""

from typing import Protocol

from nexusmcp.modules.registry.domain import UpstreamService


class UpstreamRepository(Protocol):
    async def get_by_id(
        self,
        tenant_id: str,
        upstream_service_id: str,
    ) -> UpstreamService | None: ...

    async def get_for_update(
        self,
        tenant_id: str,
        upstream_service_id: str,
    ) -> UpstreamService | None: ...
