# S5-2｜Security 与 Policy Regression 验收

> 日期：2026-08-27
> 状态：完成

## 完成内容

- ADR-0016 Static Egress Policy 落地；
- Host/CIDR/Port Allowlist；
- Metadata 与特殊地址 Hard Deny；
- 全 A/AAAA 校验、混合 Answer Fail-Closed、执行时 DNS 复检；
- Development/Test 显式 Local Demo 与 Production Fail-Closed；
- Registry 持久化前校验；
- CallTool 在 Secret/Execution Plan 前校验；
- Httpx Executor 在 Connect 前复检；
- 10 条 Policy Golden Case；
- 15 条 Security Evidence Manifest；
- Metadata Endpoint 正式 MCP E2E。

## 关键学习点

企业内部 API 使用 Private IP 是正常业务需求，因此 SSRF 防护不能等于“禁用私网”。真正的边界是：目标
必须由 Platform Security 显式批准，同时 Metadata/Link-Local 等地址不可被普通 Allowlist 覆盖。

网络校验不能放进数据库写事务。Update Upstream 先读取不可变 Service Type，退出事务后执行 DNS/Policy，
通过后再进入短写事务锁定和更新，避免数据库行锁跨越网络调用。

危险 Endpoint 必须早于 Secret 解析被拒绝；Executor 再复检是为了缩短 DNS Check 与 Connect 的时间窗口，
但仍不等于严格 DNS Pinning。

## 验收结果

```text
276 passed
2 paid external skipped
Ruff passed
basedpyright 0 errors / 0 warnings
```

完整证据见
[S5-2 Security 与 Policy Regression](../工程证据/02_S5-2_Security与PolicyRegression.md)。
