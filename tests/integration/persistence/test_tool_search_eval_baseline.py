"""当前 8 个 Demo Tool 的 PostgreSQL FTS Eval Baseline。"""

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexusmcp.infrastructure.identifiers import UuidIdentifierGenerator
from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntime
from nexusmcp.modules.catalog.adapters.sqlalchemy_search import SqlAlchemyPublishedToolSearch
from nexusmcp.modules.catalog.search import SearchPublishedTools, SearchPublishedToolsQuery
from tests.integration.persistence.test_multi_scenario_openapi_reuse import (
    NOW,
    SCENARIOS,
    FixedClock,
    import_review_publish_scenario,
    make_context,
    seed_registry,
)

pytestmark = pytest.mark.integration

CASES_PATH = Path(__file__).resolve().parents[3] / "evals" / "tool_search" / "lexical_cases.json"


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

    cases: list[dict[str, Any]] = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
    runtime = DatabaseRuntime(migrated_database_url)
    await runtime.start()
    try:
        search = SearchPublishedTools(SqlAlchemyPublishedToolSearch(runtime))
        outcomes: list[tuple[dict[str, Any], list[str]]] = []
        for case in cases:
            hits = await search.execute(
                SearchPublishedToolsQuery(
                    context=context,
                    text=str(case["query"]),
                    limit=3,
                )
            )
            outcomes.append((case, [hit.tool.canonical_name for hit in hits]))
    finally:
        await runtime.stop()

    lexical = [outcome for outcome in outcomes if outcome[0]["lexical_expected"] is True]
    semantic_targets = [outcome for outcome in outcomes if outcome[0]["lexical_expected"] is False]
    top_1 = sum(names[:1] == [case["expected_tool"]] for case, names in lexical) / len(lexical)
    hit_at_3 = sum(case["expected_tool"] in names for case, names in lexical) / len(lexical)
    semantic_misses = sum(case["expected_tool"] not in names for case, names in semantic_targets)

    assert top_1 >= 0.75
    assert hit_at_3 == 1.0
    # 已知 Gap 是 S4 Vector/Hybrid 的输入证据，而不是把 FTS 描述成语义搜索。
    assert semantic_misses >= 2
