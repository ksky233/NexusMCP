"""供应用组装和测试使用的确定性内存 Catalog Adapter。"""

from collections.abc import Iterable, Sequence

from nexusmcp.modules.catalog.domain import ToolDefinition, ToolStatus


class InMemoryToolRepository:
    """长期保留的测试/开发 Adapter，与未来 PostgreSQL 实现遵循同一 Port。"""

    def __init__(self, tools: Iterable[ToolDefinition] = ()) -> None:
        self._tools = tuple(tools)

    async def list_by_tenant(self, tenant_id: str) -> Sequence[ToolDefinition]:
        return tuple(tool for tool in self._tools if tool.tenant_id == tenant_id)

    async def get_published_by_name(
        self,
        tenant_id: str,
        canonical_name: str,
    ) -> ToolDefinition | None:
        return next(
            (
                tool
                for tool in self._tools
                if tool.tenant_id == tenant_id
                and tool.canonical_name == canonical_name
                and tool.status is ToolStatus.PUBLISHED
            ),
            None,
        )
