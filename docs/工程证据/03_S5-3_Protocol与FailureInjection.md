# S5-3｜Protocol Compatibility 与 Failure Injection 证据

> 日期：2026-08-27
> 状态：完成

## 1. Protocol Compatibility Matrix

`evals/protocol/compatibility_matrix.json` 固定 15 条协议 Case：

- Modern `server/discover → tools/list → tools/call`；
- Legacy `initialize → tools/list → tools/call`；
- 两个 Era 的 Catalog 与业务结果一致；
- Modern HTTP 无 `Mcp-Session-Id`；
- Legacy HTTP `tools/list` 携带 Session ID；
- Request-scoped Dynamic Visibility；
- `tools/call` 重新鉴权；
- Search-First Dynamic Activation；
- Modern MRTR Approval；
- W3C Trace Propagation；
- Modern/Legacy 独立 Telemetry Era。
- Legacy Array-root Output Schema 安全省略适配。

新增 Raw Modern HTTP Boundary 断言：

| Case | HTTP | JSON-RPC Error |
|---|---:|---:|
| Malformed JSON | 400 | `-32700` Parse Error |
| Unknown Method | 404 | `-32601` Method Not Found |
| Header/Body Mismatch | 400 | SDK Header Mismatch |
| Unsupported Protocol Version | 400 | `-32022` + Supported Versions |

这些错误由锁定的 MCP SDK `2.0.0` Transport/Dispatcher 产生，NexusMCP 不复制或重写 SDK 私有协议实现。

## 2. Failure Injection Matrix

`evals/reliability/failure_injection_cases.json` 固定 14 条故障证据：

- Database Startup/Readiness；
- Catalog Commit Rollback；
- Audit Append Rollback；
- Retryable Upstream Failure；
- Non-Idempotent After-Send Timeout；
- Read-Only Retry Exhaustion；
- Client Cancellation；
- Approval Concurrent Consume；
- Idempotency Duplicate/Conflict；
- Embedding Rate Limit/Invalid Vector；
- Missing Vector Projection；
- DNS/Egress Policy Change。

每条 Matrix Case 指向现有 Pytest Node；防腐测试验证文件和测试函数仍然存在。这样 Failure Report 复用真正
验证事务与状态机的测试，不重复制造只检查 Exception 文本的浅层 Case。

## 3. 关键失败语义

```text
Database Startup Failure
→ App 不进入 Ready

Publish Commit Failure
→ Retire + Publish + Binding 全部 Rollback

Audit Append Failure
→ Approval Consume + Execution Plan 全部 Rollback

Non-Idempotent Timeout After Send
→ 不 Retry，Outcome Unknown

Read-Only Retry Exhausted
→ 多 Attempt，最终 Known Failed

Missing Vector Projection
→ Hybrid Unavailable，不伪装成 Lexical
```

## 4. Observability Evidence

- Modern Span Attribute：`nexusmcp.protocol.era=modern`；
- Legacy Span Attribute：`nexusmcp.protocol.era=legacy`；
- Legacy 请求增加 `nexusmcp.legacy.fallbacks` Counter；
- Protocol Error 不包含 Request Body、Authorization 或内部 Traceback；
- Trace、Log、Audit 继续通过 Trace ID 关联，不复制完整 Payload。

## 5. 验收

- Protocol Contract + Manifest：12 项通过；
- Modern Raw Error Mapping：通过；
- Legacy HTTP Session + OTel Counter：通过；
- 全量：280 Passed、2 个付费 External Skip；
- Ruff Lint/Format、basedpyright 0/0；
- PostgreSQL 测试只使用 `nexusmcp_test`。

## 6. 已知限制

- 尚未运行官方跨语言 MCP Conformance Suite；当前证据基于 Python SDK v2；
- Legacy Missing/Expired Session 的底层错误由 SDK 管理，本阶段验证了真实 Session Presence，没有复制
  SDK Session Manager 测试；
- Client Cancellation 当前以 Application Task Cancellation 验证，未模拟真实 TCP Half-Close；
- Multi-Worker Legacy Sticky Routing 仍属于部署层后续项；
- Failure Matrix 证明状态语义，不等于 Chaos Engineering 平台。

## 7. 下一步

进入 `S5-4｜Benchmark、Threat Model 与 S5 Unified Report`：建立显式 Benchmark Runner，固定环境、并发、
Payload、p50/p95/p99、Throughput/Error Rate，并把 S4 Eval、S5 Security/Protocol/Failure 证据汇总。
