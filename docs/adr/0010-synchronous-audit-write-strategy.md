# ADR-0010｜同库同步 Audit 写入策略

> 状态：Accepted  
> 日期：2026-08-26

## Context

Tool Call 的 Policy Decision、Approval、Execution Terminal State 与 Audit Evidence 必须保持可解释的
一致性。如果先提交业务状态再异步写 Audit，进程崩溃可能留下“执行存在但审计缺失”；如果在数据库
事务内调用外部 SIEM/消息系统，又会把网络不稳定性引入核心执行事务。

NexusMCP 当前已经使用 PostgreSQL 保存治理状态，规模尚不需要独立 Audit Service。

## Decision

1. 核心 Audit Event 与 Approval、ToolExecution 保存在同一 PostgreSQL。
2. Audit 表只提供 Append，不提供 Update/Delete 业务 Port。
3. 创建 `PENDING Approval` 与 `APPROVAL_REQUIRED Audit` 在同一短事务。
4. Approve/Reject 与对应 `APPROVAL_DECISION Audit` 在同一短事务。
5. Consume Approval、创建 Running Execution、追加 `ALLOWED Audit` 在同一短事务。
6. 保存 Succeeded/Failed/Unknown/Cancelled 终态与 Terminal Audit 在同一短事务。
7. Audit 失败时对应本地状态事务回滚，不能静默丢失证据。
8. Audit 不保存完整 Arguments、Result、Secret、Token、Authorization 或 Upstream Sensitive Body。
9. Upstream HTTP/MCP 调用始终位于两个本地短事务之间，数据库事务不跨网络。
10. 向外部 SIEM/Event Bus 投递时新增 Transactional Outbox；本阶段不在事务内调用外部 Sink。

## Rejected Alternatives

- 只写普通应用日志，不建立 Audit Domain；
- 先提交 Execution，后台 Best-Effort 写 Audit；
- 在 Execution 表中不断追加 JSON Audit History；
- 数据库事务内同步调用外部 SIEM；
- Audit 保存完整请求参数和上游响应；
- 宣称本地事务可以保证 Upstream Side Effect Exactly Once。

## Consequences

- 本地治理状态和证据具有清晰原子性；
- Audit 写入故障会 Fail Closed，增加少量调用延迟；
- Audit 表增长、Partition/Retention、Outbox 和外部检索留到容量证据出现后；
- Authentication Failure 等发生在可信 Actor 建立之前的事件仍主要进入安全日志，后续需要独立
  Security Audit 接缝；
- Approval Replay/Invalid RequestState 等拒绝事件当前由 MCP 日志记录，持久化拒绝审计覆盖可在
  S3 收口时扩展。

## Verification

- 故障 Audit Repository 使 Approval Consume 和 Execution Plan 一起回滚；
- PostgreSQL Execution 的 Running/Terminal 状态分别具有 ALLOWED/Terminal Audit；
- Approval Create/Approve/Reject 具有原子 Audit；
- Unknown 与 Cancelled 终态可持久化；
- Audit Domain 拒绝敏感 Metadata Key；
- MCP Credential E2E 证明 Secret 不进入 Execution、Audit 或 Log。
