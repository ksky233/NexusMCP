# ADR-0017｜延后 Remote MCP，优先 Web Control Plane

> 状态：Accepted
> 日期：2026-08-27

## Context

NexusMCP 的当前可运行主链是：

```text
Enterprise HTTP/OpenAPI
→ Import / Review / Version / Publish
→ Governed MCP Tool
→ Agent
```

早期架构为 `UpstreamServiceType.REMOTE_MCP` 和 `ToolBindingType.REMOTE_MCP` 预留了枚举，并在部分规划
文档中把 Remote MCP Server 描述为第二类正式接入来源。但到 S5 收口时，项目没有找到足够强、足够具体的
当前企业场景来证明应该实现 Remote MCP Federation/Proxy。

讨论中区分出三类完全不同的产品：

1. 企业 HTTP/OpenAPI Tool Governance；
2. 开发者个人 MCP 管理/Marketplace；
3. 透明 MCP Relay/Enterprise MCP Edge。

它们的用户、强制力、身份、隐私、协议完整性和数据模型都不同，不能因为技术上都叫 MCP 就合并进同一
主线。

## Decision

### 1. 当前正式产品边界

当前 NexusMCP 只承诺：

> 将企业拥有的 HTTP/OpenAPI 服务转化为受治理 MCP Tool，并统一管理发现、Policy、Approval、
> Credential、Execution、Audit、Search 与 Telemetry。

Remote MCP Connector/Federation 状态改为 `Deferred`，不进入当前 S6 前的开发主线。

### 2. 不治理开发者个人 MCP

不把以下目标纳入 NexusMCP：

- 强制员工本地 Codex/Cursor/VS Code 的所有 MCP 流量经过 NexusMCP；
- 统计个人 MCP 调用量来量化“VibeCoding 程度”；
- 管理 Context7 等个人开发辅助 MCP；
- 通过 NexusMCP 监控员工个人 Prompt、代码和开发行为。

原因：

- 本地客户端可以直接配置 Remote/stdio MCP，NexusMCP 缺少自然强制边界；
- MCP 调用量不能代表开发效率或 AI 使用程度；
- 完整强制需要 MDM、IDE Policy、Network Egress 与组织隐私政策，属于 Enterprise Developer Platform；
- 代理个人工具会引入隐私、OAuth/User Context 和兼容成本，偏离企业业务 Tool Governance。

企业未来如需“批准的开发 MCP 目录”，更适合做配置 Registry/Marketplace，而不是强制流量 Proxy。

### 3. 不实现透明 MCP Relay

“只转发 MCP 并注入 Trace”不是当前功能：

- MCP 不只有 `tools/list/call`，还包含 Resources、Prompts、Sampling、Elicitation、Subscription、Progress、
  Cancellation 和不同 Session Era；
- 真正透明需要保留所有 Content Block、Callback、Streaming、Session 和 Capability Negotiation；
- 只支持 Tool/Text 会丢失远端特性；
- 只增加一跳 Trace 的收益不足以支撑独立 MCP-Aware Reverse Proxy 的复杂度。

如果未来需要该能力，应作为独立的 `MCP Edge/Relay` 产品问题重新立项，而不是伪装成现有 Connector。

### 4. Remote MCP 触发条件

只有出现明确组织级 Upstream 场景后重新评估，建议至少满足以下三项：

- 企业拥有两个以上正式 Remote MCP Server；
- 使用方是企业托管 Agent，而非员工个人 IDE；
- MCP 是 Upstream 团队正式维护的集成接口；
- 没有更稳定、治理成本更低的 HTTP/OpenAPI；
- 存在统一 Credential、Policy、Audit 的明确需求；
- 多个企业 Agent 需要复用同一 Remote MCP；
- 能明确第一版所需 Capability，而不是声称全协议透明。

触发后先做一条 Modern Streamable HTTP、Tools-only、Text/Structured Content 的纵向实验，再决定是否进入
正式产品。

### 5. 预留枚举的处理

- Domain Enum 暂时保留为历史扩展点，不代表可用能力；
- Admin API/UI 不应向用户提供可注册但无法执行的 `remote_mcp` 选项；
- 在正式 Connector 实现前，公开接口应拒绝该 Service/Binding Type；
- README、Architecture 和 Demo 不声称支持 Remote MCP；
- 后续如果长期没有触发场景，可以通过独立 ADR 删除预留枚举。

### 6. Skill 与 Tool 边界

```text
Skill
= 告诉 Agent 按什么流程、顺序和规则工作

MCP Tool
= 在流程中读取实时数据或执行操作
```

NexusMCP 继续治理可执行 Tool，不扩展为企业 Skill Registry。内部业务流程理解可以由 Agent Skill 调用
NexusMCP Tool 完成。

### 7. Web Control Plane 优先

S6 前置投入优先用于 Web UI，因为现有 Local Admin API 已有真实 Control Plane 主链：

- Upstream；
- OpenAPI Import；
- Review/Publish；
- Catalog Search；
- Approval；
- Execution/Audit 读取接缝。

Web UI 只是现有业务的展示和操作层，不改变核心产品边界，能够显著提高 Demo 和面试可理解性。

第一版必须明确标注 `Local Development Admin`，不制作虚假 Production Login；Production Admin
OIDC/AuthN/AuthZ 仍为后续能力。

## Rejected Alternatives

- 为了声称“支持任意 MCP”立即实现 Remote MCP Proxy；
- 用 MCP 调用量评估开发者 AI 编码程度；
- 强制所有个人 IDE MCP 经过 NexusMCP；
- 只代理 `tools/list/call` 却声称透明 MCP Relay；
- 因为 Domain 已有预留 Enum 就反向寻找业务理由；
- 在 Web UI 中暴露尚不可执行的 Remote MCP 注册选项。

## Consequences

- 项目叙事更聚焦，也不再过度声称当前能力；
- 当前核心 Demo 继续围绕三个 HTTP/OpenAPI Upstream；
- Remote MCP 保留为有业务触发条件的 Future Connector；
- S6 前置工作转为 Admin Query API + Web UI MVP；
- 现有规划和业务词汇中 Remote MCP 章节标记为历史预留/Deferred；
- Admin API 当前接受 `remote_mcp` 但无法执行的问题进入 Web UI 前的 W0 修正项。

## Verification

- README 和公开架构只描述当前 HTTP/OpenAPI 能力；
- `/admin` 在 Connector 未实现前拒绝 Remote MCP 注册；
- Web UI 不展示 Remote MCP；
- Demo/Quick Start 不依赖 Remote MCP；
- Future Roadmap 清楚列出 Remote MCP 的触发条件；
- 面试时能解释“为什么不做”，而不是把未实现能力包装成 Feature。

## References

- [MCP Server Features](https://modelcontextprotocol.io/specification/2025-06-18/server/index)
- [MCP Sampling](https://modelcontextprotocol.io/specification/2025-11-25/client/sampling)
- [Official Python SDK Client](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/client/index.md)
- [Context7 Client Configuration](https://context7.com/docs/resources/all-clients)
