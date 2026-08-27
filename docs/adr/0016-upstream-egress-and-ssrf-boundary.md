# ADR-0016｜Upstream Egress 与 SSRF 防护边界

> 状态：Accepted
> 日期：2026-08-27

## Context

NexusMCP 的职责是代表 Agent 调用企业 HTTP/OpenAPI 服务，这些 Upstream 很可能位于 RFC 1918 私网。
因此“禁止所有 Private IP”会直接破坏核心业务；但完全信任注册的 Endpoint，又会让 NexusMCP 成为访问
本机服务、云 Metadata、其他租户网段或任意外部目标的 SSRF 跳板。

这里讨论的是出站边界：

```text
Agent → NexusMCP → Upstream API
        Inbound    Egress/SSRF Boundary
```

谁可以访问 NexusMCP 属于 Inbound Authentication、反向代理和防火墙；本 ADR 只决定 NexusMCP 可以访问
哪些 Upstream。

OWASP 将“只能请求已识别、可信应用”的场景归为适合 Allowlist 的 SSRF 防护模型，并建议关闭 Redirect、
校验域名及其全部 A/AAAA 地址。NexusMCP 的企业 Catalog 正好属于这一模型。

## Decision

### 1. 第一版 Policy 所有权

- Egress Policy 是平台部署级配置，由 Platform/Network Security 管理；
- 普通 Agent、用户和 Tenant 业务管理员不能修改；
- 第一版不进入数据库、Control Plane UI、动态热更新或租户自助配置；
- Production 使用 Fail-Closed：空 Allowlist 不能注册或执行任何 HTTP Upstream。

第一版配置概念：

```text
allowed_hosts   = 精确可信 Hostname
allowed_cidrs   = 精确批准的 IPv4/IPv6 Network
allowed_ports   = 允许的目标 Port
```

Hostname 使用规范化后的精确匹配，不支持任意正则或宽泛字符串包含。Public SaaS 也必须显式加入 Host
Allowlist，不提供“允许所有 Public Internet”的总开关。

### 2. 两阶段校验

```text
Register / Update Upstream
→ URL Parse
→ Scheme/Credential/Host/Port Check
→ Host/CIDR Allowlist
→ Resolve all A + AAAA
→ Address Policy
→ Persist

tools/call
→ Re-parse persisted Endpoint
→ Re-resolve all A + AAAA
→ Re-apply same Policy
→ HTTP Request
```

只在注册时检查不足以覆盖 DNS、网络和配置变化；执行前必须复检。DNS 解析失败、返回空结果、任意一个地址
不符合 Policy 时全部 Fail-Closed。

### 3. Hard Deny

Hard Deny 优先级高于普通 Host/CIDR Allowlist：

- IPv4/IPv6 Link-Local；
- Unspecified；
- Multicast；
- 已知 Cloud Metadata 地址与 Hostname；
- URL 中的 Userinfo/Credential；
- 非 HTTP/HTTPS Scheme；
- Redirect Target（第一版继续 `follow_redirects=False`）。

Loopback 在 Production 永久拒绝；Development/Test 只能通过显式 Local Demo 开关允许
`localhost/127.0.0.1/::1`，不能从开发默认值静默继承到 Production。

Private Address 不是 Hard Deny：只有同时匹配 `allowed_hosts` 或 `allowed_cidrs` 才能访问，从而支持经过批准
的企业内部 API。

### 4. DNS 规则

- 域名必须先匹配 `allowed_hosts`；
- 获取全部 A/AAAA Answer，不能只验证第一个；
- 每个解析地址都必须通过 Hard Deny 和 Allowlist；
- 混合返回 Allowed/Denied 地址时整体拒绝；
- 执行前重新解析，降低 DNS Rebinding 和漂移风险；
- DNS 查询结果和完整 Endpoint 不写入模型可见错误、Metric 或普通 Info Log。

### 5. 第一版残余风险

第一版“检查后再由 httpx 按 Hostname 建连”仍存在 DNS Check 与实际 Connect 之间的 TOCTOU 窗口，不等于
严格 DNS Pinning。完整强化需要：

- 将已验证 IP 固定到实际 Socket Connection；
- HTTPS 时保持原 Host/SNI 与证书校验；
- Network Firewall/Egress Proxy 二次限制；
- 对 Allowlist DNS 做持续监控。

这些能力需要自定义 Transport 或受控 Egress Proxy，超出第一版 S5-2 范围。ADR 必须公开这一残余风险，
不能把执行前复检描述为“彻底解决 DNS Rebinding”。

### 6. 后续动态管理条件

只有出现多 Tenant 自助接入或无需重启的生产需求时，才把 Egress Policy 迁入 Control Plane。届时必须同时
具备：

- Platform Security 专属权限；
- 版本化 Policy Snapshot；
- 变更审批与 Audit；
- Tenant Scope；
- Rollback；
- 配置生效与执行 Trace 关联。

## Rejected Alternatives

- 禁止所有 Private IP：与企业内部 API 核心场景冲突；
- 只阻止 Private IP、允许全部公网：仍可访问任意外部目标并外带数据；
- 只比较 Hostname、不解析 A/AAAA：无法发现允许域名指向特殊或越权地址；
- 只在 Registry 注册时检查：DNS/Policy 漂移后执行链仍可能访问危险目标；
- 第一版建设动态 Policy 管理后台：增加权限、审批、缓存一致性和回滚复杂度，当前没有真实需求；
- 宣称执行前复检等同 DNS Pinning：忽略检查与实际连接之间的解析竞态。

## Consequences

- Demo/Test 必须显式配置 Local Endpoint 例外；
- Production 未配置 Allowlist 时 HTTP Tool Fail-Closed；
- Registry 与 Executor 共享同一个 `UpstreamEndpointPolicy` Port，但分别映射为注册错误和安全执行错误；
- DNS 解析成为注册/执行的可预期失败点，需要稳定 Error Code、Metric 与 Failure Injection；
- 运维需要维护可信 Host/CIDR/Port，且网络层仍应配置 Firewall 或 Egress Proxy；
- 第一版静态配置简单可审计，但变更需要部署流程。

## Verification

- 允许显式批准的企业私网 Host/CIDR；
- 拒绝未批准的 Private/Public Target；
- 拒绝 `file/gopher/ftp`、URL Credential 与非法 Port；
- 拒绝 IPv4/IPv6 Link-Local、Unspecified、Multicast、Metadata Target；
- 拒绝 A/AAAA 混合解析中的任意 Denied Address；
- 注册通过后，执行时 DNS 变更到 Denied Address 仍被拒绝；
- Redirect 不跟随；
- Development Local Demo 可显式启用，Production 不能启用；
- 安全错误、Log、Trace、Audit 不包含完整 Endpoint、DNS Answer 或 Credential。

## References

- [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
- [RFC 6890｜Special-Purpose Address Registries](https://www.rfc-editor.org/info/rfc6890/)

## Implementation Confirmation

S5-2 已实现：

- Static Host/CIDR/Port Allowlist 与 System DNS Resolver；
- Metadata/Link-Local/Unspecified/Multicast/Reserved Hard Deny；
- Registry Register/Update、CallTool Secret 前置、Executor Connect 前复检；
- Production Fail-Closed 与显式 Local Demo；
- A/AAAA Mixed Answer、DNS Change、Metadata E2E；
- Policy Golden Matrix 与 Security Evidence Manifest。

严格 DNS Pinning、Egress Proxy 和动态管理继续作为本 ADR 已声明的 Deferred Hardening。
