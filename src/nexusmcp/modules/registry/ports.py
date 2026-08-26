"""Registry 上下文拥有的持久化 Port。"""

from types import TracebackType
from typing import Protocol, Self

from nexusmcp.modules.registry.domain import UpstreamService


class UpstreamRepository(Protocol):
    async def add(self, tenant_id: str, upstream: UpstreamService) -> None: ...

    async def save(self, tenant_id: str, upstream: UpstreamService) -> None: ...

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

    async def get_by_name(
        self,
        tenant_id: str,
        namespace: str,
        name: str,
    ) -> UpstreamService | None: ...

    async def list_by_tenant(self, tenant_id: str) -> tuple[UpstreamService, ...]: ...


class RegistryUnitOfWork(Protocol):
    @property
    def upstreams(self) -> UpstreamRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class RegistryUnitOfWorkFactory(Protocol):
    def __call__(self) -> RegistryUnitOfWork: ...
