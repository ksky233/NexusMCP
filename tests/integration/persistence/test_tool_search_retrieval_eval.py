"""8 个 Demo Tool 的确定性 Vector/Hybrid Retrieval Eval。"""

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.infrastructure.identifiers import UuidIdentifierGenerator
from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntime
from nexusmcp.modules.catalog.adapters.sqlalchemy_reader import SqlAlchemyPublishedToolReader
from nexusmcp.modules.catalog.adapters.sqlalchemy_search import SqlAlchemyPublishedToolSearch
from nexusmcp.modules.catalog.search import SearchPublishedTools
from nexusmcp.modules.tool_search.adapters.sqlalchemy_models import TOOL_EMBEDDING_DIMENSIONS
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

pytestmark = pytest.mark.integration

CASES_PATH = Path(__file__).resolve().parents[3] / "evals" / "tool_search" / "retrieval_cases.json"
TOOL_ORDER = (
    "directory.get_employee",
    "directory.list_employees",
    "directory.search_employees",
    "inventory.get_status",
    "inventory.reserve_stock",
    "inventory.set_reorder_level",
    "ops.acknowledge_incident",
    "ops.get_status",
)


class DeterministicEvalEmbeddingProvider:
    """把人工标签映射到正交向量，只验证 Pipeline，不冒充真实语义质量。"""

    model = "eval/deterministic-one-hot-v1"
    dimensions = TOOL_EMBEDDING_DIMENSIONS

    def __init__(self, cases: tuple[RetrievalEvalCase, ...]) -> None:
        self._tool_dimensions = {name: index for index, name in enumerate(TOOL_ORDER)}
        self._query_targets = {
            case.query: (
                max(case.relevance, key=lambda item: item[1])[0] if case.relevance else None
            )
            for case in cases
        }

    async def embed(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        return tuple(self._embed_one(text) for text in texts)

    def _embed_one(self, text: str) -> EmbeddingVector:
        canonical_name = _canonical_name_from_document(text)
        target = canonical_name or self._query_targets.get(text)
        # No-Match Query 使用与所有 Tool 正交的维度；Exact Search 仍会返回最近候选，暴露无阈值边界。
        dimension = self._tool_dimensions[target] if target is not None else len(TOOL_ORDER)
        values = [0.0] * self.dimensions
        values[dimension] = 1.0
        return EmbeddingVector(
            model=self.model,
            dimensions=self.dimensions,
            values=tuple(values),
        )


def _canonical_name_from_document(text: str) -> str | None:
    prefix = "Canonical Name: "
    first_line = text.partition("\n")[0]
    return first_line.removeprefix(prefix) if first_line.startswith(prefix) else None


@pytest.mark.asyncio
async def test_deterministic_retrieval_eval_covers_full_projection_and_governance_filters(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
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
    provider = DeterministicEvalEmbeddingProvider(cases)
    runtime = DatabaseRuntime(migrated_database_url)
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
        lexical = SearchPublishedTools(SqlAlchemyPublishedToolSearch(runtime))
        vector = SearchVectorTools(
            embedding_provider=provider,
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
        await runtime.stop()

    lexical_metrics = evaluate_retrieval(
        cases,
        observations,
        strategy=RetrievalEvalStrategy.LEXICAL,
    )
    vector_metrics = evaluate_retrieval(
        cases,
        observations,
        strategy=RetrievalEvalStrategy.VECTOR,
    )
    hybrid_metrics = evaluate_retrieval(
        cases,
        observations,
        strategy=RetrievalEvalStrategy.HYBRID,
    )

    assert reindex.published_count == reindex.embedded_count == len(TOOL_ORDER)
    assert lexical_metrics.no_match_accuracy == 1.0
    assert vector_metrics.top_1_accuracy == 1.0
    assert hybrid_metrics.hit_at_k == 1.0
    assert all(
        metrics.unauthorized_leakage_count == 0
        for metrics in (lexical_metrics, vector_metrics, hybrid_metrics)
    )
