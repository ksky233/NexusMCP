# S3-1｜Read-Only HTTP tools/call 验收

> 日期：2026-08-26  
> 范围：Modern MCP `on_call_tool`、Executable Resolver、JSON Schema Validation、Static Policy、
> InMemory Execution、HTTPX GET Executor、Result/Error Mapping、Employee Directory E2E

## 1. 验收链路

```text
Modern MCP Client (2026-07-28)
→ tools/call directory.get_employee
→ RequestContext / InternalPrincipal
→ PostgreSQL Resolve Published ToolVersion/Binding/Active Upstream
→ JSON Schema Validate Arguments
→ Static Read-Only ALLOW Policy
→ Create planned/running ToolExecution
→ HTTP GET /employees/{employee_id}
→ Normalize JSON Result
→ ToolExecution succeeded
→ MCP CallToolResult
```

第一切片不解析真实 Credential，不执行写 Tool。

## 2. Executable Tool Resolution

`SqlAlchemyExecutableToolResolver` 使用单次短 Session Join：

```text
Tool
ToolVersion
ToolBinding
UpstreamService
```

必须满足：

- 所有 Tenant 与 Request Tenant 一致；
- Tool Active；
- Version Published；
- Binding Published；
- Upstream Active；
- Canonical Name 精确匹配。

输出协议无关 `ResolvedExecutableTool`，包含 Schema、Side Effect、Visibility、Binding Config 与 Upstream
Endpoint，不返回 ORM Model。

## 3. Arguments Validation

项目正式声明直接依赖 `jsonschema`，使用 Published Tool Input Schema 动态验证：

- Required；
- Type；
- Enum；
- Min/Max；
- Nested Object/Array；
- Additional Properties。

Validation Error 只记录失败 Path/Rule，不把失败值放入 Exception 或模型响应。校验失败发生在 Policy/
Execution 之前，不创建 Execution Record。

## 4. S3-1 Static Policy

```text
read_only → ALLOW
其他 Side Effect → DENY
```

这不是最终 Policy Engine，只是验证 Policy Port 在正式 Call 顺序中的位置。写 Tool 在 Executor 之前被拒绝。

## 5. InMemory Execution

S3-1 使用进程内 Repository：

```text
planned → running → succeeded
                  → failed
                  → unknown
                  → cancelled
```

Arguments 只保存 Canonical JSON Digest。无效参数、不可见 Tool、Policy Deny 不创建 Execution。

InMemory 仅用于第一条执行切片；正式 PostgreSQL Execution Store 留给后续阶段。

## 6. HTTP GET Executor

`HttpxToolExecutor` 读取通用 HTTP Binding：

```text
method
path_template
parameters: path/query/header mapping
request_body
```

当前只允许：

- Binding Type HTTP；
- Method GET；
- 无 Request Body；
- Path/Query/Header 参数；
- JSON/Text Response；
- 默认最大 Response 1 MiB；
- 不跟随 Redirect；
- 独立 Timeout；
- CancelledError 原样传播。

Credential 参数固定为 None，证明 S3-1 不会偷偷读取 Secret。

## 7. Error Normalization

| Executor 状态 | 安全错误 |
|---|---|
| Schema/Binding Invalid | `invalid_arguments` |
| Write Disabled | `authorization_denied` |
| Timeout | `upstream_timeout` / `unknown_execution_outcome` |
| Network/5xx | `upstream_unavailable` |
| 4xx/Invalid JSON/Unexpected Status | `upstream_response_error` |
| Unknown Tool | `tool_not_found` |

Upstream Body、URL、Arguments 和 Stack 不进入 MCP Error。

## 8. Modern MCP Adapter

正式 Low-Level `Server` 增加 `on_call_tool`：

- SDK 继续负责 Modern/Legacy 编解码和协商；
- 主测试协商版本为 `2026-07-28`；
- 成功返回 Text Content + `structuredContent`；
- `_meta` 返回 Execution ID/Upstream Status；
- Expected Error 返回 `isError=true` 和稳定 `com.nexusmcp/errorCode`；
- SDK 自动附加 Modern `serverInfo` Meta。

未开启 `tool_execution_enabled` 时不注册 `on_call_tool`。

## 9. E2E 证据

真实 PostgreSQL Seed：

```text
Active Tool
Published ToolVersion
Published HTTP Binding
Active Employee Directory Upstream
```

HTTPX 使用 ASGI Transport 调用真实 Fake API Handler，不启动额外网络端口。MCP Client 验证：

- `protocol_version == 2026-07-28`；
- `employee_id=emp-001` 返回 Ada Chen JSON；
- 缺少 Required Argument → `invalid_arguments`；
- Unknown Tool → `tool_not_found`；
- 只有成功调用创建一条 Succeeded Execution。

## 10. 当前有意不做

- Agent Service Authentication；
- Agent Service Principal Policy Case；
- CredentialBinding/Secret Injection；
- Approval；
- Write Tool；
- Execution PostgreSQL Migration；
- Audit Sink；
- 自动 Retry/Backoff；
- Output Schema Validation；
- Remote MCP Executor。

## 11. 下一步

进入 `S3-2｜Principal 与 ALLOW/DENY Policy`：

1. 增加可信测试 Authentication Adapter；
2. 同一个 Tool 对不同 Principal 返回 ALLOW/DENY；
3. 调用阶段重新执行 Visibility/Policy；
4. DENY 不创建 Execution、不读取 Credential；
5. 保留 REQUIRE_APPROVAL 给 S3-4。

以上内容已在
[S3-2 Principal 与 ALLOW/DENY Policy](./16_S3-2_Principal与AllowDenyPolicy.md)
完成。
