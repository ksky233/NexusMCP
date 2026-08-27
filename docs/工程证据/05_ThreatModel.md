# NexusMCP Threat Model

> 日期：2026-08-27
> 范围：当前单体部署、MCP Interface、Control Plane、PostgreSQL、Embedding Provider 与 HTTP Upstream

## 1. 资产

- Tenant、Principal、Role 与认证事实；
- Tool Schema、Binding、Upstream Endpoint；
- SecretReference 与瞬时 SecretValue；
- Tool Arguments、Result 与 Idempotency Key；
- Approval、Execution、Attempt 与 Audit；
- Search Query、Canonical Document 与 Embedding Vector；
- PostgreSQL 数据与 Telemetry。

## 2. Trust Boundary

```text
Untrusted Agent / MCP Client
→ Transport/Auth Boundary
→ Internal Principal + Tenant
→ Catalog / Policy / Approval
→ Credential Resolution
→ Egress Policy
→ Enterprise Upstream

Platform Admin
→ Local Control Plane
→ Registry / Import / Review / Publish

NexusMCP
→ PostgreSQL / Embedding Provider / OTLP Collector
```

客户端 Header、Tool Arguments、OpenAPI Document、Upstream Response 与在线模型响应全部视为不可信输入。

## 3. Threat / Mitigation / Evidence

| ID | Threat | Mitigation | Evidence | Residual Risk |
|---|---|---|---|---|
| T01 | Forged Tenant/Principal | Authenticator 创建 Internal Principal，不信任业务 Header | Principal Integration | 完整 OIDC/JWKS 未实现 |
| T02 | Cross-Tenant Read/Call/Search | Repository SQL Tenant Scope + Domain Guard + Policy | Security Manifest | DB Superuser 不在应用威胁模型内 |
| T03 | SSRF/Internal Scan | Static Host/CIDR/Port Allowlist、Metadata Hard Deny、DNS 双检、Redirect Off | ADR-0016 + Egress E2E | 无严格 DNS Pinning/Egress Proxy |
| T04 | Secret Leakage | SecretReference、瞬时 SecretValue、Log/Trace/Audit 白名单 | Secret/Telemetry Tests | Upstream 自身可能回显 Secret |
| T05 | Policy Bypass | Call 阶段重新鉴权、Default DENY、Golden Matrix | 10 Policy Cases | 通用 Condition DSL 未实现 |
| T06 | Approval Replay/Tamper | Signed Request State、Snapshot Digest、行锁单次消费 | Approval Tests | 外部审批系统未接入 |
| T07 | Duplicate Side Effect | Side Effect 分类、Idempotency Claim、Attempt、Unknown Outcome | Retry/Idempotency E2E | 跨系统 Result Replay/Reconciliation 未完成 |
| T08 | Schema/Binding Tamper | Review/Publish Digest、原子事务、不可变 Version | Publish Integration | Tool Description Prompt Injection 需运营治理 |
| T09 | Audit Failure/Tamper | 核心 Audit 同库同步、Append-only Domain、失败回滚 | Audit Failure Injection | Retention/WORM/外部归档未实现 |
| T10 | Tool Search Leakage | Tenant/Visibility/Policy Filter、Over-fetch 后过滤 | Retrieval Eval/Security | No-Match Confidence Gate 未实现 |
| T11 | Protocol Confusion | SDK v2、Modern/Legacy Matrix、Header/Body Validation | 15 Protocol Cases | 跨语言 Conformance Suite 未运行 |
| T12 | Resource Exhaustion | Body/Result/Batch/TopK/Retry/Timeout 上限 | Unit/Contract | Rate Limit、Quota、Load Shedding 未实现 |
| T13 | Telemetry Data Exfiltration | Manual Instrumentation、Attribute 白名单、无 Exception Message | ADR-0015 | OTLP Backend 权限由部署方负责 |

## 4. 安全不变量

- DENY 后不得解析 Secret 或访问 Upstream；
- Unsafe Egress 不得创建 Execution 或发送 HTTP；
- Tenant Scope 必须在搜索和读取排名前生效；
- Non-Idempotent Unknown Outcome 不自动 Retry；
- Approval 只能消费一次且必须匹配原调用；
- Log/Trace/Audit 不保存完整 Arguments、Result、Token、Secret 或正文；
- Protocol Error 不返回内部 Traceback；
- Publish 事务失败不得留下半发布状态。

## 5. 明确不声称

- 不是零信任网络或完整 API Gateway/WAF；
- 未完成 Production OIDC、KMS/Vault、Rate Limit、WORM Audit；
- 未证明高并发、多 Worker、跨区容灾；
- DNS 执行前复检不等于 Socket Pinning；
- Search Candidate 不等于最终 Tool 正确性保证；
- Platform/Database/Collector 管理员主机失陷不在当前应用层防护范围。

## 6. 后续优先级

1. Production OIDC/JWKS 与 Audience/Issuer Rotation；
2. Egress Proxy 或 DNS Pinning；
3. Rate Limit/Quota/Load Shedding；
4. Audit Retention/WORM Export；
5. Hard Negative Tool Search Confidence Gate；
6. Dependency/Container/Secret Scan 与 SBOM。
