"""Query Embedding 与 Exact Vector Tool Search 的 Application Query。"""

from nexusmcp.modules.catalog.domain import ToolVisibility
from nexusmcp.modules.catalog.search import SearchPublishedToolsQuery
from nexusmcp.modules.tool_search.domain import VectorSearchResult
from nexusmcp.modules.tool_search.ports import EmbeddingProvider, VectorToolSearch
from nexusmcp.shared.errors import (
    EmbeddingResponseError,
    InvalidArgumentsError,
    ToolSearchModeUnavailableError,
)
from nexusmcp.shared.request_context import ANONYMOUS_PRINCIPAL_ID


class SearchVectorTools:
    """把一次自然语言 Query 转为临时向量，并执行 Exact Cosine Search。"""

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        vector_search: VectorToolSearch,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._vector_search = vector_search

    @property
    def index_version(self) -> str:
        """以 Model + Dimensions 标识本次 Query 使用的可重建 Projection 版本。"""

        return f"{self._embedding_provider.model}@{self._embedding_provider.dimensions}"

    async def execute(self, query: SearchPublishedToolsQuery) -> VectorSearchResult:
        query_text = _validate_query(query)
        if query.eligible_tool_ids == ():
            return VectorSearchResult(hits=(), eligible_count=0, indexed_count=0)
        vectors = await self._embedding_provider.embed((query_text,))
        if len(vectors) != 1:
            raise EmbeddingResponseError("query embedding provider violated count contract")
        query_vector = vectors[0]
        if (
            query_vector.model != self._embedding_provider.model
            or query_vector.dimensions != self._embedding_provider.dimensions
        ):
            raise EmbeddingResponseError("query embedding provider violated model contract")
        visibilities = (ToolVisibility.PUBLIC,)
        if query.context.principal_id != ANONYMOUS_PRINCIPAL_ID:
            visibilities = (
                ToolVisibility.PUBLIC,
                ToolVisibility.AUTHENTICATED,
            )
        result = await self._vector_search.search_published_by_vector(
            query.context.tenant_id,
            query_vector,
            visibilities=visibilities,
            eligible_tool_ids=query.eligible_tool_ids,
            namespace=query.namespace,
            side_effect=query.side_effect,
            limit=query.limit,
        )
        # Exact Search 没有相似度阈值：有索引就应至少返回最近邻。零覆盖说明当前模型未建索引。
        if result.eligible_count > 0 and result.indexed_count == 0:
            raise ToolSearchModeUnavailableError("tool vector index was missing for search scope")
        return result


def _validate_query(query: SearchPublishedToolsQuery) -> str:
    query_text = query.text.strip()
    if not query_text:
        raise InvalidArgumentsError("tool search text must not be blank")
    if len(query_text) > 200:
        raise InvalidArgumentsError("tool search text must not exceed 200 characters")
    if not 1 <= query.limit <= 50:
        raise InvalidArgumentsError("tool search limit must be between 1 and 50")
    if query.namespace is not None and not query.namespace.strip():
        raise InvalidArgumentsError("tool search namespace must not be blank")
    return query_text
