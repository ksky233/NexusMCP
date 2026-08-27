# ADR-0015｜手工 OpenTelemetry Boundary 与安全 Attribute 白名单

> 状态：Accepted
> 日期：2026-08-27

## Context

S5 需要用 Trace/Metric 证明 Modern/Legacy MCP、Tool Search 与 Tool Call 的运行行为。NexusMCP 同时处理
Authorization、Credential、Tool Arguments、Search Query 和 Upstream Result，直接启用全局自动
Instrumentation 可能把 URL、Header、异常消息或高基数字段带入 Telemetry。

现有结构化 Logging 已使用白名单 Formatter；OpenTelemetry 需要遵守相同的最小披露原则，并与应用
Lifespan、RequestContext Trace ID 和测试内存 Exporter 对齐。

## Decision

1. 使用 OpenTelemetry Python API/SDK `1.44.x`，Trace 与 Metric 进入主线，OTel Logs 暂不替换标准
   `logging`。
2. 第一版采用手工 MCP Boundary Instrumentation，不启用全局 FastAPI/HTTPX 自动 Instrumentation。
3. SDK Provider 不写入 OpenTelemetry Global Provider；由 Application Factory 创建并随 Lifespan
   Shutdown，测试可以注入隔离 Provider。
4. 支持三种 Exporter：
   - `none`：SDK/No-op 本地模式；
   - `console`：开发诊断；
   - `otlp_http`：发送到配置的 OTLP/HTTP Base Endpoint。
5. 使用 W3C `traceparent` 提取远端 Parent；实际 Span Trace ID 回写不可变 `RequestContext`，确保
   Log、Audit 与 Trace 相关联。无 SDK Span 时保留原 RequestContext Trace ID。
6. Span Name 只能是低基数稳定操作名：`mcp.tools.list`、`mcp.tools.call`，不能加入 Tool Name、Tenant
   或 Query。
7. Trace Attribute 白名单：
   - `nexusmcp.operation`；
   - `nexusmcp.protocol.era`；
   - `nexusmcp.tenant.id`；
   - `nexusmcp.principal.type`；
   - `nexusmcp.tool.id/tool.version_id`；
   - `nexusmcp.search.mode`；
   - `nexusmcp.outcome/error.code`。
8. Metric Attribute 不记录 Tenant ID、Principal ID、Tool ID 等高基数字段；只保留 Operation、Protocol
   Era、Principal Type、Outcome、稳定 Error Code 与 Search Mode。
9. 禁止记录 Authorization/Cookie/Token/Secret、完整 Arguments/Result、Search Query、OpenAPI/RAG
   正文和异常消息。Unexpected Exception 只记录 `unexpected_error`，不调用自动 Exception Event。
10. 第一批 Metric：
    - `nexusmcp.mcp.requests`；
    - `nexusmcp.mcp.request.duration`；
    - `nexusmcp.tool.calls`；
    - `nexusmcp.tool.call.duration`；
    - `nexusmcp.tool_search.duration`；
    - `nexusmcp.legacy.fallbacks`。

## Consequences

- 第一版不会自动获得 SQLAlchemy/httpx/FastAPI 内部 Span，关键业务 Span 在后续 S5 小步显式加入；
- 手工代码多于一键 Auto Instrumentation，但 Attribute Contract 可测试、可审计；
- OTLP Endpoint 配置只接受 HTTP/HTTPS Base URL，Exporter 自动追加 `/v1/traces` 与 `/v1/metrics`；
- Console/OTLP Exporter 的网络和输出成本只在显式启用时产生；默认运行不改变现有性能和外部依赖；
- Protocol、Security、Benchmark 报告可以用相同 Metric Name 和 Attribute Matrix 做回归。

## Verification

- InMemory Span/Metric Exporter 验证 Instrument Name、Status、Attribute；
- W3C Parent Trace ID 与 MCP Span Trace ID 一致；
- SDK Client 自动 `tools/list` 与显式 `nexus.search_tools` 均产生 Boundary Span；
- Query、Authorization Secret、异常消息不出现在 Span Attribute/Event；
- Legacy 请求产生独立 Metric Attribute/Counter；
- Provider 由应用 Lifespan 幂等 Shutdown。

## References

- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
- [Python Manual Instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/)
- [Python Exporters](https://opentelemetry.io/docs/languages/python/exporters/)
