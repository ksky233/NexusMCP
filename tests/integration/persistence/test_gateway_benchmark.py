"""PostgreSQL + MCP + Fake Upstream 的 Benchmark Smoke/显式快照。"""

import json
import os
from collections.abc import Awaitable, Callable
from time import perf_counter

import httpx
import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from benchmarks.tooling import BenchmarkSummary, capture_environment, summarize_benchmark
from examples.upstream_apis.employee_directory.app import app as employee_directory_app
from nexusmcp.bootstrap.app import create_app
from nexusmcp.bootstrap.config import Settings
from nexusmcp.infrastructure.identifiers import UuidIdentifierGenerator
from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntime
from nexusmcp.modules.catalog.adapters.sqlalchemy_reader import SqlAlchemyPublishedToolReader
from nexusmcp.modules.tool_search.adapters.sqlalchemy_uow import (
    SqlAlchemyToolSearchUnitOfWorkFactory,
)
from nexusmcp.modules.tool_search.document_builder import ToolSearchDocumentBuilder
from nexusmcp.modules.tool_search.evaluation import load_retrieval_eval_cases
from nexusmcp.modules.tool_search.reindex_tools import ReindexTools, ReindexToolsCommand
from tests.integration.persistence.test_multi_scenario_openapi_reuse import (
    NOW,
    SCENARIOS,
    FixedClock,
    import_review_publish_scenario,
    make_context,
    seed_registry,
)
from tests.integration.persistence.test_tool_search_retrieval_eval import (
    CASES_PATH,
    TOOL_ORDER,
    DeterministicEvalEmbeddingProvider,
)

pytestmark = [pytest.mark.integration, pytest.mark.benchmark]

RUN_FULL_BENCHMARK = os.getenv("NEXUSMCP_RUN_BENCHMARKS") == "1"


@pytest.mark.asyncio
async def test_gateway_benchmark_smoke_and_optional_snapshot(
    pg_session_factory: async_sessionmaker[AsyncSession],
    migrated_database_url: str,
) -> None:
    iterations = _iterations()
    async with pg_session_factory() as seed_session:
        await seed_registry(seed_session)
        postgres_version = str(await seed_session.scalar(text("select version()")))
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
    embedding_provider = DeterministicEvalEmbeddingProvider(cases)
    runtime = DatabaseRuntime(migrated_database_url)
    await runtime.start()
    try:
        reindex = await ReindexTools(
            published_tools=SqlAlchemyPublishedToolReader(runtime),
            unit_of_work_factory=SqlAlchemyToolSearchUnitOfWorkFactory(
                runtime.require_session_factory()
            ),
            document_builder=ToolSearchDocumentBuilder(),
            embedding_provider=embedding_provider,
            embedding_model=embedding_provider.model,
            embedding_dimensions=embedding_provider.dimensions,
            clock=clock,
            identifier_generator=identifier_generator,
        ).execute(ReindexToolsCommand(context=context))
    finally:
        await runtime.stop()

    upstream_transport = httpx.ASGITransport(app=employee_directory_app)
    summaries: list[BenchmarkSummary] = []
    async with httpx.AsyncClient(transport=upstream_transport) as upstream_client:
        app = create_app(
            Settings(
                environment="test",
                catalog_backend="postgresql",
                database_url=SecretStr(migrated_database_url),
                local_tenant_id=context.tenant_id,
                tool_execution_enabled=True,
                embedding_api_key=None,
            ),
            tool_http_client=upstream_client,
            embedding_provider=embedding_provider,
        )
        async with app.router.lifespan_context(app):
            transport = httpx2.ASGITransport(app=app)
            async with httpx2.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as http_client:
                modern_transport = streamable_http_client(
                    "http://testserver/mcp",
                    http_client=http_client,
                )
                async with Client(modern_transport) as client:
                    await client.list_tools(cache_mode="refresh")
                    summaries.extend(
                        [
                            await _measure(
                                "modern_tools_list",
                                iterations,
                                lambda: _list_tools(client),
                            ),
                            await _measure(
                                "lexical_tool_search",
                                iterations,
                                lambda: _search_tools(client, "lexical"),
                            ),
                            await _measure(
                                "hybrid_tool_search",
                                iterations,
                                lambda: _search_tools(client, "hybrid"),
                            ),
                            await _measure(
                                "read_only_tool_call",
                                iterations,
                                lambda: _call_employee(client),
                            ),
                        ]
                    )
                legacy_transport = streamable_http_client(
                    "http://testserver/mcp",
                    http_client=http_client,
                )
                async with Client(legacy_transport, mode="legacy") as legacy_client:
                    await legacy_client.list_tools(cache_mode="refresh")
                    summaries.append(
                        await _measure(
                            "legacy_tools_list",
                            iterations,
                            lambda: _list_tools(legacy_client),
                        )
                    )

    assert reindex.published_count == reindex.embedded_count == len(TOOL_ORDER)
    assert all(summary.errors == 0 for summary in summaries)
    assert {summary.scenario for summary in summaries} == {
        "hybrid_tool_search",
        "legacy_tools_list",
        "lexical_tool_search",
        "modern_tools_list",
        "read_only_tool_call",
    }
    if RUN_FULL_BENCHMARK:
        report = {
            "environment": capture_environment(
                postgres_version=postgres_version,
                tool_count=len(TOOL_ORDER),
                iterations=iterations,
                concurrency=1,
            ),
            "methodology": {
                "warmup_per_scenario": 1,
                "payload": "small demo JSON",
                "client": "in_process MCP Streamable HTTP",
                "cache": "tools/list refresh; no application result cache",
            },
            "scenarios": [summary.to_dict() for summary in summaries],
        }
        print("NEXUSMCP_BENCHMARK_REPORT=" + json.dumps(report, ensure_ascii=False))


async def _measure(
    scenario: str,
    iterations: int,
    operation: Callable[[], Awaitable[None]],
) -> BenchmarkSummary:
    await operation()
    durations: list[float] = []
    errors = 0
    wall_started = perf_counter()
    for _iteration in range(iterations):
        started_at = perf_counter()
        try:
            await operation()
        except Exception:
            errors += 1
        durations.append((perf_counter() - started_at) * 1000)
    return summarize_benchmark(
        scenario,
        tuple(durations),
        errors=errors,
        wall_seconds=perf_counter() - wall_started,
    )


async def _list_tools(client: Client) -> None:
    result = await client.list_tools(cache_mode="refresh")
    if len(result.tools) != len(TOOL_ORDER) + 1:
        raise AssertionError("benchmark tools/list returned an unexpected catalog")


async def _search_tools(client: Client, mode: str) -> None:
    result = await client.call_tool(
        "nexus.search_tools",
        {"query": "get employee", "retrieval_mode": mode, "limit": 3},
    )
    content = result.structured_content
    if (
        result.is_error
        or content is None
        or content["tools"][0]["name"] != "directory.get_employee"
    ):
        raise AssertionError("benchmark Tool Search returned an unexpected result")


async def _call_employee(client: Client) -> None:
    result = await client.call_tool(
        "directory.get_employee",
        {"employee_id": "emp-001"},
    )
    content = result.structured_content
    if result.is_error or content is None or content["employee_id"] != "emp-001":
        raise AssertionError("benchmark Tool Call returned an unexpected result")


def _iterations() -> int:
    if not RUN_FULL_BENCHMARK:
        return 3
    raw_value = os.getenv("NEXUSMCP_BENCHMARK_ITERATIONS", "30")
    try:
        value = int(raw_value)
    except ValueError:
        raise RuntimeError("NEXUSMCP_BENCHMARK_ITERATIONS must be an integer") from None
    if not 10 <= value <= 200:
        raise RuntimeError("benchmark iterations must be between 10 and 200")
    return value
