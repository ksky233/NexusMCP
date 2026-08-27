"""Benchmark Summary 与运行环境采集。"""

import math
import os
import platform
import sys
from dataclasses import asdict, dataclass

import psutil


@dataclass(frozen=True, slots=True)
class BenchmarkSummary:
    scenario: str
    iterations: int
    errors: int
    error_rate: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    throughput_ops_per_second: float

    def to_dict(self) -> dict[str, str | int | float]:
        return asdict(self)


def summarize_benchmark(
    scenario: str,
    durations_ms: tuple[float, ...],
    *,
    errors: int,
    wall_seconds: float,
) -> BenchmarkSummary:
    if not scenario.strip() or not durations_ms:
        raise ValueError("benchmark scenario and durations must not be empty")
    if errors < 0 or errors > len(durations_ms):
        raise ValueError("benchmark error count was invalid")
    if wall_seconds <= 0 or not math.isfinite(wall_seconds):
        raise ValueError("benchmark wall time must be finite and positive")
    if any(duration < 0 or not math.isfinite(duration) for duration in durations_ms):
        raise ValueError("benchmark durations must be finite and non-negative")
    iterations = len(durations_ms)
    return BenchmarkSummary(
        scenario=scenario,
        iterations=iterations,
        errors=errors,
        error_rate=errors / iterations,
        latency_p50_ms=_percentile(durations_ms, 0.50),
        latency_p95_ms=_percentile(durations_ms, 0.95),
        latency_p99_ms=_percentile(durations_ms, 0.99),
        throughput_ops_per_second=iterations / wall_seconds,
    )


def capture_environment(
    *,
    postgres_version: str,
    tool_count: int,
    iterations: int,
    concurrency: int,
) -> dict[str, str | int | bool]:
    process = psutil.Process()
    return {
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "processor": platform.processor() or "unknown",
        "cpu_logical": os.cpu_count() or 0,
        "cpu_physical": psutil.cpu_count(logical=False) or 0,
        "memory_total_bytes": psutil.virtual_memory().total,
        "process_rss_bytes_after_run": process.memory_info().rss,
        "postgresql": postgres_version,
        "tool_count": tool_count,
        "iterations_per_scenario": iterations,
        "concurrency": concurrency,
        "telemetry_enabled": False,
        "audit_enabled": True,
        "upstream_transport": "in_process_asgi",
        "embedding_provider": "deterministic_in_memory",
    }


def _percentile(values: tuple[float, ...], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction
