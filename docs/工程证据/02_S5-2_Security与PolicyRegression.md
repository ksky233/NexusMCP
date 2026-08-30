# S5-2｜Security 与 Policy Regression 证据

> 日期：2026-08-27
> 状态：完成

## 1. Egress/SSRF 实现

正式边界遵循 ADR-0016：

```text
Register/Update
→ URL + Host/CIDR/Port + DNS A/AAAA Policy
→ Persist

tools/call
→ Policy/Approval
→ Egress Check
→ Credential Resolve
→ Execution Plan
→ Executor Egress Recheck
→ HTTP Connect (Redirect disabled)
```

实现组件：

- `UpstreamEndpointPolicy` Port；
- `SystemHostResolver`；
- `StaticUpstreamEndpointPolicy`；
- Deployment Settings：Enabled、Allowed Hosts/CIDRs/Ports、Local Demo；
- Registry Register/Update 接缝；
- CallTool Secret 前置接缝；
- HttpxToolExecutor Connect 前复检。

Hard Deny：Cloud Metadata、IPv4/IPv6 Link-Local、Unspecified、Multicast、Reserved、URL Credential、
非法 Scheme/Port/Fragment。Loopback 只允许 Development/Test 显式 Local Demo；Production 配置校验强制
启用 Policy、禁止 Local Demo，并在空 Allowlist 时拒绝启动。

## 2. Policy Golden Matrix

`evals/policy/policy_cases.json` 固定 10 条 Case：

- Default DENY；
- Tenant ALLOW；
- Role > Tenant；
- Agent Service Principal > Tenant；
- Tool-specific > Global；
- 同特异性按 Priority；
- 同 Priority：`DENY > REQUIRE_APPROVAL > ALLOW`；
- Disabled Policy 忽略；
- Cross-Tenant Policy 忽略。

Golden Matrix 只回归现有 `RuleBasedPolicyEvaluator`，没有引入 Rego、DSL 或未证明的 Condition
Expression。Side Effect 目前是 Policy Input 和 Tool Binding 事实，不是通用 Policy Condition 语言。

## 3. Security Evidence Manifest

`evals/security/security_cases.json` 汇总 15 条自动化证据，覆盖：

- SSRF/Egress；
- Identity/Policy；
- Tenant Boundary；
- Secret/Log/Trace；
- Approval Replay/Snapshot Tamper；
- Idempotency Duplicate/Conflict。

Manifest 的每个 Pytest Node 都由防腐测试确认文件与测试函数真实存在，避免报告长期指向已删除证据。

## 4. 关键失败行为

- Registry Endpoint 不安全：`unsafe_upstream_endpoint`，不持久化；
- 执行时 Endpoint 不安全：不解析 Secret、不创建 Execution、不发送 HTTP；
- Executor 复检失败：归一化为 Authorization 类 `unsafe_upstream_endpoint`；
- DNS 任意 A/AAAA Answer Hard Deny：整个 Target Fail-Closed；
- DNS 注册后改变到 Metadata：执行复检拒绝；
- Production 未启用 Egress Policy、空 Allowlist 或 Local Demo：Settings 启动失败。

模型可见错误只包含稳定 Safe Message；Log/Trace/Audit 不保存完整 Endpoint、DNS Answer、Query、Arguments
或 Credential。

## 5. 验收

- Security Test：14 项通过；
- Egress/Registry/CallTool/Executor/Config 相关回归：53 项通过；
- Metadata Endpoint 正式 MCP + PostgreSQL E2E 通过；
- 全量：276 Passed、2 个付费 External Skip；
- Ruff Lint/Format、basedpyright 0/0；
- PostgreSQL 测试只使用 `nexusmcp_test`。

## 6. 已知限制

- DNS 复检不是严格 Socket Pinning，仍有 Check/Connect TOCTOU；
- 第一版 Policy 是部署静态配置，无 UI、热更新、审批和 Tenant 自助；
- Application Layer 不能替代 Network Firewall/Egress Proxy；
- Allowed Host 的 DNS 持续监控尚未实现；
- Policy Condition DSL、Rate Limit、生产 Agent Service Identity 和 Admin SSO 不属于 S5-2。

## 7. 下一步

进入 `S5-3｜Protocol Compatibility 与 Failure Injection`：把 Modern/Legacy、未知方法、非法 JSON-RPC、
Session、Approval、Trace Era 等行为固定为机器矩阵，并补 DB/Audit/Embedding/Upstream 故障注入报告。
