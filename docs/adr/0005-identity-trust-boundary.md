# ADR-0005｜Identity 与 Trust Boundary

> 状态：Accepted；产品身份范围由 ADR-0019 收窄
> 日期：2026-08-26

## Context

MCP、Admin HTTP、机器 Credential 和可信代理都可能携带 Principal/Tenant 信息。直接信任 Header、
透传 Token 或让业务读取完整 Claims 会混淆认证边界并泄漏 Credential。

## Decision

1. 只有 Authentication Adapter 可以创建 `InternalPrincipal`。
2. Tenant/Principal 必须来自已验证 Credential 或受控本地配置，不能来自未验证 Header。
3. `InternalPrincipal` 只保存 Principal Type 和白名单 Attributes，不保存 Token/原始 Claims；Roles 是实现兼容
   字段，不代表员工角色系统。
4. `ActorContext` 承载协议无关 Actor；MCP `RequestContext` 在其上扩展 Protocol Context。
5. Anonymous Principal 不携带可信 Roles。
6. Policy 无匹配规则时 Default DENY。
7. Local Admin 使用固定 Settings Principal，禁止 Production 启用。
8. Data Plane Principal 主线只包含 Agent Service；员工身份与 Agent 会话用户不进入 NexusMCP。
9. 多 Agent 共用部署必须通过受信机器 Credential 或 Trusted Proxy 映射 Principal。

## Rejected Alternatives

- 把 Inbound Token 原样作为 Egress Credential；
- 信任客户端 Tenant/User/Agent Header；
- 在 Domain/Log/Audit 保存完整 JWT Claims；
- 每个 Interface 自己定义互不兼容的 Principal。

## Consequences

- Protocol/Auth Adapter 必须完成 Service Credential Mapping 与 Allowlist；
- Use Case 可以只依赖可信 Principal；
- 测试必须覆盖 Forged Header、Wrong Service Credential 和 Cross-Tenant；
- 员工 IAM、用户中心和完整 OAuth/OIDC Server 不属于当前项目范围。
