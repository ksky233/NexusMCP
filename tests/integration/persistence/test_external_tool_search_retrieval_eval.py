"""显式开启的 SiliconFlow Tool Retrieval Quality Eval。"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.bootstrap.config import Settings
from nexusmcp.infrastructure.identifiers import UuidIdentifierGenerator
from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntime
from nexusmcp.modules.catalog.adapters.sqlalchemy_reader import SqlAlchemyPublishedToolReader
from nexusmcp.modules.catalog.adapters.sqlalchemy_search import SqlAlchemyPublishedToolSearch
from nexusmcp.modules.catalog.search import SearchPublishedTools
from nexusmcp.modules.credentials.domain import SecretValue
from nexusmcp.modules.tool_search.adapters.siliconflow import SiliconFlowEmbeddingProvider
from nexusmcp.modules.tool_search.adapters.sqlalchemy_uow import (
    SqlAlchemyToolSearchUnitOfWorkFactory,
)
from nexusmcp.modules.tool_search.adapters.sqlalchemy_vector_search import (
    SqlAlchemyExactVectorToolSearch,
)
from nexusmcp.modules.tool_search.document_builder import ToolSearchDocumentBuilder
from nexusmcp.modules.tool_search.domain import EmbeddingVector
from nexusmcp.modules.tool_search.evaluation import (
    RetrievalEvalCase,
    RetrievalEvalObservation,
    RetrievalEvalStrategy,
    collect_retrieval_observations,
    evaluate_retrieval,
    load_retrieval_eval_cases,
)
from nexusmcp.modules.tool_search.hybrid_search import SearchHybridTools
from nexusmcp.modules.tool_search.rank_fusion import ReciprocalRankFusion
from nexusmcp.modules.tool_search.reindex_tools import ReindexTools, ReindexToolsCommand
from nexusmcp.modules.tool_search.vector_search import SearchVectorTools
from tests.integration.persistence.test_multi_scenario_openapi_reuse import (
    NOW,
    SCENARIOS,
    FixedClock,
    import_review_publish_scenario,
    make_context,
    seed_registry,
)
from tests.integration.persistence.test_tool_search_retrieval_eval import TOOL_ORDER

RUN_EXTERNAL = os.getenv("NEXUSMCP_RUN_EXTERNAL_TESTS") == "1"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.external,
    pytest.mark.skipif(
        not RUN_EXTERNAL,
        reason="set NEXUSMCP_RUN_EXTERNAL_TESTS=1 to call the paid embedding API",
    ),
]

CASES_PATH = Path(__file__).resolve().parents[3] / "evals" / "tool_search" / "retrieval_cases.json"


class PrecomputedQueryEmbeddingProvider:
    """复用一次真实 Batch 结果，避免为三种 Strategy 重复调用付费 API。"""

    def __init__(
        self,
        *,
        model: str,
        dimensions: int,
        vectors_by_query: dict[str, EmbeddingVector],
    ) -> None:
        self._model = model
        self._dimensions = dimensions
        self._vectors_by_query = vectors_by_query

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        try:
            return tuple(self._vectors_by_query[text] for text in texts)
        except KeyError:
            raise ValueError("retrieval eval query was not precomputed") from None


@pytest.mark.asyncio
async def test_siliconflow_retrieval_quality_snapshot(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    settings = Settings()
    api_key = settings.embedding_api_key
    if api_key is None:
        pytest.fail("NEXUSMCP_EMBEDDING_API_KEY is required for external retrieval eval")
    async with pg_session_factory() as seed_session:
        await seed_registry(seed_session)
    context = make_context()
    clock = FixedClock(NOW)
    identifier_generator = UuidIdentifierGenerator()
    for scenario in SCENARIOS:
        await import_review_publish_scenario(
            scenario,
            session_factory=pg_session_factory,
            context=context,
            clock=clock,
            identifier_generator=identifier_generator,
        )

    cases = load_retrieval_eval_cases(CASES_PATH)
    runtime = DatabaseRuntime(migrated_database_url)
    client = httpx.AsyncClient(follow_redirects=False, trust_env=False)
    provider = SiliconFlowEmbeddingProvider(
        client,
        api_url=settings.embedding_api_url,
        api_key=SecretValue(api_key.get_secret_value()),
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        timeout_seconds=settings.embedding_timeout_seconds,
        max_batch_size=settings.embedding_batch_size,
    )
    await runtime.start()
    try:
        reindex = await ReindexTools(
            published_tools=SqlAlchemyPublishedToolReader(runtime),
            unit_of_work_factory=SqlAlchemyToolSearchUnitOfWorkFactory(
                runtime.require_session_factory()
            ),
            document_builder=ToolSearchDocumentBuilder(),
            embedding_provider=provider,
            embedding_model=provider.model,
            embedding_dimensions=provider.dimensions,
            clock=clock,
            identifier_generator=identifier_generator,
        ).execute(ReindexToolsCommand(context=context))
        query_vectors, query_batch_count, query_embedding_latency_ms = await _precompute_queries(
            provider,
            cases,
            batch_size=settings.embedding_batch_size,
        )
        cached_provider = PrecomputedQueryEmbeddingProvider(
            model=provider.model,
            dimensions=provider.dimensions,
            vectors_by_query=query_vectors,
        )
        lexical = SearchPublishedTools(SqlAlchemyPublishedToolSearch(runtime))
        vector = SearchVectorTools(
            embedding_provider=cached_provider,
            vector_search=SqlAlchemyExactVectorToolSearch(runtime),
        )
        hybrid = SearchHybridTools(
            lexical_search=lexical,
            vector_search=vector,
            rank_fusion=ReciprocalRankFusion(),
        )
        observations = await collect_retrieval_observations(
            cases,
            context=context,
            lexical=lexical,
            vector=vector,
            hybrid=hybrid,
        )
    finally:
        await client.aclose()
        await runtime.stop()

    metrics = {
        strategy.value: evaluate_retrieval(
            cases,
            observations,
            strategy=strategy,
        ).to_dict()
        for strategy in RetrievalEvalStrategy
    }
    report = {
        "run": {
            "recorded_at": datetime.now(UTC).isoformat(),
            "provider": "SiliconFlow",
            "model": provider.model,
            "dimensions": provider.dimensions,
            "distance": "cosine",
            "vector_index": "exact_scan",
            "rank_fusion": "rrf_k_60",
            "query_embedding_mode": "precomputed_batch_for_cost_control",
            "retrieval_latency_scope": "database_and_fusion_without_remote_embedding",
            "query_embedding_batch_count": query_batch_count,
            "query_embedding_batch_latency_ms": query_embedding_latency_ms,
        },
        "dataset": {
            "case_count": len(cases),
            "positive_case_count": sum(bool(case.relevance) for case in cases),
            "no_match_case_count": sum(not case.relevance for case in cases),
            "tool_count": len(TOOL_ORDER),
            "categories": sorted({case.category for case in cases}),
        },
        "index": {
            "published_count": reindex.published_count,
            "embedded_count": reindex.embedded_count,
            "current_count": reindex.current_count,
        },
        "metrics": metrics,
        "metrics_by_category": _metrics_by_category(cases, observations),
        "rankings": [
            {
                "case_id": observation.case_id,
                "strategy": observation.strategy.value,
                "ranked_tools": list(observation.ranked_tools),
            }
            for observation in observations
        ],
    }
    print("NEXUSMCP_RETRIEVAL_EVAL_REPORT=" + json.dumps(report, ensure_ascii=False))

    assert reindex.published_count == reindex.embedded_count == len(TOOL_ORDER)
    assert query_batch_count <= 2
    assert all(
        strategy_metrics["unauthorized_leakage_count"] == 0 for strategy_metrics in metrics.values()
    )


async def _precompute_queries(
    provider: SiliconFlowEmbeddingProvider,
    cases: tuple[RetrievalEvalCase, ...],
    *,
    batch_size: int,
) -> tuple[dict[str, EmbeddingVector], int, float]:
    vectors_by_query: dict[str, EmbeddingVector] = {}
    batch_count = 0
    started_at = perf_counter()
    for start in range(0, len(cases), batch_size):
        batch = cases[start : start + batch_size]
        texts = tuple(case.query for case in batch)
        vectors = await provider.embed(texts)
        vectors_by_query.update(zip(texts, vectors, strict=True))
        batch_count += 1
    return vectors_by_query, batch_count, (perf_counter() - started_at) * 1000


def _metrics_by_category(
    cases: tuple[RetrievalEvalCase, ...],
    observations: tuple[RetrievalEvalObservation, ...],
) -> dict[str, dict[str, dict[str, object]]]:
    results: dict[str, dict[str, dict[str, object]]] = {}
    for category in sorted({case.category for case in cases}):
        category_cases = tuple(case for case in cases if case.category == category)
        category_ids = {case.id for case in category_cases}
        category_observations = tuple(
            observation for observation in observations if observation.case_id in category_ids
        )
        if not any(case.relevance for case in category_cases):
            continue
        results[category] = {
            strategy.value: evaluate_retrieval(
                category_cases,
                category_observations,
                strategy=strategy,
            ).to_dict()
            for strategy in RetrievalEvalStrategy
        }
    return results
