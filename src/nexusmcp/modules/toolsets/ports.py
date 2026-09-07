"""Toolset Aggregate 与同事务 Catalog Snapshot 的 Port。"""

from dataclasses import dataclass
from types import TracebackType
from typing import Protocol, Self

from nexusmcp.modules.toolsets.domain import Toolset, ToolsetMemberAvailability


@dataclass(frozen=True, slots=True)
class ToolsetCatalogSnapshot:
    tool_id: str
    tenant_id: str
    availability: ToolsetMemberAvailability
    published_tool_version_id: str | None
    canonical_name: str | None = None
    description: str | None = None
    serialized_schema_size: int = 0

    def __post_init__(self) -> None:
        if not self.tool_id.strip() or not self.tenant_id.strip():
            raise ValueError("catalog snapshot ids must not be blank")
        if (
            self.availability is ToolsetMemberAvailability.AVAILABLE
            and not self.published_tool_version_id
        ):
            raise ValueError("available catalog snapshot requires published version id")
        if (
            self.availability is not ToolsetMemberAvailability.AVAILABLE
            and self.published_tool_version_id is not None
        ):
            raise ValueError("unavailable catalog snapshot must not expose published version id")
        if self.serialized_schema_size < 0:
            raise ValueError("catalog snapshot schema size must not be negative")


class ToolsetCatalogReader(Protocol):
    """使用 Toolset UoW 的同一事务读取 Catalog 可用性。"""

    async def list_member_snapshots(
        self,
        tenant_id: str,
        tool_ids: tuple[str, ...],
    ) -> tuple[ToolsetCatalogSnapshot, ...]: ...

    async def list_published_snapshots(
        self,
        tenant_id: str,
    ) -> tuple[ToolsetCatalogSnapshot, ...]: ...


class ToolsetRepository(Protocol):
    async def add(self, tenant_id: str, toolset: Toolset) -> None: ...

    async def save(self, tenant_id: str, toolset: Toolset) -> None: ...

    async def get_by_id(self, tenant_id: str, toolset_id: str) -> Toolset | None: ...

    async def get_for_update(self, tenant_id: str, toolset_id: str) -> Toolset | None: ...

    async def get_by_slug(self, tenant_id: str, slug: str) -> Toolset | None: ...

    async def get_all_published(self, tenant_id: str) -> Toolset | None: ...

    async def list_by_tenant(self, tenant_id: str) -> tuple[Toolset, ...]: ...

    async def list_granted_active(
        self,
        tenant_id: str,
        principal_id: str,
    ) -> tuple[Toolset, ...]: ...


class ToolsetUnitOfWork(Protocol):
    @property
    def toolsets(self) -> ToolsetRepository: ...

    @property
    def catalog(self) -> ToolsetCatalogReader: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class ToolsetUnitOfWorkFactory(Protocol):
    def __call__(self) -> ToolsetUnitOfWork: ...
