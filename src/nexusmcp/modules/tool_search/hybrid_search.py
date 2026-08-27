"""Lexical、Vector 与 RRF 的 Hybrid Tool Search 编排。"""

import asyncio

from nexusmcp.modules.catalog.domain import PublishedToolSearchHit
from nexusmcp.modules.catalog.search import SearchPublishedTools, SearchPublishedToolsQuery
from nexusmcp.modules.tool_search.rank_fusion import ReciprocalRankFusion
from nexusmcp.modules.tool_search.vector_search import SearchVectorTools


class SearchHybridTools:
    def __init__(
        self,
        *,
        lexical_search: SearchPublishedTools,
        vector_search: SearchVectorTools,
        rank_fusion: ReciprocalRankFusion,
    ) -> None:
        self._lexical_search = lexical_search
        self._vector_search = vector_search
        self._rank_fusion = rank_fusion

    @property
    def index_version(self) -> str:
        return self._vector_search.index_version

    async def execute(
        self,
        query: SearchPublishedToolsQuery,
    ) -> tuple[PublishedToolSearchHit, ...]:
        lexical_hits, vector_result = await asyncio.gather(
            self._lexical_search.execute(query),
            self._vector_search.execute(query),
        )
        return self._rank_fusion.fuse(
            (lexical_hits, vector_result.hits),
            limit=query.limit,
        )
