"""供 Publish 测试使用的确定性内存 Upstream Adapter。"""

from __future__ import annotations

from collections.abc import Iterable

from nexusmcp.modules.registry.domain import UpstreamService


class InMemoryUpstreamRepository:
    def __init__(self, upstreams: Iterable[UpstreamService] = ()) -> None:
        self._upstreams = {upstream.id: upstream for upstream in upstreams}

    async def get_by_id(
        self,
        tenant_id: str,
        upstream_service_id: str,
    ) -> UpstreamService | None:
        upstream = self._upstreams.get(upstream_service_id)
        return upstream if upstream is not None and upstream.tenant_id == tenant_id else None

    async def get_for_update(
        self,
        tenant_id: str,
        upstream_service_id: str,
    ) -> UpstreamService | None:
        # 内存执行无行锁；方法表达 Publish 与 Disable 不能并发穿透的业务意图。
        return await self.get_by_id(tenant_id, upstream_service_id)

    def clone(self) -> InMemoryUpstreamRepository:
        return InMemoryUpstreamRepository(self._upstreams.values())

    def replace_with(self, repository: InMemoryUpstreamRepository) -> None:
        self._upstreams = dict(repository._upstreams)
