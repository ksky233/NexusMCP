"""正式 MCP Adapter 的 Trace Propagation、Metric 与敏感字段隔离契约。"""

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from nexusmcp.bootstrap.app import create_app
from nexusmcp.bootstrap.config import Settings
from nexusmcp.infrastructure.observability import NexusTelemetry
from nexusmcp.modules.catalog.adapters.in_memory import InMemoryToolCatalogRepository
from nexusmcp.modules.catalog.domain import PublishedTool, ToolSideEffect, ToolVisibility


@pytest.mark.asyncio
async def test_mcp_boundary_exports_trace_metrics_without_query_or_authorization() -> None:
    span_exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    metric_reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=[metric_reader])
    telemetry = NexusTelemetry(
        tracer=tracer_provider.get_tracer("nexusmcp.contract"),
        meter=meter_provider.get_meter("nexusmcp.contract"),
    )
    repository = InMemoryToolCatalogRepository(
        published_tools=[
            PublishedTool(
                tool_id="directory-get-employee",
                tool_version_id="directory-get-employee-v1",
                tenant_id="local",
                canonical_name="directory.get_employee",
                display_name="Get employee",
                description="Get one employee by id.",
                input_schema={"type": "object", "properties": {}},
                output_schema=None,
                version=1,
                visibility=ToolVisibility.PUBLIC,
                side_effect=ToolSideEffect.READ_ONLY,
                schema_digest="1" * 64,
            )
        ]
    )
    app = create_app(
        Settings(environment="test", tool_discovery_mode="search_first"),
        repository,
        telemetry=telemetry,
    )
    secret = "Bearer telemetry-secret-must-not-export"
    try:
        async with app.router.lifespan_context(app):
            transport = httpx2.ASGITransport(app=app)
            async with httpx2.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                headers={
                    "traceparent": "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01",
                    "authorization": secret,
                },
            ) as http_client:
                mcp_transport = streamable_http_client(
                    "http://testserver/mcp",
                    http_client=http_client,
                )
                async with Client(mcp_transport) as client:
                    await client.list_tools(cache_mode="refresh")
                    result = await client.call_tool(
                        "nexus.search_tools",
                        {"query": "employee private query", "retrieval_mode": "lexical"},
                    )

        assert result.is_error is False
        spans = span_exporter.get_finished_spans()
        assert [span.name for span in spans].count("mcp.tools.list") >= 1
        call_spans = [span for span in spans if span.name == "mcp.tools.call"]
        assert len(call_spans) == 1
        assert all(
            span.context is not None and f"{span.context.trace_id:032x}" == "a" * 32
            for span in spans
        )
        call_span = call_spans[0]
        assert call_span.attributes is not None
        assert call_span.attributes["nexusmcp.search.mode"] == "lexical"
        exported = repr([(span.attributes, span.events) for span in spans])
        assert "employee private query" not in exported
        assert secret not in exported

        metrics_data = metric_reader.get_metrics_data()
        assert metrics_data is not None
        metric_names = {
            metric.name
            for resource_metric in metrics_data.resource_metrics
            for scope_metric in resource_metric.scope_metrics
            for metric in scope_metric.metrics
        }
        assert "nexusmcp.mcp.requests" in metric_names
        assert "nexusmcp.tool_search.duration" in metric_names
    finally:
        meter_provider.shutdown()
        tracer_provider.shutdown()


@pytest.mark.asyncio
async def test_legacy_http_request_has_distinct_span_attribute_and_metric() -> None:
    span_exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    metric_reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=[metric_reader])
    telemetry = NexusTelemetry(
        tracer=tracer_provider.get_tracer("nexusmcp.contract.legacy"),
        meter=meter_provider.get_meter("nexusmcp.contract.legacy"),
    )
    app = create_app(
        Settings(environment="test"),
        InMemoryToolCatalogRepository(),
        telemetry=telemetry,
    )
    try:
        async with app.router.lifespan_context(app):
            transport = httpx2.ASGITransport(app=app)
            async with httpx2.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as http_client:
                mcp_transport = streamable_http_client(
                    "http://testserver/mcp",
                    http_client=http_client,
                )
                async with Client(mcp_transport, mode="legacy") as client:
                    listed = await client.list_tools(cache_mode="refresh")
                    assert client.protocol_version == "2025-11-25"

        assert [tool.name for tool in listed.tools] == ["nexus.search_tools"]
        spans = span_exporter.get_finished_spans()
        assert spans
        assert all(
            span.attributes is not None and span.attributes["nexusmcp.protocol.era"] == "legacy"
            for span in spans
        )
        metrics_data = metric_reader.get_metrics_data()
        assert metrics_data is not None
        metric_names = {
            metric.name
            for resource_metric in metrics_data.resource_metrics
            for scope_metric in resource_metric.scope_metrics
            for metric in scope_metric.metrics
        }
        assert "nexusmcp.legacy.fallbacks" in metric_names
    finally:
        meter_provider.shutdown()
        tracer_provider.shutdown()
