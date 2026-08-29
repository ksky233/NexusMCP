"""Lexical、Vector 与 RRF 的 Hybrid Tool Search 编排。"""

import asyncio
from dataclasses import dataclass

from nexusmcp.modules.catalog.domain import PublishedToolSearchHit
from nexusmcp.modules.catalog.search import SearchPublishedTools, SearchPublishedToolsQuery
from nexusmcp.modules.tool_search.rank_fusion import ReciprocalRankFusion
from nexusmcp.modules.tool_search.vector_search import SearchVectorTools


@dataclass(frozen=True, slots=True)
class HybridHitDiagnostics:
    rrf_score: float
    lexical_rank: int | None
    lexical_score: float | None
    vector_rank: int | None
    vector_cosine_similarity: float | None


@dataclass(frozen=True, slots=True)
class HybridSearchResult:
    hits: tuple[PublishedToolSearchHit, ...]
    diagnostics: dict[str, HybridHitDiagnostics]


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
        return (await self.execute_detailed(query)).hits

    async def execute_detailed(
        self,
        query: SearchPublishedToolsQuery,
    ) -> HybridSearchResult:
        lexical_hits, vector_result = await asyncio.gather(
            self._lexical_search.execute(query),
            self._vector_search.execute(query),
        )
        fused = self._rank_fusion.fuse(
            (lexical_hits, vector_result.hits),
            limit=query.limit,
        )
        lexical = _ranked_hits(lexical_hits)
        vector = _ranked_hits(vector_result.hits)
        return HybridSearchResult(
            hits=fused,
            diagnostics={
                hit.tool.tool_version_id: HybridHitDiagnostics(
                    rrf_score=hit.rank,
                    lexical_rank=(
                        lexical[hit.tool.tool_version_id][0]
                        if hit.tool.tool_version_id in lexical
                        else None
                    ),
                    lexical_score=(
                        lexical[hit.tool.tool_version_id][1]
                        if hit.tool.tool_version_id in lexical
                        else None
                    ),
                    vector_rank=(
                        vector[hit.tool.tool_version_id][0]
                        if hit.tool.tool_version_id in vector
                        else None
                    ),
                    vector_cosine_similarity=(
                        vector[hit.tool.tool_version_id][1]
                        if hit.tool.tool_version_id in vector
                        else None
                    ),
                )
                for hit in fused
            },
        )


def _ranked_hits(
    hits: tuple[PublishedToolSearchHit, ...],
) -> dict[str, tuple[int, float]]:
    ranked: dict[str, tuple[int, float]] = {}
    for position, hit in enumerate(hits, start=1):
        ranked.setdefault(hit.tool.tool_version_id, (position, hit.rank))
    return ranked
