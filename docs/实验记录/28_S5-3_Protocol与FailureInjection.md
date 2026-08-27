# S5-3｜Protocol Compatibility 与 Failure Injection 验收

> 日期：2026-08-27
> 状态：完成

## 完成内容

- 15 条 Modern/Legacy Protocol Compatibility Matrix；
- Modern Raw JSON-RPC Parse/Method/Header/Version 拒绝测试；
- Modern Stateless 与 Legacy Stateful HTTP Session 对照；
- Legacy OTel Span Era 与 Fallback Counter；
- 14 条 Failure Injection Matrix；
- Protocol/Failure Evidence Manifest 防腐测试；
- 现有事务、Audit、Retry、Approval、Idempotency、Embedding、Egress 故障证据统一归档。

## 关键学习点

协议兼容测试应验证“同一业务在不同协议时代的可观察差异”，而不是建立两套业务实现。Modern 没有隐式
Session，Legacy 通过 SDK Session Manager 维护 Session；两者最终进入同一 Catalog、Policy 和 Execution。

Failure Injection 的价值不是异常数量，而是证明失败后的状态：是否回滚、是否重试、是否 Unknown、是否
消费 Approval、是否产生 Execution/Audit。只有状态断言才能成为工程证据。

## 验收结果

```text
280 passed
2 paid external skipped
Ruff passed
basedpyright 0 errors / 0 warnings
```

完整证据见
[S5-3 Protocol Compatibility 与 Failure Injection](../工程证据/03_S5-3_Protocol与FailureInjection.md)。
