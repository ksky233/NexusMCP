# NexusMCP 核心业务主链与 Java 迁移评估

> 状态：初步确认，作为后续领域建模与迁移设计的输入
> 日期：2026-08-24
> 范围：项目定位、API → MCP 主链、协议方向、Java 旧实现评估、迁移边界
> 不在本文冻结：最终目录、数据库表结构、Python SDK 精确版本与 ASGI 接入细节
> 后续决策更新：ADR-0017 已延后 Remote MCP；本文相关章节只保留早期扩展分析，不代表当前能力或主线。

## 1. 文档结论

NexusMCP 的第一核心业务是：

> 将企业内部 HTTP/OpenAPI 服务接入统一 Tool Catalog，转换并发布为 MCP Tool；Agent 调用 Tool 时，由 NexusMCP 完成解析、授权、凭据注入、上游执行、结果规范化和审计。

旧 Java 项目已经证明了最小技术链路可行：

```text
Gateway 配置
→ Tool 配置
→ HTTP Protocol + 字段 Mapping
→ tools/list 动态生成 Schema
→ tools/call 查询 Protocol
→ 调用企业 HTTP API
```

Java 实现与 NexusMCP 的核心方向一致，但它主要是数据库驱动的 MCP-to-HTTP Gateway 教学原型。NexusMCP 不逐行翻译 Java，而是在其转换内核之上补全：

- API 接入和 Tool 发布生命周期；
- 明确的 Tool Binding / Connector 模型；
- Modern MCP 与 Legacy 兼容；
- Identity、Policy、Credential、Approval；
- 安全 HTTP 执行；
- Trace、Metric、Audit；
- 可复现的 Contract、Golden、E2E 和 Security Test。

## 2. 产品定位

### 2.1 一句话定位

> NexusMCP 是企业 Tool 接入与治理平台：当前把内部 OpenAPI/HTTP API 转化为受治理 MCP Tool，通过 MCP
> 对 Agent 暴露，并在调用链上统一执行身份、策略、凭据、审批和审计。

### 2.2 当前来源与 Deferred 扩展

```text
企业 HTTP/OpenAPI ──→ HTTP Connector ─→ Tool Catalog ─→ NexusMCP Gateway ─→ Agent

Remote MCP Connector
→ ADR-0017 Deferred，仅在明确组织级 Upstream 场景后重新评估
```

优先级：

1. 第一条 MVP 主线是 `HTTP/OpenAPI → MCP Tool`；
2. 不治理开发者个人 MCP，不实现透明 Relay；
3. Future Remote MCP 如被真实场景触发，仍应复用 Catalog 与治理链路，但需独立 ADR/实验。

### 2.3 三层能力

| 层次 | 职责 | 只做到该层时的产品形态 |
|---|---|---|
| API → MCP Converter | 将 OpenAPI Operation 标准化为 MCP Tool Definition | OpenAPI 转换器 |
| MCP Gateway Runtime | 实现 `tools/list`、`tools/call` 和上游执行 | 可用 MCP Gateway |
| Enterprise Governance | Identity、Policy、Credential、Approval、Audit、Trace | NexusMCP 完整定位 |

第一条纵向切片必须同时覆盖前两层；治理能力沿同一调用链逐步加入，不单独建设一套与 API 映射脱节的平台。

## 3. 核心业务主链

### 3.1 Control Plane：API 接入与发布

```text
提交 OpenAPI Source
    ↓
安全校验与读取
    ↓
解析 Paths / Operations / Schema / Security
    ↓
生成 Imported Operations
    ↓
生成 Draft ToolDefinition + Draft ToolBinding
    ↓
检查名称冲突、不支持特性和安全风险
    ↓
Review
    ↓
Publish Tool Version
    ↓
进入 Tool Catalog
```

重要原则：

- Import 只产生 Draft，不直接暴露给 Agent；
- Tool Definition 与执行 Binding 分开；
- 发布时固定 Tool Schema、Binding 和安全策略的可追踪版本；
- OpenAPI 是接入输入，不是每次 `tools/call` 时重新解析的运行时依赖；
- Credential 只保存引用和绑定元数据，不进入 Tool Schema。

### 3.2 Data Plane：工具发现

```text
MCP tools/list / Tool Search
    ↓
解析 Protocol Version / Request Context
    ↓
识别 Tenant / Principal / Agent
    ↓
查询 Published Tool Catalog
    ↓
Visibility + Policy Filter
    ↓
返回当前调用者可见的 Tool Schema
```

`tools/list` 的结果不是数据库中所有 Tool 的无条件集合。缓存键和查询条件必须考虑身份、可见性、Policy Snapshot、Tool Version 和 Protocol Era。

### 3.3 Data Plane：工具调用

```text
MCP tools/call
    ↓
Tool Resolution
    ↓
解析 ToolDefinition + ToolBinding
    ↓
Policy Decision
    ├── DENY → 规范错误 + Audit
    ├── REQUIRE_APPROVAL → Approval Request
    └── ALLOW
          ↓
Credential Binding Resolution
          ↓
Executor Dispatch
    └── HTTP Connector → 企业 HTTP API
          ↓
Response Normalize / Redact
          ↓
ToolExecution + Trace + Metric + Audit
          ↓
MCP Result / Error
```

### 3.4 接入时编译，运行时执行

NexusMCP 不在每次 Tool Call 时临时解析 OpenAPI：

```text
接入/发布阶段
OpenAPI → Normalized Operation → ToolDefinition + ToolBinding

运行阶段
Tool Call → Published Definition/Binding → Executor
```

这样才能获得确定的版本、审核、安全策略、稳定性能和可回滚性。

## 4. 协议与 Python SDK v2 基线

### 4.1 已确认方向

NexusMCP 采用：

```text
Modern MCP 2026-07-28 作为主线
+
Legacy Handshake/Session 作为兼容路径
+
官方 Python MCP SDK v2 负责协议实现
```

三项方向已经确认，不再使用 Java 项目的协议版本作为新实现基线。

项目初始化时仍需通过实验锁定：

- Python MCP SDK 精确版本或 commit；
- SDK 支持的 Protocol Version 列表；
- Conformance Suite 版本；
- SDK 原生应用挂载还是自定义 ASGI Adapter；
- 已知 Expected Failures 和目标客户端兼容矩阵。

### 4.2 Modern 与 Legacy 的边界

| 维度 | Modern 主线 | Legacy 兼容 |
|---|---|---|
| 协议基线 | `2026-07-28` | `2025-11-25` 及更早版本 |
| 协商方式 | `server/discover` 或已知版本请求 | `initialize` Handshake |
| Transport Session | 不创建协议级 Session | 可使用 `Mcp-Session-Id` |
| 水平扩容 | 普通请求路由，不依赖 Session Stickiness | 有状态 Session 可能需要 Sticky Routing |
| 服务端补充输入 | Multi Round-Trip / Input Required | Elicitation 等旧版回调能力 |
| NexusMCP 用途 | 所有新业务和默认 Client | 旧客户端兼容测试与迁移期服务 |

Modern MCP 不使用协议级 Session，不代表业务不能有状态。以下状态仍应显式建模：

```text
approval_id
task_id
cursor
request_state
idempotency_key
tool_execution_id
```

它们属于业务对象或协议 Extension，不应隐藏在 HTTP Connection 或 Java 式 Session Map 中。

### 4.3 SDK v2 的职责边界

官方 Python MCP SDK v2 负责：

- MCP 类型和 JSON 编解码；
- Modern/Legacy 协议识别与协商；
- `server/discover` 与 Legacy `initialize`；
- Transport 和 Session 兼容细节；
- 标准错误和协议结果类型；
- SDK 已支持的 Multi Round-Trip、Subscription 等协议能力。

NexusMCP 自己负责：

- Registry、Catalog 和 Tool Binding；
- Identity、RequestContext 和 Trust Boundary；
- Policy、Credential、Approval；
- Tool Resolution 和 Executor Dispatch；
- HTTP/MCP Upstream 安全调用；
- Audit、Trace、Metric 和业务错误分类；
- SDK 类型与内部 Application Use Case 之间的 Adapter。

原则：

> SDK 负责“如何正确说 MCP”，NexusMCP 负责“哪个 Tool 可以被谁以什么凭据安全执行”。

NexusMCP 不重新手写完整 MCP Schema、协议协商和 Transport 状态机；只有在 SDK 无法提供 Gateway 所需的 Context、Routing 或 Auth Hook 时，才通过 ADR 讨论受控 Adapter，不直接修改 SDK 私有成员。

### 4.4 Java 协议代码的迁移位置

Java 项目的 `McpSchemaVO` 固定版本为 `2024-11-05`，Streamable 主链仍围绕：

```text
initialize
→ 创建 Session
→ 返回 Mcp-Session-Id
→ GET/POST/DELETE 管理 Session
→ Redis 同步 Session Metadata
```

该实现的迁移定位是：

| Java 资产 | NexusMCP 处理 |
|---|---|
| JSON-RPC Request/Response/Notification 样例 | 脱敏后转成 Golden Fixture |
| `initialize`、Session、SSE/Streamable 消息 | Legacy Compatibility Test |
| `tools/list`、`tools/call` 的业务意图 | 提取为协议无关 Application Use Case |
| 手写 `McpSchemaVO` | 不迁移，使用 SDK 类型 |
| Tree/Node Method Dispatch | 不迁移，由 SDK/Protocol Adapter 路由 |
| Redis Session 同步 | 不进入 Modern 主线，仅用于理解 Legacy 运维代价 |

核心业务 Use Case 不感知协议时代：

```text
Modern MCP Adapter ─┐
                    ├─→ ListVisibleTools / CallTool Use Case
Legacy MCP Adapter ─┘
```

Modern 与 Legacy 可以有不同 Transport Context 和响应映射，但必须复用同一 Catalog、Policy、Credential、Execution 和 Audit 逻辑。

### 4.5 S1 协议验收证据

在进入正式业务骨架前，必须通过可运行实验证明：

- Modern Client 可以执行 `server/discover`、`tools/list`、`tools/call`；
- Modern 请求不创建 `Mcp-Session-Id`；
- Legacy Client 可以执行 `initialize`、`tools/list`、`tools/call`；
- Auto Negotiation 能在 Modern 和 Legacy Server 之间选择正确路径；
- 同一业务 Tool 在两个协议时代得到一致业务结果；
- Unknown Method 和 Invalid Message 返回协议规范错误；
- Protocol Version/Era 进入 RequestContext、Trace、Metric 和 Audit；
- SDK 升级可以重复运行相同 Compatibility Matrix。

### 4.6 官方基线

- MCP `2026-07-28`：<https://blog.modelcontextprotocol.io/posts/2026-07-28/>
- MCP Python SDK：<https://github.com/modelcontextprotocol/python-sdk>
- SDK v2 What's New：<https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/whats-new.md>
- Protocol Versions：<https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/protocol-versions.md>
- Serving Legacy Clients：<https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/legacy-clients.md>

## 5. 初步核心模型

以下名称是领域讨论候选，不等同于最终数据库表名。

| 概念 | 拥有的状态与职责 |
|---|---|
| `UpstreamService` | 当前企业 HTTP 服务的非敏感元数据、Endpoint、Owner、Health；Remote MCP 是 Deferred 扩展 |
| `OpenAPIImport` | Source、Digest、Import Status、错误和安全校验快照 |
| `ImportedOperation` | Method、Path、参数位置、Normalized Schema、冲突与审核状态 |
| `ToolDefinition` | MCP 名称、描述、输入/输出 Schema、Version、Status、Visibility、Side Effect |
| `ToolBinding` | Tool Version 到执行目标的绑定、Executor Type 和非敏感执行配置 |
| `CredentialBinding` | Principal/Role/Tool/Upstream 与 `secret_ref` 的绑定关系 |
| `ApprovalRequest` | Tool、Principal、参数摘要、Decision、Expiry、一次性消费状态 |
| `ToolExecution` | Request/Trace、Tool Version、Policy Decision、Idempotency、Outcome |
| `AuditEvent` | 谁对什么执行了什么动作、结果和脱敏摘要 |

### 5.1 ToolDefinition 与 ToolBinding 必须分开

`ToolDefinition` 回答：

```text
Agent 看见什么？
Tool 叫什么？
参数 Schema 是什么？
当前版本和发布状态是什么？
```

`ToolBinding` 回答：

```text
这个 Tool 由谁执行？
当前使用哪个 HTTP Method/Path？
参数如何映射？
使用什么超时、响应和安全策略？
```

统一关系：

```text
ToolDefinition
    ↓
ToolBinding
    └── HttpOperationBinding
```

## 6. Java 旧实现的实际主链

旧项目参考根目录：

```text
LearnForNexusAI/AI-MCP-Gateway/projects/ai-mcp-gateway/
```

### 6.1 管理入口

`AdminController` 提供 Gateway、Tool、Protocol、Auth 的保存和查询，以及 OpenAPI 解析、导入操作。

相关入口：

- `save_gateway_config`；
- `save_gateway_tool_config`；
- `save_gateway_protocol`；
- `analysis_protocol`；
- `import_gateway_protocol`；
- `save_gateway_auth`。

### 6.2 OpenAPI 解析

`ProtocolAnalysis`：

1. 解析 OpenAPI JSON；
2. 取第一个 `servers.url`；
3. 按用户指定的 Endpoint 查找 Path；
4. 检测 HTTP Method；
5. 选择 Request Body 或 Parameters Strategy；
6. 生成 `HTTPProtocolVO` 和字段 Mapping。

`RequestBodyAnalysisStrategy` 与 `ParametersAnalysisStrategy` 负责递归 `$ref` 和参数字段转换。

### 6.3 数据存储

Java 使用五张核心表：

```text
mcp_gateway
mcp_gateway_auth
mcp_gateway_tool
mcp_protocol_http
mcp_protocol_mapping
```

关系近似为：

```text
mcp_gateway.gateway_id
    ↓
mcp_gateway_tool.protocol_id
    ↓
mcp_protocol_http.protocol_id
    ↓
mcp_protocol_mapping.protocol_id
```

`ProtocolRepository.saveHttpProtocolAndMapping` 使用事务保存 Protocol 和 Mapping。

### 6.4 Tool 绑定

Java 没有显式 `ToolBinding` 对象。管理员保存 Tool 时，将 `protocol_id` 和 `protocol_type` 写入 `mcp_gateway_tool`。

因此：

> Java 的 `protocol_id + protocol_type` 是 ToolBinding 的早期隐式表达。

管理页面同样要求管理员从 Protocol 列表中手工选择 `protocol_id`。

### 6.5 tools/list

`ToolsListHandler`：

1. 根据 `gateway_id` 查询 Tool；
2. 对每个 Tool 查询 Protocol Mapping；
3. 根据 `parent_path/mcp_path` 构建树；
4. 递归生成 MCP `inputSchema`；
5. 返回 Tool Name、Description 和 Schema。

### 6.6 tools/call

`ToolsCallHandler`：

1. 解析 Tool Name 和 Arguments；
2. 使用 `gateway_id + tool_name` 查询 `protocol_id`；
3. 查询 HTTP URL、Method、Header、Timeout；
4. 调用 `ISessionPort.toolCall`；
5. 将上游响应包装为 MCP Text Content。

`SessionPort` 通过 Retrofit/OkHttp 执行 GET/POST。

## 7. Java 与 NexusMCP 的一致点

### 7.1 核心问题选择正确

Java 不是把 Tool 写死在代码中，而是尝试用数据库配置把企业 HTTP API 动态暴露为 MCP Tool。该问题域与 NexusMCP 第一主线一致。

### 7.2 基础对象拆分方向正确

Java 已经从早期“Protocol 同时代表 Tool”演进为：

```text
Gateway 1 ── N Tool
Tool    N ── 1 Protocol
Protocol 1 ── N Mapping
```

该关系是 NexusMCP 建模的重要输入。

### 7.3 动态 Schema Builder 值得迁移为 Fixture

Java 通过父子路径递归构建嵌套 JSON Schema，能够提供：

- nested object；
- required；
- path/query 样例；
- GET/POST 调用样例。

这些输入和预期输出适合转成 Python Golden Cases。

### 7.4 Port/Adapter 依赖方向值得保留

Java Domain 定义 Repository/Port 接口，Infrastructure 提供数据库、HTTP 和 Redis Adapter。NexusMCP 应保留依赖倒置，但不复制七个 Maven Module 和每个 Java Class。

### 7.5 写入事务思想正确

Protocol 与 Mapping 一起提交，失败回滚。NexusMCP 需要把该思想扩展到 Import、Draft、Publish、Tool Version 和 Audit。

## 8. Java 的主要限制

### 8.1 OpenAPI Import 没有形成接入闭环

Java 的 `importGatewayProtocol` 只完成：

```text
OpenAPI Analysis → Protocol/Mapping Storage
```

不会同时：

- 创建 Draft Tool；
- 建立可审核 Binding；
- 生成 Import Report；
- 检查 Tool Name Collision；
- Publish Tool Version；
- 使 Tool 自动进入 Catalog。

Tool 需要通过另一套管理操作手工绑定 `protocol_id`。

### 8.2 OpenAPI 解析范围有限

当前静态实现表现为：

- 只读取第一个 Server；
- 一个 Path 只选择一个 Method；
- Request Body 与 Parameters 二选一；
- Parameters 只处理 path/query；
- `$ref` 处理范围有限；
- array/items、enum、oneOf/anyOf 等关键 JSON Schema 语义不完整；
- 解析异常记录日志后返回空结果；
- 没有 URL Fetch/SSRF 安全边界。

### 8.3 字段行模型不足以承载完整 JSON Schema

`mcp_protocol_mapping` 只保存：

```text
field_name
parent_path
mcp_path
mcp_type
mcp_desc
is_required
sort_order
```

这适合教学和简单嵌套对象，但会丢失或难以表达复杂 Schema 语义。NexusMCP 应保存确定性的完整 JSON Schema/Normalized Operation，字段 Mapping 仅作为导入中间表示或执行映射。

### 8.4 HTTP 执行器不是通用映射器

Java POST 默认取 Arguments 第一个根对象作为 Body；GET 也基于同样的形状提取 Path/Query。它无法可靠覆盖：

- 同时存在 path/query/header/body；
- 多个根参数；
- multipart/binary；
- Content-Type 差异；
- response mapping；
- 状态码和错误体分类。

### 8.5 可靠性与副作用语义不足

当前实现中：

- 只真正执行 GET/POST；
- Protocol 的单次 Timeout 没有应用到调用；
- `retry_times` 被保存但没有形成调用策略；
- 没有 read-only/idempotent/non-idempotent 分类；
- 未检查 HTTP Status；
- 未限制响应大小；
- 未表达 Unknown Execution Outcome；
- 同步 HTTP 调用不适合作为 Python async 实现参考。

### 8.6 安全边界不足

静态源码和 SQL 显示：

- API Key 明文存储；
- API Key 可通过 Query Parameter 传递；
- HTTP Header 以普通 JSON 保存；
- 部分日志记录 API Key、Header、Context 和完整 Message；
- 缺少 SSRF/URL Allowlist；
- Inbound Auth、Principal 和 Egress Credential 没有分开；
- 限流器是进程内状态，异常路径存在放行行为。

NexusMCP 不迁移任何示例 Key 或未知 Header 值。

### 8.7 数据完整性和生命周期不足

旧 Schema 没有完整表达或约束：

- Tool → Protocol 外键；
- Protocol → Mapping 外键；
- `protocol_id` 唯一性；
- Tool Draft/Review/Published/Disabled；
- Tool Owner/Tags/Visibility/Schema Digest；
- Protocol Status 在执行时的强制检查；
- Tenant/Principal/Policy/Audit。

### 8.8 协议属于 Legacy Session 主线

Java 手写 MCP Schema，并围绕 `initialize`、`Mcp-Session-Id`、GET/POST/DELETE Session 和 Redis Session 同步设计。它可用于 Legacy Fixture 和兼容性理解，但不进入 NexusMCP Modern 主模型。

### 8.9 测试主要是调试型测试

与主链相关的若干测试主要启动 Spring Context、连接数据库或外部服务并打印结果，缺少确定性断言。NexusMCP 只提取脱敏输入与预期行为，不复制其测试组织方式。

## 9. Java 的 DDD 评价

更准确的结论是：

> Java 项目采用 DDD 风格的分层和六边形依赖方向，但领域模型整体偏贫血。

值得学习：

- Trigger / Case / Domain / Infrastructure 的职责方向；
- Domain Port 与 Infrastructure Adapter；
- Protocol、Auth、Gateway、Session 的初步问题域拆分；
- Strategy 处理不同 OpenAPI 输入；
- Repository 事务边界。

不宜照搬：

- 很多 Domain Service 只是 Repository 的透传层；
- `SessionRepository` 同时读取 Gateway、Tool、Protocol，状态所有权不清；
- `SessionPort` 同时承担 HTTP Executor 和 Redis Session，职责过宽；
- Tool 发布、Binding、Credential、Execution 没有成为明确领域对象；
- Tree/Factory/Node 对简单 Method Dispatch 存在过度设计；
- 七个 Maven Module 不适合一对一翻译成 Python Package。

## 10. 迁移决策矩阵

### 10.1 继承问题与测试资产

- Gateway → Tool → Protocol/Binding 的业务关系；
- 动态 `tools/list`；
- 动态 `tools/call`；
- OpenAPI Parser 的输入样例；
- nested/required/path/query Fixture；
- JSON-RPC Request/Response/Notification 样例；
- Domain Port / Infrastructure Adapter 依赖方向；
- Protocol + Mapping 的事务思想。

### 10.2 重新设计

- OpenAPI Import → Draft → Review → Publish；
- ToolDefinition / ToolBinding / Connector；
- Tool Catalog 与版本生命周期；
- 完整 JSON Schema/Normalized Operation；
- Modern MCP + Legacy Compatibility Adapter；
- Identity / Policy / Credential / Approval；
- Async HTTP/MCP Executor；
- SSRF、Timeout、Response Limit、Error Classification；
- Idempotency、Side Effect、Unknown Outcome；
- Audit、Trace、Metric；
- Contract、Golden、E2E、Security Test。

### 10.3 明确拒绝迁移

- Java 七模块一对一翻译；
- Modern 请求依赖 Transport Session；
- 手写完整 MCP Schema 代替官方 SDK；
- 明文 API Key/Header；
- 每个 Schema 字段一行作为最终 Tool Schema；
- 固定次数的无条件 Retry；
- 日志替代断言的测试；
- 把 Java SQL 表直接作为 Python Domain Model。

## 11. 初步领域边界

以下边界用于下一轮 DDD 讨论，尚未冻结目录：

```text
Registry
└── HTTP Upstream Service

OpenAPI Import
├── Source / Import Job
├── Normalized Operation
└── Review Report

Tool Catalog
├── ToolDefinition
├── ToolVersion
└── Publish / Disable / Visibility

Connectors
├── ToolBinding
└── HttpOperationBinding

Gateway Runtime
├── Tool Discovery
├── Tool Resolution
├── Executor Dispatch
└── Result Normalization

Governance
├── Identity
├── Policy
├── Credential
├── Approval
└── Audit
```

边界原则：

- Control Plane / Data Plane 是调用和运行边界，不是两套重复领域模型；
- Tool Catalog 拥有 Tool 对外定义，Connector 拥有执行绑定；
- Protocol Adapter 不拥有 Tool 业务状态；
- Credential Secret 不属于 Catalog、Tool Schema 或 Request Context；
- Audit 记录决策和结果，但不反向决定业务行为。

## 12. 纵向切片与多源通用性证明

NexusMCP 不绑定支付、运维或其他单一业务系统。Demo 使用三个完全模拟、彼此独立的轻量企业 API：

```text
Employee Directory OpenAPI ─┐
Operations OpenAPI         ├─→ 同一 OpenAPI Import / Catalog / Binding / Runtime
Inventory OpenAPI          ┘
```

三个 Fake API 的职责：

| Fake API | 第一版接口 | 主要验证 |
|---|---|---|
| Employee Directory | 查询员工、按部门搜索 | Path、Query、分页、只读可见性 |
| Operations | 查询服务状态、重启服务 | 副作用、Approval、Timeout、未知执行结果 |
| Inventory | 查询库存、创建/取消预留 | JSON Body、nested/enum、幂等写、Credential |

实施顺序仍保持小步闭环：

```text
第一步：directory.get_employee
→ Import
→ Draft Tool + HttpOperationBinding
→ Review + Publish
→ tools/list
→ tools/call
→ Employee Directory Result

第二步：接入 Operations 与 Inventory
→ 不修改 NexusMCP 核心 Import/Runtime
→ 只增加 OpenAPI、Metadata、Binding、Policy 和 Credential 配置
```

这两个步骤分别证明：

- 第一条 API → MCP 纵向链路可以工作；
- 同一实现可以接入多个业务语义、参数形态和治理要求不同的企业系统。

通用性约束：

- NexusMCP Core 不得 import 任何 Demo 模块；
- 不得出现按场景名称分支的 Parser、Gateway 或 Executor；
- 三个服务使用独立 Namespace，允许用跨服务同名 Operation 验证名称冲突处理；
- 每个 Fake API 只保留 2～3 个接口和内存数据；
- 每个服务同时提供静态 OpenAPI Fixture 和可运行 E2E Upstream。

验收至少包括：

- Path 和 Query 参数映射正确；
- Tool Schema 与发布版本固定；
- Draft Tool 不可见，Published Tool 可见；
- 禁用 Tool 后不可发现、不可调用；
- Credential 不进入 Tool Schema 和普通日志；
- 上游 4xx/5xx/Timeout 能得到确定错误；
- 三个 Upstream 使用同一通用接入链且拥有独立 Tool Binding；
- 新增第二、第三个 Demo 不需要修改 NexusMCP 核心代码；
- 不依赖真实企业服务、真实 Token 或模型调用。

## 13. 待下一轮讨论的问题

1. Remote MCP 已由 ADR-0017 延后；只有出现明确组织级 Upstream 场景后才重新讨论 Registry/Connector。
2. `ToolBinding` 属于 Catalog 聚合，还是形成独立 Connector 领域？
3. OpenAPI Import、Draft Tool 和 Binding 的事务边界是什么？
4. Tool Version 使用独立实体还是单表多版本？
5. Published Snapshot 如何供 Data Plane 稳定读取？
6. 第一阶段是否只支持 Local Fixture/Upload，暂缓远程 URL Fetch？
7. 第一条纵向切片中的最小 Identity/Policy 边界是什么？

上述问题解决后，再冻结 Python 业务模块和项目根目录结构。

## 14. 主要源码证据

| 结论 | Java 证据 |
|---|---|
| Streamable 入口围绕 Session | `McpStreamableGatewayController`、Streamable Message Nodes |
| Method Dispatch | `SessionMessageService`、`SessionMessageHandlerMethodEnum` |
| 动态 tools/list | `ToolsListHandler`、`SessionRepository` |
| 动态 tools/call | `ToolsCallHandler`、`SessionPort`、`GenericHttpGateway` |
| OpenAPI 解析 | `ProtocolAnalysis`、`RequestBodyAnalysisStrategy`、`ParametersAnalysisStrategy` |
| Protocol/Mapping 事务 | `ProtocolRepository.saveHttpProtocolAndMapping` |
| Tool 手工绑定 protocol_id | `GatewayRepository`、`mcp_gateway_tool_mapper.xml`、管理页面 Tool 表单 |
| 明文 API Key/Header | `mcp_gateway_auth`、`mcp_protocol_http`、Auth/Controller/SQL 示例 |
| 进程内限流 | `AuthRateLimitService` |
| Legacy 协议版本 | `McpSchemaVO.LATEST_PROTOCOL_VERSION` |
| 调试型测试 | `ProtocolAnalysisTest`、`ToolsListHandlerTest`、`ToolsCallHandlerTest` |

## 15. 下一份产出

在本文评审通过后，下一份文档应是：

> 《NexusMCP 业务词汇、核心用例与限界上下文》

它负责把本文的候选概念转成统一语言，明确每个领域拥有和不拥有的状态，并为 Python 模块结构提供依据。
