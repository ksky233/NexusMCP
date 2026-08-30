# ADR-0006｜Credential Reference 与 Egress Injection

> 状态：Accepted  
> 日期：2026-08-26

## Context

NexusMCP 需要代表已授权 Agent Service Principal 调用企业 Upstream，但 Tool Schema、Binding、数据库、日志、Audit 和
模型响应都不能保存真实 Secret。Inbound Credential、Internal Principal 和 Egress Credential 必须分离。

## Decision

1. 数据库只保存 `SecretReference(provider, opaque_reference, version)`。
2. `CredentialBinding` 按 Tenant、Subject、Tool（可选）和 Upstream 选择 SecretReference。
3. 相同优先级出现多条 Binding 时 Fail Closed，不随机选择。
4. Policy ALLOW/Approval Consume 之后才解析 Secret。
5. `CredentialProvider` 返回临时 `SecretValue`；字符串表示永远脱敏。
6. `ResolvedCredential` 只进入单次 Executor 调用，不进入 Repository/Audit。
7. Injection 只能使用 Binding 声明的位置、名称和格式；第一切片优先 Header。
8. 禁止无条件 Token Passthrough，禁止把 Inbound Authorization 复制给 Upstream。
9. Credential 错误返回稳定安全 Code，不暴露 Reference、Provider Error 或 Secret。

## Binding Specificity

推荐从具体到通用选择：

```text
Principal + Tool
Tenant + Tool
Principal + Upstream
Tenant + Upstream
```

精确冲突时拒绝调用，不能依赖数据库返回顺序。

## Rejected Alternatives

- ToolBinding 直接保存 API Key；
- Secret Value 进入 RequestContext；
- 日志/Audit 保存注入后的 Header；
- 把 Vault/AWS/Azure SDK 类型暴露给 Domain；
- 默认透传 MCP Client Credential。

## Consequences

- Local 开发可先实现 Environment Provider；
- 外部 Secret Store 只需新增 Adapter；
- Executor 测试必须证明 Secret 不进入 Log/Audit/Error；
- Query Injection 的 URL/日志风险高于 Header，需要独立安全测试。

## Implementation Confirmation

S3-3 已用 InMemory Resolver 和 Environment Provider 验证本 ADR：

- `Agent Service Principal > Tenant`，同一 Subject 下 `Tool > Upstream Wildcard`；
- 同特异性多条 Binding 直接返回 `credential_binding_conflict`；
- Upstream `auth_scheme != none` 时必须成功解析 Credential，否则 Fail Closed；
- Policy ALLOW 后才解析 Secret；DENY 不调用 Resolver/Provider；
- Execution 只保存 `credential_binding_id`，临时 `SecretValue` 只传给 Executor；
- Header 与 Query 均由受信 Binding 在参数映射后覆盖注入。

Environment Provider 是本地开发 Adapter，不代表生产 Secret Store 决策；CredentialBinding
PostgreSQL 持久化也不在本阶段范围内。

ADR-0019 进一步冻结：员工个人 Token、员工 Role 和 On-Behalf-Of Credential 不进入当前主线；需要员工级
授权的 Upstream 由上层 Agent 服务或原业务系统负责。
