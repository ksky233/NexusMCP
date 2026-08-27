"""OpenTelemetry Trace/Metric Runtime 与安全 MCP 请求观测边界。"""

import sys
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter
from typing import Literal

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import Counter, Histogram, Meter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.trace import Span, SpanKind, Status, StatusCode, Tracer
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

type TelemetryExporter = Literal["none", "console", "otlp_http"]
type AttributeValue = str | bool | int | float

_INSTRUMENTATION_NAME = "nexusmcp"
_INSTRUMENTATION_VERSION = "0.1.0"


@dataclass(frozen=True, slots=True)
class TelemetrySettings:
    enabled: bool
    exporter: TelemetryExporter
    service_name: str
    environment: str
    otlp_endpoint: str | None = None
    export_interval_ms: int = 60_000
    export_timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not self.service_name.strip() or not self.environment.strip():
            raise ValueError("telemetry service and environment must not be blank")
        if self.export_interval_ms <= 0 or self.export_timeout_seconds <= 0:
            raise ValueError("telemetry export timing must be positive")
        if self.exporter == "otlp_http" and not self.otlp_endpoint:
            raise ValueError("OTLP HTTP telemetry exporter requires an endpoint")


class McpRequestObservation:
    """单个 MCP Boundary Span；只开放稳定白名单字段。"""

    def __init__(
        self,
        *,
        span: Span,
        operation: str,
        protocol_era: str,
        principal_type: str,
        started_at: float,
        requests_counter: Counter,
        request_duration: Histogram,
        tool_calls_counter: Counter,
        tool_call_duration: Histogram,
        search_duration: Histogram,
        legacy_fallback_counter: Counter,
    ) -> None:
        self._span = span
        self._operation = operation
        self._protocol_era = protocol_era
        self._principal_type = principal_type
        self._started_at = started_at
        self._requests_counter = requests_counter
        self._request_duration = request_duration
        self._tool_calls_counter = tool_calls_counter
        self._tool_call_duration = tool_call_duration
        self._search_duration = search_duration
        self._legacy_fallback_counter = legacy_fallback_counter
        self._search_mode: str | None = None
        self._finished = False

    @property
    def trace_id(self) -> str | None:
        context = self._span.get_span_context()
        return f"{context.trace_id:032x}" if context.is_valid else None

    def set_tool_scope(self, *, tool_id: str, tool_version_id: str) -> None:
        self._span.set_attribute("nexusmcp.tool.id", tool_id)
        self._span.set_attribute("nexusmcp.tool.version_id", tool_version_id)

    def set_search_mode(self, retrieval_mode: str) -> None:
        self._search_mode = retrieval_mode
        self._span.set_attribute("nexusmcp.search.mode", retrieval_mode)

    def finish(self, *, outcome: str, error_code: str | None = None) -> None:
        if self._finished:
            return
        self._finished = True
        duration_ms = (perf_counter() - self._started_at) * 1000
        self._span.set_attribute("nexusmcp.outcome", outcome)
        if error_code is not None:
            self._span.set_attribute("nexusmcp.error.code", error_code)
            self._span.set_status(Status(StatusCode.ERROR))
        else:
            self._span.set_status(Status(StatusCode.OK))
        metric_attributes: dict[str, AttributeValue] = {
            "nexusmcp.operation": self._operation,
            "nexusmcp.protocol.era": self._protocol_era,
            "nexusmcp.principal.type": self._principal_type,
            "nexusmcp.outcome": outcome,
        }
        if error_code is not None:
            metric_attributes["nexusmcp.error.code"] = error_code
        self._requests_counter.add(1, metric_attributes)
        self._request_duration.record(duration_ms, metric_attributes)
        if self._operation == "tools.call":
            self._tool_calls_counter.add(1, metric_attributes)
            self._tool_call_duration.record(duration_ms, metric_attributes)
        if self._search_mode is not None:
            search_attributes = dict(metric_attributes)
            search_attributes["nexusmcp.search.mode"] = self._search_mode
            self._search_duration.record(duration_ms, search_attributes)
        if self._protocol_era == "legacy":
            self._legacy_fallback_counter.add(1, metric_attributes)


class NexusTelemetry:
    """只暴露 NexusMCP 允许的 Span/Metric，不接受任意 Attribute Mapping。"""

    def __init__(self, *, tracer: Tracer, meter: Meter) -> None:
        self._tracer = tracer
        self._requests_counter = meter.create_counter(
            "nexusmcp.mcp.requests",
            unit="{request}",
            description="Completed MCP boundary requests.",
        )
        self._request_duration = meter.create_histogram(
            "nexusmcp.mcp.request.duration",
            unit="ms",
            description="MCP boundary request duration.",
        )
        self._tool_calls_counter = meter.create_counter(
            "nexusmcp.tool.calls",
            unit="{call}",
            description="Completed MCP tools/call requests.",
        )
        self._tool_call_duration = meter.create_histogram(
            "nexusmcp.tool.call.duration",
            unit="ms",
            description="MCP tools/call duration.",
        )
        self._search_duration = meter.create_histogram(
            "nexusmcp.tool_search.duration",
            unit="ms",
            description="Built-in Tool Search duration.",
        )
        self._legacy_fallback_counter = meter.create_counter(
            "nexusmcp.legacy.fallbacks",
            unit="{request}",
            description="Requests served through the Legacy compatibility era.",
        )

    @classmethod
    def noop(cls) -> "NexusTelemetry":
        return cls(
            tracer=trace.NoOpTracerProvider().get_tracer(
                _INSTRUMENTATION_NAME,
                _INSTRUMENTATION_VERSION,
            ),
            meter=metrics.NoOpMeterProvider().get_meter(
                _INSTRUMENTATION_NAME,
                _INSTRUMENTATION_VERSION,
            ),
        )

    @contextmanager
    def observe_mcp_request(
        self,
        *,
        operation: str,
        protocol_era: str,
        tenant_id: str,
        principal_type: str,
        carrier: Mapping[str, str],
    ) -> Generator[McpRequestObservation, None, None]:
        parent_context = TraceContextTextMapPropagator().extract(
            carrier=carrier,
        )
        attributes: dict[str, AttributeValue] = {
            "nexusmcp.operation": operation,
            "nexusmcp.protocol.era": protocol_era,
            "nexusmcp.tenant.id": tenant_id,
            "nexusmcp.principal.type": principal_type,
        }
        with self._tracer.start_as_current_span(
            f"mcp.{operation}",
            context=parent_context,
            kind=SpanKind.SERVER,
            attributes=attributes,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            observation = McpRequestObservation(
                span=span,
                operation=operation,
                protocol_era=protocol_era,
                principal_type=principal_type,
                started_at=perf_counter(),
                requests_counter=self._requests_counter,
                request_duration=self._request_duration,
                tool_calls_counter=self._tool_calls_counter,
                tool_call_duration=self._tool_call_duration,
                search_duration=self._search_duration,
                legacy_fallback_counter=self._legacy_fallback_counter,
            )
            try:
                yield observation
            except BaseException:
                observation.finish(outcome="error", error_code="unexpected_error")
                raise
            finally:
                observation.finish(outcome="success")


class TelemetryRuntime:
    def __init__(
        self,
        *,
        telemetry: NexusTelemetry,
        tracer_provider: TracerProvider | None = None,
        meter_provider: MeterProvider | None = None,
    ) -> None:
        self.telemetry = telemetry
        self.tracer_provider = tracer_provider
        self.meter_provider = meter_provider
        self._shutdown = False

    def shutdown(self) -> None:
        if self._shutdown:
            return
        self._shutdown = True
        if self.meter_provider is not None:
            self.meter_provider.shutdown()
        if self.tracer_provider is not None:
            self.tracer_provider.shutdown()


def create_telemetry_runtime(settings: TelemetrySettings) -> TelemetryRuntime:
    if not settings.enabled:
        return TelemetryRuntime(telemetry=NexusTelemetry.noop())

    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "deployment.environment.name": settings.environment,
        }
    )
    metric_readers: list[PeriodicExportingMetricReader] = []
    tracer_provider = TracerProvider(resource=resource)
    if settings.exporter == "console":
        tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        metric_readers.append(
            PeriodicExportingMetricReader(
                ConsoleMetricExporter(out=sys.stdout),
                export_interval_millis=settings.export_interval_ms,
                export_timeout_millis=settings.export_timeout_seconds * 1000,
            )
        )
    elif settings.exporter == "otlp_http":
        endpoint = _validated_otlp_endpoint(settings.otlp_endpoint)
        tracer_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=f"{endpoint}/v1/traces",
                    timeout=settings.export_timeout_seconds,
                )
            )
        )
        metric_readers.append(
            PeriodicExportingMetricReader(
                OTLPMetricExporter(
                    endpoint=f"{endpoint}/v1/metrics",
                    timeout=settings.export_timeout_seconds,
                ),
                export_interval_millis=settings.export_interval_ms,
                export_timeout_millis=settings.export_timeout_seconds * 1000,
            )
        )
    meter_provider = MeterProvider(resource=resource, metric_readers=metric_readers)
    return TelemetryRuntime(
        telemetry=NexusTelemetry(
            tracer=tracer_provider.get_tracer(
                _INSTRUMENTATION_NAME,
                _INSTRUMENTATION_VERSION,
            ),
            meter=meter_provider.get_meter(
                _INSTRUMENTATION_NAME,
                _INSTRUMENTATION_VERSION,
            ),
        ),
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )


def _validated_otlp_endpoint(value: str | None) -> str:
    if value is None or not value.startswith(("https://", "http://")):
        raise ValueError("OTLP HTTP endpoint must use http or https")
    return value.rstrip("/")
