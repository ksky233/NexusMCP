"""Benchmark Percentile、Throughput 与 Error Rate 公式测试。"""

import pytest

from benchmarks.tooling import summarize_benchmark


def test_benchmark_summary_uses_deterministic_percentiles_and_wall_time() -> None:
    summary = summarize_benchmark(
        "tools_list",
        (1.0, 2.0, 3.0, 4.0, 5.0),
        errors=1,
        wall_seconds=0.5,
    )

    assert summary.iterations == 5
    assert summary.error_rate == 0.2
    assert summary.latency_p50_ms == 3.0
    assert summary.latency_p95_ms == pytest.approx(4.8)
    assert summary.latency_p99_ms == pytest.approx(4.96)
    assert summary.throughput_ops_per_second == 10.0


def test_benchmark_summary_rejects_invalid_evidence() -> None:
    with pytest.raises(ValueError, match="durations"):
        summarize_benchmark("tools_list", (), errors=0, wall_seconds=1)
    with pytest.raises(ValueError, match="error count"):
        summarize_benchmark("tools_list", (1.0,), errors=2, wall_seconds=1)
