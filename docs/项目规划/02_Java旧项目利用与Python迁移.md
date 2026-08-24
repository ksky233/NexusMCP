# 02｜Java 旧项目利用与 Python 迁移

> 状态：初步迁移策略
> 原则：迁移问题域、状态模型和测试样例，不逐行翻译 Java，不复制旧协议 Transport。

## 1. 源项目

旧项目位于：

```text
LearnForNexusAI/AI-MCP-Gateway/
├── docs/course/
├── examples/json-rpc/
├── examples/mcp-server/
└── projects/ai-mcp-gateway/
```

主工程采用：

```text
Spring Boot 3
Spring AI
Java 17
MySQL
Redis
DDD-style multi-module
```

## 2. 总体结论

旧项目可以贡献三类资产：

```text
A. 直接吸收的业务知识
B. 需要重新设计的工程实现
C. 仅用于理解历史的协议代码
```

| 资产 | 利用等级 | 处理方式 |
|---|---|---|
| JSON-RPC 概念与测试消息 | 高 | 转成 Python Golden Cases |
| Tool/Gateway/Auth/Protocol 业务词汇 | 高 | 重写为新领域模型 |
| OpenAPI 解析需求与边界案例 | 高 | 保留输入样例，重写 Parser |
| `tools/list` / `tools/call` Handler 思路 | 中 | 保留职责，改用 SDK/Dispatcher |
| Java DDD 模块职责 | 中 | 映射边界，不映射模块数量 |
| MySQL 表和样例数据 | 中到低 | 做迁移输入，不直接沿用 |
| Redis Session 同步 | 低 | 只作为 Legacy 对照 |
| SSE/Session Transport | 历史参考 | 不进入 Modern 主实现 |
| 手写 MCP Schema | 低 | 被官方 SDK 类型替代 |
| Java 管理 UI | 低 | 只参考操作流程 |

## 3. 旧协议事实

旧项目虽然支持 Streamable HTTP，但主实现仍属于 Legacy Era：

- `McpSchemaVO.LATEST_PROTOCOL_VERSION = "2024-11-05"`；
- `InitializeNode` 创建 Session 并返回 `Mcp-Session-Id`；
- Streamable GET/POST/DELETE 围绕 Session 工作；
- Example Transport 最多声明到 `2025-06-18`；
- 没有 `2026-07-28` 的 `server/discover`、`Mcp-Method`、`Mcp-Name`、MRTR 和 cache hints。

因此：

> “已支持 Streamable HTTP”不能作为“已支持最新 MCP”的证据。

新版协议设计以 [01｜协议基线与兼容策略](./01_协议基线与兼容策略.md) 为唯一项目基线。

## 4. Java 模块到 Python 边界映射

| Java 模块 | 旧职责 | Python 去向 | 迁移方式 |
|---|---|---|---|
| `ai-mcp-gateway-trigger` | Controller / HTTP 入口 | `nexusmcp/api`、`nexusmcp/protocols` | 重写，使用 ASGI/FastAPI 与 MCP SDK |
| `ai-mcp-gateway-case` | 会话/消息用例编排 | `nexusmcp/application` | 保留 use-case 概念，删除 Tree Router 形式依赖 |
| `ai-mcp-gateway-domain` | Gateway/Auth/Session/Protocol/LLM | 各 domain package | 按状态所有权重新拆分 |
| `ai-mcp-gateway-infrastructure` | DAO/Repository/外部 HTTP | `nexusmcp/infrastructure` | SQLAlchemy/httpx 重写 |
| `ai-mcp-gateway-api` | DTO/API contract | `nexusmcp/api/schemas` | Pydantic v2 重写 |
| `ai-mcp-gateway-types` | 异常与公共类型 | `nexusmcp/common` | 只保留真正跨域类型 |
| `ai-mcp-gateway-app` | 配置/入口/集成测试 | `nexusmcp/main.py`、`tests/integration` | 使用 app factory 与 dependency injection |

不要把 7 个 Maven Module 等比例翻译成 7 个 Python Package。Python 版本优先维护清晰的依赖方向和领域边界。

## 5. 功能级迁移矩阵

### 5.1 JSON-RPC

保留：

- request/response/notification 区分；
- request id；
- method dispatch；
- error code 思维；
- 旧项目测试 JSON。

重写：

- 类型使用官方 SDK；
- 未知字段和版本由 SDK/Protocol Adapter 处理；
- 错误映射统一进入 `ProtocolErrorNormalizer`。

### 5.2 MCP Transport

保留：

- Modern 与 Legacy 需要兼容的业务要求；
- timeout/cancel/disconnect 场景；
- Legacy Session 作为兼容测试。

拒绝迁移：

- `initialize → createSession` 作为统一入口；
- Modern GET/DELETE Session 生命周期；
- 为现代请求建立 Redis Session；
- 自己维护全部 MCP Schema。

### 5.3 OpenAPI Import

重点复用旧项目的输入样例和问题列表：

- path/query/header/body；
- nested object；
- required；
- enum；
- operationId；
- ref；
- GET/POST/PUT/DELETE；
- Tool Name Collision。

新实现补充：

- OpenAPI 3.0/3.1 版本识别；
- SSRF 与 URL allowlist；
- Import → Draft → Review → Publish；
- Schema digest/version；
- response size/content-type policy；
- binary/stream response 明确拒绝或降级；
- Credential mapping 不落入 Tool Schema。

### 5.4 Auth / Rate Limit

旧项目的 `gateway_id + api_key + rate_limit` 只能作为 MVP 业务参考。

新模型应拆分：

```text
Credential used to call NexusMCP
!=
Identity / Principal
!=
Credential used by NexusMCP to call upstream
```

即：Inbound Auth、Internal Principal、Egress Credential 是三个概念。

### 5.5 Registry / Tool

旧表 `mcp_gateway`、`mcp_gateway_tool`、`mcp_protocol_http`、`mcp_protocol_mapping` 可以帮助理解：

- Gateway/Server；
- Tool；
- Protocol Endpoint；
- Request Mapping。

新项目应重新建模：

- `mcp_server` 不等于 Gateway 部署实例；
- Tool Schema 使用 JSON Schema/JSONB，而不是必须拆成每个字段一行；
- Secret Header 不存入普通 Protocol 配置；
- Tool Publish Status、Schema Digest、Owner、Tags、Visibility 成为一等字段；
- Retry Policy 必须考虑 Tool Side Effect。

## 6. 旧数据库利用方式

不直接执行旧 SQL 初始化新数据库，原因包括：

- 样例中存在明文 API Key；
- `gateway_id` 同时承担多种语义；
- Tool 与 Protocol/Mapping 耦合；
- HTTP Header 可能包含 Secret；
- 缺少 Tenant/Principal/Policy/Audit；
- 旧 Session 模型不适用于 Modern 协议；
- 表中 Retry 次数没有表达幂等语义。

正确利用方式：

1. 提取表意图和字段含义；
2. 为每张旧表写新模型映射；
3. 使用脱敏 fixture 验证转换；
4. 如确需导入旧数据，编写单向 migration script；
5. 不导入样例 Key、真实 URL 和历史 Session。

数据模型草案见 [04｜数据模型与状态所有权](./04_数据模型与状态所有权.md)。

## 7. 建议源码阅读顺序

不要通读全部 Java 文件，按调用链阅读：

1. `McpStreamableGatewayController`：确认旧入口；
2. `InitializeNode`：确认 Session 创建；
3. Streamable Message Root/Factory：看 Dispatch；
4. `ToolsListHandler` / `ToolsCallHandler`：看核心 Handler；
5. `ProtocolAnalysis` 与 OpenAPI Strategy：看导入；
6. `GatewayConfigService` / `GatewayToolConfigService`：看配置聚合；
7. Repository/DAO/SQL：看状态所有权；
8. `SessionDistributedService`：理解旧版多实例代价；
9. Java Tests/Swagger fixtures：提取 Golden Cases。

每条调用链输出：

```text
入口
状态读取
核心决策
Outbound
错误路径
可复用测试
Python 新边界
```

## 8. 迁移实施方法

每个功能使用四步法：

```text
Read Java
  ↓
Extract Contract
  ↓
Write Python Golden Test
  ↓
Implement New Boundary
```

禁止：

- 先生成整套 Python 目录再理解状态；
- 将 Java Class 一对一转换；
- 为保持兼容复制旧错误行为；
- 让旧 SQL 决定新 Domain Model；
- 把旧管理 UI 作为首个里程碑。

## 9. 迁移完成证据

- 有一份 Java → Python 能力矩阵；
- 至少 10 个旧项目协议/OpenAPI Fixture 转成 Python Test；
- Modern 请求不依赖旧 Session；
- 新数据模型不保存明文 Key；
- OpenAPI Import 能处理旧项目的 nested/required 样例；
- README 明确列出“继承的设计”和“拒绝的设计”；
- 旧项目只读保留，不在原目录上直接二次开发。
