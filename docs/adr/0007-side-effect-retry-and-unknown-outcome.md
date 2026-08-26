# ADR-0007｜Side Effect、Retry 与 Unknown Execution Outcome

> 状态：Accepted  
> 日期：2026-08-26

## Context

网络 Timeout 不一定代表 Upstream 未执行。对库存预留、工单创建等非幂等 Tool 盲目 Retry 可能重复产生
真实副作用，因此普通成功/失败二态不足以描述 Gateway Execution。

## Decision

1. ToolVersion 必须声明 `read_only/idempotent_write/non_idempotent_write/unknown`。
2. Execution 使用 `planned/running/succeeded/failed/unknown/cancelled` 状态机。
3. 在发起外部调用前持久化 Execution Plan/Arguments Digest。
4. DB Transaction 不跨越 Upstream HTTP/MCP。
5. 区分 `timeout_before_send` 与 `timeout_after_send`。
6. Non-Idempotent/Unknown 在 After-Send Timeout 时进入 `unknown`，要求 Reconciliation，不自动 Retry。
7. Idempotent Write 只有具备明确 Idempotency Key/Upstream Contract 时才允许 Retry。
8. Read Only 可对有限 Network/5xx/Timeout 使用有界 Retry。
9. Validation/Auth/AuthZ/Approval/Credential/4xx 不 Retry。
10. Cancel 必须向 Executor 传播；无法确认结果时仍可落为 Unknown。

## Idempotency Scope

第一版建议使用：

```text
tenant_id
+ principal_id
+ tool_version_id
+ idempotency_key
```

同 Key 但 Arguments Digest 不同必须冲突，不能复用旧结果。

## Rejected Alternatives

- 所有 Exception 自动 Retry；
- 只根据 HTTP Method 推断副作用；
- Timeout 一律标记 Failed；
- 非幂等 Tool 使用通用三次重试；
- 不记录 Execution，只依赖普通日志推断结果。

## Consequences

- Connector 必须报告请求是否可能已经发送；
- Execution Store 需要 Unknown/Reconciliation 查询；
- Approval/Idempotency 必须绑定 Arguments Digest；
- Retry 参数和 Backoff 实现留给真实 Executor Benchmark。
