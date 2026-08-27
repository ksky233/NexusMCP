"""Query Embedding 与 Vector Search Application Query 测试。"""

import pytest

from nexusmcp.modules.catalog.domain import (
    PublishedTool,
    PublishedToolSearchHit,
    ToolSideEffect,
    ToolVisibility,
)
from nexusmcp.modules.catalog.search import SearchPublishedToolsQuery
from nexusmcp.modules.tool_search.domain import EmbeddingVector, VectorSearchResult
from nexusmcp.modules.tool_search.vector_search import SearchVectorTools
from nexusmcp.shared.errors import EmbeddingResponseError, ToolSearchModeUnavailableError
from nexusmcp.shared.request_context import ProtocolEra, RequestContext


class FakeEmbeddingProvider:
    model = "test/embedding"
    dimensions = 3

    def __init__(self, vectors: tuple[EmbeddingVector, ...] | None = None) -> None:
        self.texts: tuple[str, ...] | None = None
        self._vectors = (
            vectors
            if vectors is not None
            else (
                EmbeddingVector(
                    model=self.model,
                    dimensions=self.dimensions,
                    values=(1.0, 0.0, 0.0),
                ),
            )
        )

    async def embed(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        self.texts = texts
        return self._vectors


class CapturingVectorSearch:
    def __init__(self, result: VectorSearchResult) -> None:
        self.result = result
        self.tenant_id: str | None = None
        self.query_vector: EmbeddingVector | None = None
        self.visibilities: tuple[ToolVisibility, ...] = ()
        self.namespace: str | None = None
        self.side_effect: ToolSideEffect | None = None
        self.limit = 0

    async def search_published_by_vector(
        self,
        tenant_id: str,
        query_vector: EmbeddingVector,
        *,
        visibilities: tuple[ToolVisibility, ...],
        namespace: str | None,
        side_effect: ToolSideEffect | None,
        limit: int,
    ) -> VectorSearchResult:
        self.tenant_id = tenant_id
        self.query_vector = query_vector
        self.visibilities = visibilities
        self.namespace = namespace
        self.side_effect = side_effect
        self.limit = limit
        return self.result


def context(principal_id: str = "operator") -> RequestContext:
    return RequestContext(
        request_id="request-vector-search",
        trace_id="a" * 32,
        protocol_version="2026-07-28",
        protocol_era=ProtocolEra.MODERN,
        tenant_id="tenant-a",
        principal_id=principal_id,
        authn_method="test",
    )


def search_hit() -> PublishedToolSearchHit:
    return PublishedToolSearchHit(
        tool=PublishedTool(
            tool_id="tool-get",
            tool_version_id="tool-get-v1",
            tenant_id="tenant-a",
            canonical_name="inventory.get_status",
            display_name="Get inventory status",
            description="Get current inventory status.",
            input_schema={"type": "object", "properties": {}},
            output_schema=None,
            version=1,
            visibility=ToolVisibility.AUTHENTICATED,
            side_effect=ToolSideEffect.READ_ONLY,
            schema_digest="1" * 64,
        ),
        rank=0.9,
    )


@pytest.mark.asyncio
async def test_query_embedding_is_ephemeral_and_static_scope_is_forwarded() -> None:
    provider = FakeEmbeddingProvider()
    adapter = CapturingVectorSearch(
        VectorSearchResult(hits=(search_hit(),), eligible_count=2, indexed_count=1)
    )
    use_case = SearchVectorTools(embedding_provider=provider, vector_search=adapter)

    result = await use_case.execute(
        SearchPublishedToolsQuery(
            context=context(),
            text="  items that are almost sold out  ",
            namespace="inventory",
            side_effect=ToolSideEffect.READ_ONLY,
            limit=8,
        )
    )

    assert result.hits[0].tool.canonical_name == "inventory.get_status"
    assert provider.texts == ("items that are almost sold out",)
    assert adapter.tenant_id == "tenant-a"
    assert adapter.query_vector is not None
    assert adapter.query_vector.values == (1.0, 0.0, 0.0)
    assert adapter.visibilities == (ToolVisibility.PUBLIC, ToolVisibility.AUTHENTICATED)
    assert adapter.namespace == "inventory"
    assert adapter.side_effect is ToolSideEffect.READ_ONLY
    assert adapter.limit == 8


@pytest.mark.asyncio
async def test_zero_index_coverage_is_not_silently_treated_as_hybrid() -> None:
    use_case = SearchVectorTools(
        embedding_provider=FakeEmbeddingProvider(),
        vector_search=CapturingVectorSearch(
            VectorSearchResult(hits=(), eligible_count=3, indexed_count=0)
        ),
    )

    with pytest.raises(ToolSearchModeUnavailableError):
        await use_case.execute(
            SearchPublishedToolsQuery(context=context(), text="find a warehouse tool")
        )


@pytest.mark.asyncio
async def test_query_embedding_provider_contract_is_checked() -> None:
    use_case = SearchVectorTools(
        embedding_provider=FakeEmbeddingProvider(vectors=()),
        vector_search=CapturingVectorSearch(
            VectorSearchResult(hits=(), eligible_count=0, indexed_count=0)
        ),
    )

    with pytest.raises(EmbeddingResponseError, match="count contract"):
        await use_case.execute(SearchPublishedToolsQuery(context=context(), text="anything"))
