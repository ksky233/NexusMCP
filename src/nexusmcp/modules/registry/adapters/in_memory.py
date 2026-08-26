"""供 Publish 测试使用的确定性内存 Upstream Adapter。"""

from __future__ import annotations

from collections.abc import Iterable

from nexusmcp.modules.registry.domain import UpstreamService


class InMemoryUpstreamRepository:
    def __init__(self, upstreams: Iterable[UpstreamService] = ()) -> None:
        self._upstreams = {upstream.id: upstream for upstream in upstreams}

    async def add(self, tenant_id: str, upstream: UpstreamService) -> None:
        _require_matching_tenant(tenant_id, upstream.tenant_id)
        if upstream.id in self._upstreams:
            raise ValueError("upstream service id already exists")
        if await self.get_by_name(tenant_id, upstream.namespace, upstream.name) is not None:
            raise ValueError("upstream service name already exists in namespace")
        self._upstreams[upstream.id] = upstream

    async def save(self, tenant_id: str, upstream: UpstreamService) -> None:
        _require_matching_tenant(tenant_id, upstream.tenant_id)
        current = self._upstreams.get(upstream.id)
        if current is None or current.tenant_id != tenant_id:
            raise ValueError("upstream service does not exist in tenant")
        self._upstreams[upstream.id] = upstream

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

    async def get_by_name(
        self,
        tenant_id: str,
        namespace: str,
        name: str,
    ) -> UpstreamService | None:
        return next(
            (
                upstream
                for upstream in self._upstreams.values()
                if upstream.tenant_id == tenant_id
                and upstream.namespace == namespace
                and upstream.name == name
            ),
            None,
        )

    async def list_by_tenant(self, tenant_id: str) -> tuple[UpstreamService, ...]:
        upstreams = (
            upstream for upstream in self._upstreams.values() if upstream.tenant_id == tenant_id
        )
        return tuple(sorted(upstreams, key=lambda upstream: (upstream.namespace, upstream.name)))

    def clone(self) -> InMemoryUpstreamRepository:
        return InMemoryUpstreamRepository(self._upstreams.values())

    def replace_with(self, repository: InMemoryUpstreamRepository) -> None:
        self._upstreams = dict(repository._upstreams)


def _require_matching_tenant(requested_tenant_id: str, entity_tenant_id: str) -> None:
    if requested_tenant_id != entity_tenant_id:
        raise ValueError("entity tenant does not match repository tenant scope")
