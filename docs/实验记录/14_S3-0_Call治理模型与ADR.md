# S3-0｜Call/Policy/Credential/Execution 模型与 ADR 验收

> 2026-08-30 边界修订：本文 Principal/Role 模型保留为治理机制实验记录；ADR-0019 已将产品主线调用者
> 收窄为 Agent Service Principal，不建设员工身份、角色或会话系统。

> 日期：2026-08-26  
> 范围：Identity、Call、Policy、Credential、Approval、Execution、Audit Domain/Port，
> ADR-0005/0006/0007，S3 编排与事务边界

## 1. 目标

S3-0 不执行真实 Tool，而是先冻结任何 `tools/call` 实现都不能违反的安全模型：

```text
Principal
→ Tool Resolution
→ Arguments Validation/Digest
→ Policy
→ Approval
→ Credential Reference/Injection
→ Execution
→ Error/Retry/Unknown
→ Audit
```

本阶段不建新表、不发送 HTTP、不读取真实 Secret。

## 2. 新增模型

| Context | 模型 |
|---|---|
| Identity | `InternalPrincipal`、`PrincipalType` |
| Policy | `PolicyEvaluationInput`、`PolicyDecision`、`ALLOW/DENY/REQUIRE_APPROVAL` |
| Credentials | `SecretReference`、`SecretValue`、`CredentialBinding`、`ResolvedCredential` |
| Approval | `ApprovalRequest`、`pending/approved/rejected/expired/consumed` |
| Execution | `CallToolCommand`、`ResolvedExecutableTool`、`ToolExecution`、Error Category、Retry |
| Audit | `AuditEvent`、Action、Outcome、Safe Metadata |

Arguments、Result、Token 和 Secret 不进入默认持久化模型；Approval/Execution/Audit 使用 Canonical JSON
Digest。

## 3. 新增 Port

```text
PolicyEvaluator
CredentialBindingResolver
CredentialProvider
ApprovalRepository
ExecutableToolResolver
ToolExecutor
ToolExecutionRepository
AuditSink
```

Port 不暴露 MCP SDK、FastAPI、SQLAlchemy、httpx 或 Secret Store SDK。

## 4. 状态机证据

Approval：

```text
pending → approved → consumed
        → rejected
        → expired
```

消费重新验证 Principal、ToolVersion、Arguments Digest 和 Expiry，且只能一次。

Execution：

```text
planned → running → succeeded / failed / unknown / cancelled
planned ─────────→ cancelled
```

Unknown 与 Failed 分离，防止非幂等写在不确定状态下盲目 Retry。

## 5. Retry Matrix

单元测试固定：

- Read Only Network/5xx/Timeout → Retry；
- Idempotent Write + Key → Retry；
- Idempotent Write 无 Key → Do Not Retry；
- Non-Idempotent After-Send Timeout → Require Reconciliation；
- Validation/Auth/AuthZ/Approval/Credential/4xx → Do Not Retry。

具体次数、Backoff/Jitter 留给 S3 Executor 实测。

## 6. Secret 安全证据

- `SecretReference` 拆分 Provider 与 Opaque Reference；
- `SecretValue.__str__/__repr__` 永远脱敏；
- `reveal()` 只留给最终 Injection Adapter；
- Credential Binding 保存 Scope/Injection Metadata，不保存 Value；
- AuditEvent Schema 没有 Arguments/Result/Secret 字段。

## 7. ADR

- [ADR-0005｜Identity 与 Trust Boundary](../adr/0005-identity-trust-boundary.md)
- [ADR-0006｜Credential Reference 与 Egress Injection](../adr/0006-credential-reference-and-injection.md)
- [ADR-0007｜Side Effect、Retry 与 Unknown Execution Outcome](../adr/0007-side-effect-retry-and-unknown-outcome.md)

仍 Deferred：Policy DSL、Approval MRTR/REST、Audit Outbox、Secret Store 产品、Retry 参数。

## 8. 代码位置

```text
src/nexusmcp/modules/identity/domain.py
src/nexusmcp/modules/policy/domain.py
src/nexusmcp/modules/policy/ports.py
src/nexusmcp/modules/credentials/domain.py
src/nexusmcp/modules/credentials/ports.py
src/nexusmcp/modules/approval/domain.py
src/nexusmcp/modules/approval/ports.py
src/nexusmcp/modules/execution/domain.py
src/nexusmcp/modules/execution/ports.py
src/nexusmcp/modules/audit/domain.py
src/nexusmcp/modules/audit/ports.py
src/nexusmcp/shared/digests.py
```

## 9. 下一步

进入 `S3-1｜Read-Only HTTP tools/call`：

1. Resolve `directory.get_employee` Published Version/Binding；
2. JSON Schema Arguments Validation；
3. Static ALLOW Policy；
4. Create/Finish InMemory Execution Record；
5. HTTP GET 参数映射、Timeout/Cancel；
6. Result/Error Normalize；
7. MCP `tools/call` Contract/E2E；
8. 不接真实 Credential/Approval/写 Tool。

以上内容已在 [S3-1 Read-Only HTTP tools/call](./15_S3-1_ReadOnlyHTTPToolsCall.md) 完成。
