"""Published Tool Keyword Search 的 Application Query。"""

from dataclasses import dataclass

from nexusmcp.modules.catalog.domain import PublishedToolSearchHit, ToolVisibility
from nexusmcp.modules.catalog.ports import PublishedToolSearch
from nexusmcp.shared.errors import InvalidArgumentsError
from nexusmcp.shared.request_context import ANONYMOUS_PRINCIPAL_ID, RequestContext


@dataclass(frozen=True, slots=True)
class SearchPublishedToolsQuery:
    context: RequestContext
    text: str
    limit: int = 10


class SearchPublishedTools:
    def __init__(self, search: PublishedToolSearch) -> None:
        self._search = search

    async def execute(
        self,
        query: SearchPublishedToolsQuery,
    ) -> tuple[PublishedToolSearchHit, ...]:
        query_text = query.text.strip()
        if not query_text:
            raise InvalidArgumentsError("tool search text must not be blank")
        if len(query_text) > 200:
            raise InvalidArgumentsError("tool search text must not exceed 200 characters")
        if not 1 <= query.limit <= 50:
            raise InvalidArgumentsError("tool search limit must be between 1 and 50")
        visibilities = (ToolVisibility.PUBLIC,)
        if query.context.principal_id != ANONYMOUS_PRINCIPAL_ID:
            visibilities = (
                ToolVisibility.PUBLIC,
                ToolVisibility.AUTHENTICATED,
            )
        return await self._search.search_published(
            query.context.tenant_id,
            query_text,
            visibilities=visibilities,
            limit=query.limit,
        )
