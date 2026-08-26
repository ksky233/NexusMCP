# ADR-0012｜Retry、Idempotency 与 ExecutionAttempt

> 状态：Accepted  
> 日期：2026-08-26

## Context

Agent、MCP Host 和网络都可能重复发起调用；一次调用内部也可能遇到 503、Network Error 或 Timeout。
如果把每次 Retry 当成新的 ToolExecution，Approval、Audit 和业务意图会被重复；如果对非幂等写盲目
Retry，又可能产生重复工单、扣款或库存预留。

NexusMCP 当前不持久化完整 Result，因此不能假装能够对完成后的重复请求透明回放原响应。

## Decision

1. `ToolExecution` 表示一次业务意图，`ExecutionAttempt` 表示一次 Upstream 传输尝试。
2. Retry 不重新执行 Policy、不重复消费 Approval、不重新选择 Credential，也不创建第二条 Execution。
3. Attempt 在请求前持久化为 Running，请求后持久化 Succeeded/Failed/Unknown/Cancelled。
4. Read-Only 对有限 Network/5xx/Timeout 执行有界指数 Backoff Retry。
5. Idempotent Write 只有提供可信 Idempotency Key 时才执行和 Retry。
6. Non-Idempotent/Unknown Write 的 After-Send Timeout 不 Retry，Execution 进入 UNKNOWN。
7. Idempotency Key 从 MCP Request `_meta["com.nexusmcp/idempotencyKey"]` 读取，不进入 Tool Arguments
   或 Arguments Digest；Key 只允许 1～128 位安全 ASCII Token 字符。
8. Approval 同时绑定 Idempotency Key，恢复调用不能替换 Key。
9. 数据库唯一 Scope 为 Tenant + Principal + ToolVersion + Idempotency Key。
10. 同 Key 不同 Arguments Digest 返回 `idempotency_conflict`；Running、Succeeded、Unknown、Failed
    分别返回稳定状态错误和 Existing Execution ID，不再次调用 Upstream。
11. Succeeded Duplicate 当前不回放业务 Result，因为 Result 不持久化；调用方获得原 Execution ID。
12. 只开放 GET 与 SideEffect=`idempotent_write` 的 PUT；POST 和非幂等写继续拒绝。

## Rejected Alternatives

- 每个 Retry 创建新的 ToolExecution；
- 所有 Exception 固定重试三次；
- 自动给每次调用生成随机 Idempotency Key；
- 把 Idempotency Key 放入模型可修改的 Tool Arguments；
- 相同 Key 配合不同 Arguments 继续执行；
- 为了透明 Replay 无边界保存完整 Result；
- 当前阶段开放所有 POST/DELETE 写操作；
- 宣称 Gateway + Upstream 已实现 Exactly Once。

## Consequences

- PostgreSQL 新增 ExecutionAttempt 表和 Idempotency Partial Unique Index；
- Concurrent Claim 依靠数据库唯一约束 Fail Closed；
- Duplicate Completed 返回 Existing Execution ID 而不是原业务 Result；
- Retry 总时间预算、Jitter、跨进程继续 Retry 与 Result Cache 留待后续证据；
- Upstream 必须真实支持 Idempotency-Key，Tool 标记本身不能把非幂等 API 变安全；
- 当前 Inventory PUT 是唯一写执行白名单切片。

## Verification

- Read-Only 与 Idempotent Write 前两次失败、第三次成功，产生一个 Execution/三个 Attempt；
- Backoff 为确定性的指数序列；
- Non-Idempotent After-Send Timeout 只有一次 Attempt 并进入 UNKNOWN；
- PostgreSQL Concurrent Claim 只创建一条 Execution；
- 同 Key 同参数不重复调用 Upstream，同 Key不同参数返回 Conflict；
- 三次 PUT Attempt 使用同一个受信 Idempotency-Key；
- 客户端伪造同名 Header 被可信 Key 覆盖；
- POST 即使携带 Key 仍被拒绝。
