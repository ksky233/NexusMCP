# S5-0/1｜工程证据矩阵与 OpenTelemetry 基线

> 日期：2026-08-27
> 状态：完成

## 1. 实现内容

- 新增 S5 Evidence Matrix，区分已完成证据与后续安全/协议/Benchmark 工作；
- 锁定 OpenTelemetry API/SDK/OTLP HTTP Exporter `1.44.x`；
- Application Factory 组装独立 TracerProvider/MeterProvider；
- Provider 随 FastAPI Lifespan 幂等 Shutdown，不污染测试 Global Provider；
- MCP `tools/list`、`tools/call` 建立 SERVER Span；
- W3C `traceparent` 传播到实际 Span，并回写 RequestContext Trace ID；
- 建立 MCP、Tool Call、Tool Search、Legacy Count/Duration Metric；
- 支持 `none/console/otlp_http` Exporter；
- InMemory Exporter Contract Test 证明 Attribute、Metric 和敏感字段边界。

## 2. 安全选择

没有启用 FastAPI/httpx 全局 Auto Instrumentation。第一版只在可信 MCP Interface Boundary 手工埋点，
避免自动采集 URL、Header、Query Parameter 或异常消息。

Trace 可以记录 Tenant ID、Tool ID 等受控内部标识；Metric 为避免高基数，不记录这些 ID。两者都不记录
Search Query、Tool Arguments、Result、Token、Secret 或正文。

## 3. Trace/Log/Audit 关系

```text
Trace
= 一次调用的因果与耗时

Log
= 运行诊断事件，可采样和轮转

Audit
= 谁对什么执行了什么，需要稳定持久化
```

三者通过同一个 32 Hex Trace ID 关联，但不会互相复制敏感 Payload。

## 4. 验证

- OTel Unit/Contract、Bootstrap/Config 与既有 MCP Contract 共 23 项通过；
- Trace Parent `aaaaaaaa...` 被正式 MCP Span 继承；
- MCP SDK 自动 Discovery 会产生真实 `tools/list` Span；
- `nexus.search_tools` 产生 `tools.call` Span 与 Search Duration；
- Authorization 与私有 Query 不出现在 Span Attribute/Event；
- Unexpected Exception 不产生包含异常消息的 OTel Exception Event；
- Ruff 与 basedpyright 通过。

## 5. 下一步

进入 `S5-2｜Security 与 Policy Regression`。重点不是简单封禁所有 Private IP，而是为“企业内部 API”
场景设计可配置 Egress Allowlist、Metadata Endpoint Hard Deny、DNS 解析/执行时复检，并把现有 Tenant、
Principal、Credential、Approval、Idempotency 安全证据统一到 Golden Matrix。

正式实现边界见
[ADR-0016｜Upstream Egress 与 SSRF 防护边界](../adr/0016-upstream-egress-and-ssrf-boundary.md)。
