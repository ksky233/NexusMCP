"""Tool Catalog 用例拥有的 Repository 与事务 Port。"""

from types import TracebackType
from typing import Protocol, Self

from nexusmcp.modules.catalog.domain import PublishedTool, Tool, ToolVersion
from nexusmcp.modules.connectors.ports import ToolBindingRepository
from nexusmcp.modules.registry.ports import UpstreamRepository


class ToolCatalogRepository(Protocol):
    """以 Catalog 领域对象表达读写意图，不暴露 ORM 或 SQLAlchemy Session。"""

    async def add_tool(self, tenant_id: str, tool: Tool) -> None: ...

    async def save_tool(self, tenant_id: str, tool: Tool) -> None: ...

    async def get_tool_by_id(self, tenant_id: str, tool_id: str) -> Tool | None: ...

    async def get_tool_by_name(
        self,
        tenant_id: str,
        canonical_name: str,
    ) -> Tool | None: ...

    async def get_tool_for_update(self, tenant_id: str, tool_id: str) -> Tool | None: ...

    async def add_version(self, tenant_id: str, version: ToolVersion) -> None: ...

    async def save_version(self, tenant_id: str, version: ToolVersion) -> None: ...

    async def get_version_by_id(
        self,
        tenant_id: str,
        tool_version_id: str,
    ) -> ToolVersion | None: ...

    async def get_version_for_update(
        self,
        tenant_id: str,
        tool_version_id: str,
    ) -> ToolVersion | None: ...

    async def get_published_version(
        self,
        tenant_id: str,
        tool_id: str,
    ) -> ToolVersion | None: ...

    async def list_published_by_tenant(self, tenant_id: str) -> tuple[PublishedTool, ...]: ...

    async def get_published_by_name(
        self,
        tenant_id: str,
        canonical_name: str,
    ) -> PublishedTool | None: ...


class CatalogUnitOfWork(Protocol):
    """为 Catalog 与 Binding 的一次业务变更划定原子事务边界。"""

    @property
    def catalog(self) -> ToolCatalogRepository: ...

    @property
    def bindings(self) -> ToolBindingRepository: ...

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


class CatalogUnitOfWorkFactory(Protocol):
    """为每次 Command 创建独立事务边界，避免并发请求共享 Session。"""

    def __call__(self) -> CatalogUnitOfWork: ...
