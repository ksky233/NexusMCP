"""Tool 发现相关的 Application Use Case。"""

from dataclasses import dataclass

from nexusmcp.modules.catalog.domain import ToolDefinition
from nexusmcp.modules.catalog.ports import ToolRepository
from nexusmcp.shared.request_context import RequestContext


@dataclass(frozen=True, slots=True)
class ListVisibleToolsQuery:
    context: RequestContext


class ListVisibleTools:
    def __init__(self, repository: ToolRepository) -> None:
        self._repository = repository

    async def execute(self, query: ListVisibleToolsQuery) -> tuple[ToolDefinition, ...]:
        """返回当前请求 Principal 可见的已发布 Tool。"""

        tools = await self._repository.list_by_tenant(query.context.tenant_id)
        visible = [tool for tool in tools if tool.is_visible_to(query.context.principal_id)]
        return tuple(sorted(visible, key=lambda tool: tool.canonical_name))
