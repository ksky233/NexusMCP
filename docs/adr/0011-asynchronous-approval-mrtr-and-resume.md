# ADR-0011｜异步 Approval、MRTR 与恢复

> 状态：Accepted  
> 日期：2026-08-26

## Context

Agent 发起 Tool Call 后，人工审批可能只需数秒，也可能需要另一位负责人等待数小时。NexusMCP 不能
让一次 HTTP Request、数据库事务、Secret Lease 或 Upstream Connection 原地等待。与此同时，审批
必须绑定原始调用且只能使用一次，Agent 自己声称“已经批准”不能成为可信授权事实。

Modern MCP `2026-07-28` 提供 `InputRequiredResult`、`inputResponses` 与 `requestState` 的 MRTR
能力；并非所有客户端或长审批流程都适合自动 MRTR Loop。

## Decision

1. Approval 是 PostgreSQL 持久化业务状态，不依赖 Transport Session。
2. Host 内短时确认使用 `InputRequiredResult` 内嵌 Elicitation；Host 收集用户决定后发起新一轮
   `tools/call`。
3. 长时间或不同审批人流程由 Control Plane Approve/Reject；Host 保存首轮返回的 opaque
   `requestState`，之后重新发起调用。
4. 第一轮请求创建 `PENDING` Approval 后立即返回，不持有数据库事务或 HTTP/Upstream 资源。
5. `requestState` 使用 SDK `RequestStateBoundary` 的 AES-GCM 保护，并绑定 Method、Tool、Arguments
   Digest、Audience 与 TTL；生产/Multi-Worker 使用共享 Key。
6. Approval 额外绑定 Tenant、Principal、Tool、Tool Version、Arguments Digest 与 Policy Version。
7. 消费使用 PostgreSQL `SELECT ... FOR UPDATE`；只有 `APPROVED` 能原子转为 `CONSUMED`。
8. Policy 在恢复调用时重新评估；Approval Consume 成功后才解析 Credential。
9. MRTR Elicitation 表示当前可信 Host 的交互确认。要求职责分离的企业审批必须走具有独立身份的
   Control Plane/外部审批系统。
10. Legacy/不支持 MRTR 的客户端后续通过显式 Approval Resource 兼容，不复制长连接 Session。

## Rejected Alternatives

- 单次 `tools/call` 长时间阻塞直到人类决定；
- 只在 Agent Memory 中保存批准结果；
- Agent 在 Arguments 中自行声明 `approved=true`；
- Approval 批准后可无限重复调用；
- 只使用 MRTR，不保留持久化异步恢复路径；
- 将原始 Arguments 或 `requestState` 明文写入 Approval 表。

## Consequences

- Host 必须在异步路径中保存 opaque `requestState` 与 `approval_id`；
- 开发/单进程可使用 Ephemeral Key，重启恢复和多实例必须配置共享 Key；
- 本地 `/admin` 仅是学习阶段 Control Plane，生产前必须接入真实 Admin AuthN/AuthZ；
- Approval 页面当前只展示 Tool/Version/Arguments Digest，安全的参数预览需要单独设计；
- S3-4 的 Approval Consume 与 InMemory Execution 尚非同一事务；进程在两者之间失败会安全停止但需
  新审批，S3-5 持久化 Execution 时合并该短事务；
- 不支持 MRTR 的客户端仍需要后续 Compatibility Adapter。

## Verification

- Modern Client Elicitation Callback 完成两轮 `tools/call`；
- 第一轮应用停止后，使用共享 Key 和 PostgreSQL Approval 在新应用实例恢复；
- 篡改 `requestState` 或 Arguments 被协议边界拒绝；
- Host Decline 产生 `REJECTED` 且不创建 Execution；
- 两个 PostgreSQL 并发消费者只有一个成功；
- 已消费 Approval Replay 返回 `approval_already_consumed`。
