"""当前 8 个 Demo Tool 的 PostgreSQL FTS Eval Baseline。"""

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.infrastructure.identifiers import UuidIdentifierGenerator
from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntime
from nexusmcp.modules.catalog.adapters.sqlalchemy_search import SqlAlchemyPublishedToolSearch
from nexusmcp.modules.catalog.search import SearchPublishedTools, SearchPublishedToolsQuery
from nexusmcp.modules.tool_search.evaluation import (
    RetrievalEvalCase,
    load_retrieval_eval_cases,
)
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


@pytest.mark.asyncio
async def test_postgresql_fts_baseline_has_expected_exact_recall_and_known_semantic_gaps(
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
    runtime = DatabaseRuntime(migrated_database_url)
    await runtime.start()
    try:
        search = SearchPublishedTools(SqlAlchemyPublishedToolSearch(runtime))
        outcomes: list[tuple[RetrievalEvalCase, list[str]]] = []
        for case in cases:
            hits = await search.execute(
                SearchPublishedToolsQuery(
                    context=context,
                    text=case.query,
                    limit=3,
                    namespace=case.namespace,
                    side_effect=case.side_effect,
                )
            )
            outcomes.append((case, [hit.tool.canonical_name for hit in hits]))
    finally:
        await runtime.stop()

    lexical = [
        (case, names) for case, names in outcomes if case.lexical_expected and case.relevance
    ]
    semantic_targets = [
        (case, names) for case, names in outcomes if not case.lexical_expected and case.relevance
    ]
    no_matches = [(case, names) for case, names in outcomes if not case.relevance]
    top_1 = sum(bool(names) and names[0] in case.relevant_tools for case, names in lexical) / len(
        lexical
    )
    hit_at_3 = sum(
        any(name in case.relevant_tools for name in names[:3]) for case, names in lexical
    ) / len(lexical)
    semantic_misses = sum(
        not any(name in case.relevant_tools for name in names) for case, names in semantic_targets
    )

    assert top_1 >= 0.75
    assert hit_at_3 == 1.0
    assert all(not names for _case, names in no_matches)
    # 已知 Gap 是 S4 Vector/Hybrid 的输入证据，而不是把 FTS 描述成语义搜索。
    assert semantic_misses >= 2
