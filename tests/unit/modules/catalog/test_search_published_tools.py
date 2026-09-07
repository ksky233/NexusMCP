"""SearchPublishedTools 参数与粗粒度 Visibility 测试。"""

from dataclasses import dataclass

import pytest

from nexusmcp.modules.catalog.domain import (
    PublishedTool,
    PublishedToolSearchHit,
    ToolSideEffect,
    ToolVisibility,
)
from nexusmcp.modules.catalog.search import SearchPublishedTools, SearchPublishedToolsQuery
from nexusmcp.shared.errors import InvalidArgumentsError
from nexusmcp.shared.request_context import ProtocolEra, RequestContext


@dataclass
class CapturingSearch:
    visibilities: tuple[ToolVisibility, ...] = ()
    query_text: str = ""
    limit: int = 0
    namespace: str | None = None
    side_effect: ToolSideEffect | None = None
    eligible_tool_ids: tuple[str, ...] | None = None

    async def search_published(
        self,
        tenant_id: str,
        query_text: str,
        *,
        visibilities: tuple[ToolVisibility, ...],
        eligible_tool_ids: tuple[str, ...] | None,
        namespace: str | None,
        side_effect: ToolSideEffect | None,
        limit: int,
    ) -> tuple[PublishedToolSearchHit, ...]:
        _ = tenant_id
        self.visibilities = visibilities
        self.eligible_tool_ids = eligible_tool_ids
        self.query_text = query_text
        self.limit = limit
        self.namespace = namespace
        self.side_effect = side_effect
        return (
            PublishedToolSearchHit(
                tool=PublishedTool(
                    tool_id="tool-1",
                    tool_version_id="version-1",
                    tenant_id="tenant-a",
                    canonical_name="inventory.reserve_stock",
                    display_name="Reserve stock",
                    description="Create a stock reservation.",
                    input_schema={"type": "object", "properties": {}},
                    output_schema=None,
                    version=1,
                    visibility=ToolVisibility.PUBLIC,
                    side_effect=ToolSideEffect.NON_IDEMPOTENT_WRITE,
                    schema_digest="1" * 64,
                ),
                rank=1.0,
            ),
        )


def _context(principal_id: str) -> RequestContext:
    return RequestContext(
        request_id="request-search",
        trace_id="6" * 32,
        protocol_version="2026-07-28",
        protocol_era=ProtocolEra.MODERN,
        tenant_id="tenant-a",
        principal_id=principal_id,
        authn_method="test",
    )


@pytest.mark.asyncio
async def test_search_normalizes_text_limit_and_anonymous_visibility() -> None:
    adapter = CapturingSearch()

    hits = await SearchPublishedTools(adapter).execute(
        SearchPublishedToolsQuery(
            context=_context("anonymous"),
            text="  reserve stock  ",
            limit=5,
            namespace=" inventory ",
            side_effect=ToolSideEffect.NON_IDEMPOTENT_WRITE,
            eligible_tool_ids=("tool-1",),
        )
    )

    assert [hit.tool.canonical_name for hit in hits] == ["inventory.reserve_stock"]
    assert adapter.query_text == "reserve stock"
    assert adapter.limit == 5
    assert adapter.visibilities == (ToolVisibility.PUBLIC,)
    assert adapter.namespace == "inventory"
    assert adapter.side_effect is ToolSideEffect.NON_IDEMPOTENT_WRITE
    assert adapter.eligible_tool_ids == ("tool-1",)


@pytest.mark.asyncio
async def test_authenticated_search_includes_authenticated_but_not_restricted() -> None:
    adapter = CapturingSearch()

    await SearchPublishedTools(adapter).execute(
        SearchPublishedToolsQuery(context=_context("operator"), text="incident")
    )

    assert adapter.visibilities == (
        ToolVisibility.PUBLIC,
        ToolVisibility.AUTHENTICATED,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "limit"),
    [
        ("   ", 10),
        ("x" * 201, 10),
        ("stock", 0),
        ("stock", 51),
    ],
)
async def test_search_rejects_invalid_query(text: str, limit: int) -> None:
    with pytest.raises(InvalidArgumentsError):
        await SearchPublishedTools(CapturingSearch()).execute(
            SearchPublishedToolsQuery(
                context=_context("operator"),
                text=text,
                limit=limit,
            )
        )
