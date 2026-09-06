"""Toolset Port 的确定性 InMemory Adapter。"""

from __future__ import annotations

from collections.abc import Iterable

from nexusmcp.modules.toolsets.domain import Toolset, ToolsetKind, ToolsetStatus
from nexusmcp.modules.toolsets.ports import ToolsetCatalogSnapshot


class InMemoryToolsetRepository:
    def __init__(self, toolsets: Iterable[Toolset] = ()) -> None:
        seed = tuple(toolsets)
        if len(seed) != len({toolset.id for toolset in seed}):
            raise ValueError("toolset id already exists")
        self._toolsets = {toolset.id: toolset for toolset in seed}
        self._validate_seed_uniqueness()

    async def add(self, tenant_id: str, toolset: Toolset) -> None:
        _require_matching_tenant(tenant_id, toolset.tenant_id)
        if toolset.id in self._toolsets:
            raise ValueError("toolset id already exists")
        if await self.get_by_slug(tenant_id, toolset.slug) is not None:
            raise ValueError("toolset slug already exists in tenant")
        if (
            toolset.kind is ToolsetKind.ALL_PUBLISHED
            and await self.get_all_published(tenant_id) is not None
        ):
            raise ValueError("all_published toolset already exists in tenant")
        self._toolsets[toolset.id] = toolset

    async def save(self, tenant_id: str, toolset: Toolset) -> None:
        _require_matching_tenant(tenant_id, toolset.tenant_id)
        current = self._toolsets.get(toolset.id)
        if current is None or current.tenant_id != tenant_id:
            raise ValueError("toolset does not exist in tenant")
        if (
            current.slug != toolset.slug
            or current.kind is not toolset.kind
            or current.created_by != toolset.created_by
            or current.created_at != toolset.created_at
        ):
            raise ValueError("toolset stable identity fields are immutable")
        slug_owner = await self.get_by_slug(tenant_id, toolset.slug)
        if slug_owner is not None and slug_owner.id != toolset.id:
            raise ValueError("toolset slug already exists in tenant")
        all_published = await self.get_all_published(tenant_id)
        if (
            toolset.kind is ToolsetKind.ALL_PUBLISHED
            and all_published is not None
            and all_published.id != toolset.id
        ):
            raise ValueError("all_published toolset already exists in tenant")
        self._toolsets[toolset.id] = toolset

    async def get_by_id(self, tenant_id: str, toolset_id: str) -> Toolset | None:
        toolset = self._toolsets.get(toolset_id)
        return toolset if toolset is not None and toolset.tenant_id == tenant_id else None

    async def get_for_update(self, tenant_id: str, toolset_id: str) -> Toolset | None:
        # InMemory 测试单线程执行；该方法保留 PostgreSQL SELECT FOR UPDATE 的业务意图。
        return await self.get_by_id(tenant_id, toolset_id)

    async def get_by_slug(self, tenant_id: str, slug: str) -> Toolset | None:
        return next(
            (
                toolset
                for toolset in self._toolsets.values()
                if toolset.tenant_id == tenant_id and toolset.slug == slug
            ),
            None,
        )

    async def get_all_published(self, tenant_id: str) -> Toolset | None:
        return next(
            (
                toolset
                for toolset in self._toolsets.values()
                if toolset.tenant_id == tenant_id and toolset.kind is ToolsetKind.ALL_PUBLISHED
            ),
            None,
        )

    async def list_by_tenant(self, tenant_id: str) -> tuple[Toolset, ...]:
        return tuple(
            sorted(
                (toolset for toolset in self._toolsets.values() if toolset.tenant_id == tenant_id),
                key=lambda toolset: toolset.slug,
            )
        )

    async def list_granted_active(
        self,
        tenant_id: str,
        principal_id: str,
    ) -> tuple[Toolset, ...]:
        return tuple(
            toolset
            for toolset in await self.list_by_tenant(tenant_id)
            if toolset.status is ToolsetStatus.ACTIVE and principal_id in toolset.principal_ids
        )

    def clone(self) -> InMemoryToolsetRepository:
        return InMemoryToolsetRepository(self._toolsets.values())

    def replace_with(self, repository: InMemoryToolsetRepository) -> None:
        self._toolsets = dict(repository._toolsets)

    def _validate_seed_uniqueness(self) -> None:
        identities = [toolset.id for toolset in self._toolsets.values()]
        slugs = [(toolset.tenant_id, toolset.slug) for toolset in self._toolsets.values()]
        system_tenants = [
            toolset.tenant_id
            for toolset in self._toolsets.values()
            if toolset.kind is ToolsetKind.ALL_PUBLISHED
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("toolset id already exists")
        if len(slugs) != len(set(slugs)):
            raise ValueError("toolset slug already exists in tenant")
        if len(system_tenants) != len(set(system_tenants)):
            raise ValueError("all_published toolset already exists in tenant")


class InMemoryToolsetCatalogReader:
    def __init__(self, snapshots: Iterable[ToolsetCatalogSnapshot] = ()) -> None:
        seed = tuple(snapshots)
        keys = [(snapshot.tenant_id, snapshot.tool_id) for snapshot in seed]
        if len(keys) != len(set(keys)):
            raise ValueError("catalog snapshot tool id already exists in tenant")
        self._snapshots = {(snapshot.tenant_id, snapshot.tool_id): snapshot for snapshot in seed}

    async def list_member_snapshots(
        self,
        tenant_id: str,
        tool_ids: tuple[str, ...],
    ) -> tuple[ToolsetCatalogSnapshot, ...]:
        return tuple(
            snapshot
            for tool_id in tool_ids
            if (snapshot := self._snapshots.get((tenant_id, tool_id))) is not None
        )


def _require_matching_tenant(requested_tenant_id: str, entity_tenant_id: str) -> None:
    if requested_tenant_id != entity_tenant_id:
        raise ValueError("entity tenant does not match repository tenant scope")
