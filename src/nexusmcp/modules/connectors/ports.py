"""Connectors 上下文拥有的持久化 Port。"""

from typing import Protocol

from nexusmcp.modules.connectors.domain import ToolBinding


class ToolBindingRepository(Protocol):
    """持久化 ToolVersion 与执行目标之间的一对一绑定。"""

    async def add(self, tenant_id: str, binding: ToolBinding) -> None: ...

    async def save(self, tenant_id: str, binding: ToolBinding) -> None: ...

    async def get_by_id(
        self,
        tenant_id: str,
        binding_id: str,
    ) -> ToolBinding | None: ...

    async def get_by_tool_version(
        self,
        tenant_id: str,
        tool_version_id: str,
    ) -> ToolBinding | None: ...

    async def get_by_tool_version_for_update(
        self,
        tenant_id: str,
        tool_version_id: str,
    ) -> ToolBinding | None: ...

    async def get_for_update(
        self,
        tenant_id: str,
        binding_id: str,
    ) -> ToolBinding | None: ...
