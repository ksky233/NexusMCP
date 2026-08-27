"""OpenTelemetry 白名单、Trace Propagation 与 Metric 基线测试。"""

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from nexusmcp.infrastructure.observability.telemetry import (
    NexusTelemetry,
    TelemetrySettings,
    create_telemetry_runtime,
)


def telemetry_with_memory_exporters() -> tuple[
    NexusTelemetry,
    InMemorySpanExporter,
    InMemoryMetricReader,
    TracerProvider,
    MeterProvider,
]:
    span_exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    metric_reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=[metric_reader])
    telemetry = NexusTelemetry(
        tracer=tracer_provider.get_tracer("nexusmcp.tests"),
        meter=meter_provider.get_meter("nexusmcp.tests"),
    )
    return telemetry, span_exporter, metric_reader, tracer_provider, meter_provider


def test_mcp_observation_propagates_trace_and_exports_allowlisted_evidence() -> None:
    telemetry, span_exporter, metric_reader, tracer_provider, meter_provider = (
        telemetry_with_memory_exporters()
    )
    try:
        with telemetry.observe_mcp_request(
            operation="tools.call",
            protocol_era="modern",
            tenant_id="tenant-a",
            principal_type="service",
            carrier={
                "traceparent": "00-11111111111111111111111111111111-2222222222222222-01",
                "authorization": "Bearer must-never-be-exported",
            },
        ) as observation:
            observation.set_tool_scope(tool_id="tool-1", tool_version_id="version-1")
            observation.set_search_mode("hybrid")
            observation.finish(outcome="rejected", error_code="authorization_denied")
            assert observation.trace_id == "1" * 32

        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.name == "mcp.tools.call"
        assert span.attributes is not None
        assert span.attributes["nexusmcp.tenant.id"] == "tenant-a"
        assert span.attributes["nexusmcp.tool.id"] == "tool-1"
        assert span.attributes["nexusmcp.search.mode"] == "hybrid"
        assert span.attributes["nexusmcp.error.code"] == "authorization_denied"
        assert "must-never-be-exported" not in repr(span.attributes)

        metrics_data = metric_reader.get_metrics_data()
        assert metrics_data is not None
        metric_names = {
            metric.name
            for resource_metric in metrics_data.resource_metrics
            for scope_metric in resource_metric.scope_metrics
            for metric in scope_metric.metrics
        }
        assert {
            "nexusmcp.mcp.requests",
            "nexusmcp.mcp.request.duration",
            "nexusmcp.tool.calls",
            "nexusmcp.tool.call.duration",
            "nexusmcp.tool_search.duration",
        } <= metric_names
    finally:
        meter_provider.shutdown()
        tracer_provider.shutdown()


def test_unexpected_exception_does_not_export_exception_message_or_secret() -> None:
    telemetry, span_exporter, _metric_reader, tracer_provider, meter_provider = (
        telemetry_with_memory_exporters()
    )
    try:
        with pytest.raises(RuntimeError, match="should stay local"):
            with telemetry.observe_mcp_request(
                operation="tools.list",
                protocol_era="modern",
                tenant_id="tenant-a",
                principal_type="user",
                carrier={},
            ):
                raise RuntimeError("password=should stay local")

        span = span_exporter.get_finished_spans()[0]
        assert span.events == ()
        assert span.attributes is not None
        assert span.attributes["nexusmcp.error.code"] == "unexpected_error"
        assert "should stay local" not in repr(span)
    finally:
        meter_provider.shutdown()
        tracer_provider.shutdown()


def test_disabled_runtime_is_noop_and_otlp_requires_safe_endpoint() -> None:
    runtime = create_telemetry_runtime(
        TelemetrySettings(
            enabled=False,
            exporter="none",
            service_name="nexusmcp",
            environment="test",
        )
    )
    runtime.shutdown()
    runtime.shutdown()

    with pytest.raises(ValueError, match="requires an endpoint"):
        TelemetrySettings(
            enabled=True,
            exporter="otlp_http",
            service_name="nexusmcp",
            environment="test",
        )
