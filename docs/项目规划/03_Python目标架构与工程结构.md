# 03｜Python 目标架构与工程结构

> 状态：Accepted，项目布局由 [ADR-0001](../adr/0001-python-project-layout.md) 冻结
> 目标：用适合 Python 的模块化单体承载 Control Plane 与 Data Plane，避免 Java 式目录直译。

## 1. 技术栈建议

| 层面 | 推荐 |
|---|---|
| Runtime | Python 3.12+，项目初始化时锁定小版本 |
| Packaging | `uv` + `pyproject.toml` + lockfile |
| API | FastAPI / Starlette |
| Contract | Pydantic v2 |
| Persistence | SQLAlchemy 2 async + Alembic |
| Database | PostgreSQL；S4 Tool Semantic Retrieval 使用 pgvector |
| Cache/Coordination | Redis 按需引入，不作为空骨架依赖 |
| HTTP Client | httpx async |
| MCP | 官方 Python MCP SDK v2 |
| Observability | OpenTelemetry |
| Tests | pytest + pytest-asyncio + integration containers |
| Quality | Ruff、basedpyright、pre-commit（需要时启用 Hook） |
| Deployment | Docker Compose；后续再讨论 Kubernetes |

直接依赖在相关阶段确认，完整解析版本由 `uv.lock` 锁定。当前 S1 已锁定 Python 3.12.10 和 `mcp==2.0.0`；Persistence 等依赖在真实模块出现时加入。

## 2. 已确认目录与渐进创建规则

```text
NexusMCP/
├── pyproject.toml
├── uv.lock
├── src/
│   └── nexusmcp/
│       ├── main.py
│       ├── bootstrap/
│       ├── interfaces/
│       ├── modules/
│       ├── infrastructure/     # 有真实跨模块技术职责后创建
│       └── shared/
├── migrations/                 # PostgreSQL Model 出现后创建
├── examples/
│   ├── mcp_compatibility/
│   ├── upstream_apis/
│   │   ├── employee_directory/
│   │   ├── operations/
│   │   └── inventory/
│   └── demo_client/
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   ├── e2e/
│   ├── security/
│   └── fixtures/
├── evals/
├── docs/
└── docker-compose.yml
```

第一层职责：

```text
bootstrap       应用组装、配置和 Lifespan
interfaces      MCP/Admin/Health/CLI 入站 Adapter
modules         按限界上下文组织 Domain、Use Case、Port、专用 Adapter
infrastructure  跨模块数据库/HTTP/Secret/Otel 技术基础
shared          极少量稳定跨域契约
```

业务候选模块为 Registry、OpenAPI Import、Catalog、Connectors、Identity、Policy、Credentials、Approval、Execution、Audit，但模块只在第一个真实 Use Case 出现时创建。

简单模块先使用：

```text
modules/catalog/
├── domain.py
├── ports.py
└── use_cases.py
```

出现真实复杂度后再拆成 `domain/`、`application/`、`ports/`、`adapters/` 子包，不预建空分层。

首批实际目录只包括：

```text
src/nexusmcp/
├── main.py
├── bootstrap/
│   ├── app.py
│   └── config.py
├── interfaces/
│   ├── health/router.py
│   └── mcp/
│       ├── server.py
│       ├── context.py
│       └── errors.py
├── modules/catalog/
│   ├── domain.py
│   ├── ports.py
│   ├── use_cases.py
│   └── adapters/in_memory.py
└── shared/
    ├── errors.py
    └── request_context.py
```

`infrastructure`、其他业务模块、Admin API、CLI、Migration 和 Eval 在真实职责出现时创建。

`catalog/adapters/in_memory.py` 已因 Application Factory 和确定性测试的真实需要进入首批目录；它实现与未来 PostgreSQL Adapter 相同的 Port，不是一次性 Demo。

`examples/upstream_apis/` 中的三个 Fake API 是独立测试上游，不属于 NexusMCP Domain。`src/nexusmcp/` 不得 import Demo 模块，也不得为某个场景增加专用 Parser、Gateway 或 Executor。三个服务必须通过同一 OpenAPI Import、Tool Binding 和 Runtime 链路接入。

## 3. 依赖方向

核心规则：

```text
API / Protocol Adapter
        ↓
Application Use Case
        ↓
Domain Model / Policy Contract
        ↓
Repository / Provider Port
        ↑
Infrastructure Adapter
```

不允许：

- Domain 直接 import FastAPI Request；
- Tool Handler 直接读取全局数据库 Session；
- Policy Engine 直接发送 HTTP；
- Credential Resolver 把 Secret 返回给 Agent 层；
- Audit 反向决定业务是否允许；
- Control Plane Service 调用 Data Plane 私有实现。

## 4. Control Plane

负责低频配置和生命周期：

- MCP Server Register/Update/Disable；
- Tool Sync；
- OpenAPI Import；
- Draft/Review/Publish；
- Policy 配置；
- Credential Binding 配置；
- Tool Search；
- Health Status 和版本查看。

Control Plane 写入配置状态，发布后形成 Data Plane 可读取的快照或带版本记录。

## 5. Data Plane

负责高频请求：

- 协议版本识别；
- Authentication 和 RequestContext；
- Server/Tool Resolution；
- Visibility/Policy；
- Credential Resolution；
- MCP/HTTP Upstream；
- timeout/cancel/error normalization；
- redaction；
- Trace/Metric/Audit。

Data Plane 不负责：

- 编辑 OpenAPI 文档；
- 交互式创建 Tool；
- 修改 Policy；
- 管理真实 Secret 值；
- 运行完整 Agent Loop。

## 6. RequestContext

统一请求上下文建议包含：

```python
class RequestContext:
    request_id: str
    trace_id: str
    protocol_version: str
    protocol_era: str
    tenant_id: str
    principal_id: str
    agent_id: str | None
    run_id: str | None
    authn_method: str
    policy_snapshot: str | None
```

创建原则：

- Protocol Adapter 解析协议字段；
- Auth Middleware 创建可信 Principal；
- 客户端 Header 不能覆盖 Token Claims；
- Secret 不进入 Context；
- Context 在 async 调用链中显式传递或通过受控 ContextVar 传播；
- 后台任务必须复制必要字段，不能依赖已结束 Request 对象。

## 7. Application Use Cases

Use Case 按行为命名，而不是按旧 Java Service 命名，例如：

```text
RegisterUpstreamService
SyncServerTools
ImportOpenApi
ReviewImportedTool
PublishTool
SearchTools
ListVisibleTools
CallTool
ResolveApproval
CheckServerHealth
```

每个 Use Case 定义：

- 输入 Command/Query；
- 读取的状态；
- 产生的 Policy Decision；
- 事务边界；
- Outbound Port；
- Audit Event；
- 可重试性。

## 8. Port / Adapter

建议先定义少量高价值 Port：

```python
class ToolRepository(Protocol): ...
class UpstreamRepository(Protocol): ...
class PolicyEvaluator(Protocol): ...
class CredentialProvider(Protocol): ...
class ToolExecutor(Protocol): ...
class AuditSink(Protocol): ...
```

不要为每个 Class 建 Interface。Port 只用于隔离真正会变化的外部边界或重要策略。

## 9. Async 与并发

必须统一：

- 所有外部 HTTP/MCP 调用使用 async；
- 每个 outbound 设置 timeout；
- disconnect/cancel 向下游传播；
- DB transaction 不跨越长时间 HTTP 调用；
- 不在事件循环执行阻塞 PDF 解析/Embedding；
- 并发 Tool Call 有上限；
- Health Check 有独立 semaphore；
- Audit 写入失败不能悄悄吞掉，但也不能默认让 Tool 重复执行。

对副作用 Tool：

```text
before execute → create execution record/idempotency key
execute
after response → mark outcome
unknown outcome → do not blind retry
```

## 10. 配置与 Secret

配置分为：

```text
Application Config
= port/log/db/otel/feature flag

Control Plane Config
= server/tool/policy/credential binding metadata

Secret Value
= environment/dev secret store/external vault
```

数据库只保存 `secret_ref`、provider 和 binding metadata，不默认保存明文 Secret。

## 11. 错误模型

内部错误至少区分：

```text
AuthenticationError
AuthorizationError
ApprovalRequired
ToolNotFound
ToolDisabled
InvalidArguments
ProtocolError
UpstreamTimeout
UpstreamUnavailable
UnknownExecutionOutcome
CredentialResolutionError
RateLimitExceeded
```

由 Protocol Adapter 映射成 MCP/JSON-RPC/HTTP 对外错误。日志保留内部 error code，不向客户端泄露 Secret、堆栈和内部 URL。

实现边界：

```text
Domain/Application
→ 只抛 NexusMcpError 子类，不 import FastAPI/MCP/SQLAlchemy Error

MCP Interface
→ 映射为 MCP Tool Result 或 JSON-RPC Error

HTTP Interface
→ 映射为 HTTP Status + {code, message, request_id}

Background Job
→ 映射为 failed status + error_code + safe message
```

`safe_message` 可以进入协议响应；内部诊断消息只进入受控日志。HTTP Status、MCP Result 和 Job Status
都属于 Interface Adapter 决策，不写入 Domain Exception。

Expected Error 只在最外层边界记录一次，避免 Repository、Use Case、Interface 重复打印同一异常。
Unexpected Exception 对外统一返回安全消息，内部日志只记录异常类型和不含参数值的 Stack Frame。

S2-2B-3.5 已实现 Publish 前置错误集：Tool/Version/Binding Not Found、Invalid Tool State、Tenant
Boundary Violation、Publish Conflict、Upstream Not Active 和 Schema/Binding Digest Mismatch。

## 12. 启动形态

第一版进程内同时挂载：

```text
/admin/*        Control Plane REST
/mcp            MCP Modern + Legacy
/health/*       readiness/liveness/dependency health
/metrics        Prometheus exporter（若采用）
```

后续拆分触发条件：

- Data Plane 负载显著高于 Control Plane；
- 配置变更需要独立权限/部署；
- 故障隔离或独立扩缩容有实测依据；
- 管理面与运行面需要不同网络边界。
