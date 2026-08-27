# S5-4｜Gateway Benchmark 基线

> 日期：2026-08-27
> 状态：完成

## 1. 方法

Benchmark 使用：

- Windows 11 Host；
- Python 3.12.10；
- Docker PostgreSQL 18.6 + pgvector 0.8.6；
- 8 个 OpenAPI Import/Review/Publish Demo Tool；
- MCP Streamable HTTP In-Process ASGI Transport；
- Employee Directory In-Process ASGI Upstream；
- Deterministic In-Memory Query Embedding；
- Audit 开启、Telemetry 关闭；
- 每场景 Warmup 1 次、采样 30 次、并发 1；
- `tools/list` 强制 Refresh，不命中 Client Cache。

普通 CI 运行 3 次 Smoke，只验证 Runner 与结果；显式设置以下变量才生成正式快照：

```powershell
$env:NEXUSMCP_RUN_BENCHMARKS = "1"
$env:NEXUSMCP_BENCHMARK_ITERATIONS = "30"
uv run python -m pytest tests/integration/persistence/test_gateway_benchmark.py -q -s
```

## 2. 结果

| Scenario | P50 | P95 | P99 | Throughput | Error Rate |
|---|---:|---:|---:|---:|---:|
| Modern tools/list | 8.74 ms | 14.05 ms | 15.77 ms | 104.37 ops/s | 0% |
| Lexical Tool Search | 17.58 ms | 69.20 ms | 81.80 ms | 40.16 ops/s | 0% |
| Hybrid Tool Search | 19.70 ms | 53.04 ms | 67.50 ms | 38.01 ops/s | 0% |
| Read-Only Tool Call | 70.45 ms | 133.35 ms | 146.61 ms | 12.98 ops/s | 0% |
| Legacy tools/list | 8.91 ms | 21.48 ms | 29.98 ms | 83.05 ops/s | 0% |

机器可读快照：
[2026-08-27_local_postgresql18.json](../../benchmarks/results/2026-08-27_local_postgresql18.json)。

## 3. 解释

- Modern/Legacy `tools/list` P50 接近，Legacy Stateful Session 的吞吐与 Tail 稍差，但 30 次样本不能用于
  统计显著性结论；
- Hybrid 相比 Lexical 的 P50 增加约 2.1 ms；该结果使用内存 Query Embedding，不含在线模型网络延迟；
- Read-Only Call 包含 Resolve、Policy、Execution/Audit 多个 PostgreSQL 短事务和 Fake Upstream，因此比
  Search 明显更高；
- Windows Scheduler、Docker Desktop 与低采样数使 P95/P99 易波动；
- 并发 1 只能作为回归基线，不能推导最大吞吐、连接池容量或生产 SLO。

## 4. 使用边界

这个快照用于：

- 后续改动前后同环境对比；
- 发现数量级回退；
- 证明报告包含环境、Payload、Cache、Audit/Trace 开关和错误率。

它不用于：

- 宣称生产 QPS；
- 选择 HNSW/IVFFlat；
- 估算真实 SiliconFlow End-to-End Latency；
- 证明高并发、多 Worker、远程 PostgreSQL 或真实企业网络表现。

后续 Capacity Benchmark 需要独立进程、真实 TCP、并发梯度、稳定 Warmup、更多样本和资源监控。
