"""供应用组装、Contract Test 使用的确定性内存 Catalog Adapter。"""

from __future__ import annotations

from collections.abc import Iterable

from nexusmcp.modules.catalog.domain import (
    PublishedTool,
    Tool,
    ToolVersion,
    ToolVersionStatus,
)


class InMemoryToolCatalogRepository:
    """不模拟 SQLAlchemy，只实现 ToolCatalogRepository 的业务可观察行为。"""

    def __init__(
        self,
        tools: Iterable[Tool] = (),
        versions: Iterable[ToolVersion] = (),
        published_tools: Iterable[PublishedTool] = (),
    ) -> None:
        self._tools = {tool.id: tool for tool in tools}
        self._versions = {version.id: version for version in versions}
        self._published_tools = {
            (tool.tenant_id, tool.canonical_name): tool for tool in published_tools
        }
        self._validate_seed_uniqueness()

    async def add_tool(self, tenant_id: str, tool: Tool) -> None:
        _require_matching_tenant(tenant_id, tool.tenant_id)
        if tool.id in self._tools:
            raise ValueError("tool id already exists")
        if await self.get_tool_by_name(tenant_id, tool.canonical_name) is not None:
            raise ValueError("tool canonical name already exists in tenant")
        self._tools[tool.id] = tool

    async def save_tool(self, tenant_id: str, tool: Tool) -> None:
        _require_matching_tenant(tenant_id, tool.tenant_id)
        current = self._tools.get(tool.id)
        if current is None or current.tenant_id != tenant_id:
            raise ValueError("tool does not exist in tenant")
        name_owner = await self.get_tool_by_name(tenant_id, tool.canonical_name)
        if name_owner is not None and name_owner.id != tool.id:
            raise ValueError("tool canonical name already exists in tenant")
        self._tools[tool.id] = tool

    async def get_tool_by_id(self, tenant_id: str, tool_id: str) -> Tool | None:
        tool = self._tools.get(tool_id)
        return tool if tool is not None and tool.tenant_id == tenant_id else None

    async def get_tool_by_name(
        self,
        tenant_id: str,
        canonical_name: str,
    ) -> Tool | None:
        return next(
            (
                tool
                for tool in self._tools.values()
                if tool.tenant_id == tenant_id and tool.canonical_name == canonical_name
            ),
            None,
        )

    async def get_tool_by_name_for_update(
        self,
        tenant_id: str,
        canonical_name: str,
    ) -> Tool | None:
        return await self.get_tool_by_name(tenant_id, canonical_name)

    async def get_tool_for_update(self, tenant_id: str, tool_id: str) -> Tool | None:
        # 内存执行是单线程确定性测试；方法保留业务所需的排他读取语义。
        return await self.get_tool_by_id(tenant_id, tool_id)

    async def add_version(self, tenant_id: str, version: ToolVersion) -> None:
        _require_matching_tenant(tenant_id, version.tenant_id)
        if version.id in self._versions:
            raise ValueError("tool version id already exists")
        if self._version_number_exists(version):
            raise ValueError("tool version number already exists")
        self._versions[version.id] = version

    async def save_version(self, tenant_id: str, version: ToolVersion) -> None:
        _require_matching_tenant(tenant_id, version.tenant_id)
        current = self._versions.get(version.id)
        if current is None or current.tenant_id != tenant_id:
            raise ValueError("tool version does not exist in tenant")
        if any(
            candidate.id != version.id
            and candidate.tool_id == version.tool_id
            and candidate.version == version.version
            for candidate in self._versions.values()
        ):
            raise ValueError("tool version number already exists")
        self._versions[version.id] = version

    async def get_version_by_id(
        self,
        tenant_id: str,
        tool_version_id: str,
    ) -> ToolVersion | None:
        version = self._versions.get(tool_version_id)
        return version if version is not None and version.tenant_id == tenant_id else None

    async def get_version_for_update(
        self,
        tenant_id: str,
        tool_version_id: str,
    ) -> ToolVersion | None:
        # PostgreSQL Adapter 会把同一意图映射为 SELECT ... FOR UPDATE。
        return await self.get_version_by_id(tenant_id, tool_version_id)

    async def get_published_version(
        self,
        tenant_id: str,
        tool_id: str,
    ) -> ToolVersion | None:
        return next(
            (
                version
                for version in self._versions.values()
                if version.tenant_id == tenant_id
                and version.tool_id == tool_id
                and version.status is ToolVersionStatus.PUBLISHED
            ),
            None,
        )

    async def next_version_number(self, tenant_id: str, tool_id: str) -> int:
        versions = [
            version.version
            for version in self._versions.values()
            if version.tenant_id == tenant_id and version.tool_id == tool_id
        ]
        return max(versions, default=0) + 1

    async def list_published_by_tenant(self, tenant_id: str) -> tuple[PublishedTool, ...]:
        tools = (tool for tool in self._published_tools.values() if tool.tenant_id == tenant_id)
        return tuple(sorted(tools, key=lambda tool: tool.canonical_name))

    async def get_published_by_name(
        self,
        tenant_id: str,
        canonical_name: str,
    ) -> PublishedTool | None:
        return self._published_tools.get((tenant_id, canonical_name))

    def clone(self) -> InMemoryToolCatalogRepository:
        """为 InMemory Unit of Work 创建事务内隔离副本。"""

        return InMemoryToolCatalogRepository(
            tools=self._tools.values(),
            versions=self._versions.values(),
            published_tools=self._published_tools.values(),
        )

    def replace_with(self, repository: InMemoryToolCatalogRepository) -> None:
        """一次替换完整内存状态，模拟原子 Commit 的可观察结果。"""

        self._tools = dict(repository._tools)
        self._versions = dict(repository._versions)
        self._published_tools = dict(repository._published_tools)

    def _version_number_exists(self, version: ToolVersion) -> bool:
        return any(
            candidate.tool_id == version.tool_id and candidate.version == version.version
            for candidate in self._versions.values()
        )

    def _validate_seed_uniqueness(self) -> None:
        names = [(tool.tenant_id, tool.canonical_name) for tool in self._tools.values()]
        versions = [(version.tool_id, version.version) for version in self._versions.values()]
        if len(names) != len(set(names)):
            raise ValueError("tool canonical name already exists in tenant")
        if len(versions) != len(set(versions)):
            raise ValueError("tool version number already exists")


def _require_matching_tenant(requested_tenant_id: str, entity_tenant_id: str) -> None:
    if requested_tenant_id != entity_tenant_id:
        raise ValueError("entity tenant does not match repository tenant scope")
