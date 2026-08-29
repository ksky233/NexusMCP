# OpenAPI 到 MCP 调用的手工验证流程

> 日期：2026-08-29
> 用途：重复验证 NexusMCP 的 OpenAPI 接入、Tool 发布、MCP 暴露、真实调用与审计主链

## 1. 这次验证要证明什么

本流程使用仓库自带的 Employee Directory Fake API，手工跑通：

```text
Fake HTTP API
→ Register Upstream
→ Import OpenAPI
→ Review Operation
→ Publish Tool
→ MCP tools/list
→ MCP tools/call
→ HTTP Upstream
→ Execution / Attempt / Audit
```

它同时验证两类能力：

- Control Plane：注册、导入、审核和发布；
- Data Plane：Tool 发现、调用治理、HTTP 转发和执行证据。

本流程会向开发数据库 `nexusmcp` 写入 Demo 数据。重复执行时应更换 Namespace，避免与已有 Tool 的稳定身份
冲突。

## 2. 前置条件

- Docker Desktop 已启动；
- 项目依赖已经执行过 `uv sync`；
- 前端依赖已经执行过 `cd web && pnpm install`；
- `8000`、`9001`、`5173` 端口未被其他程序占用；
- 所有后端命令均在项目根目录执行。

项目根目录：

```text
E:\AI_Projects\LearnProjects\Projects\NexusAI\NexusMCP
```

## 3. 启动 Employee Directory Fake API

在终端 A 执行：

```powershell
uv run uvicorn examples.upstream_apis.employee_directory.app:app `
  --host 127.0.0.1 `
  --port 9001 `
  --reload
```

### 这一步的作用

Fake API 模拟一个已经存在的企业内部 HTTP 系统。NexusMCP 不负责实现员工查询业务，只负责把该 API 的
能力接入、治理并暴露为 MCP Tool。

对应角色：

```text
Employee Directory Fake API
= 被接入的企业内部 Upstream Service
```

### 验证

访问：

```text
http://127.0.0.1:9001/docs
http://127.0.0.1:9001/employees/emp-001
```

第二个地址应返回 `Ada Chen`。如果这里失败，后面的 Tool 调用也一定失败，因此应先修复 Fake API。

## 4. 启动 NexusMCP 后端

在终端 B 执行：

```powershell
$env:NEXUSMCP_TOOL_EXECUTION_ENABLED = "true"
$env:NEXUSMCP_TOOL_DISCOVERY_MODE = "eager"
$env:NEXUSMCP_UPSTREAM_EGRESS_POLICY_ENABLED = "true"
$env:NEXUSMCP_UPSTREAM_ALLOWED_PORTS = "[9001]"
$env:NEXUSMCP_UPSTREAM_ALLOW_LOCAL_DEMO = "true"
$env:NEXUSMCP_OPENAPI_FIXTURE_ROOT = "examples/upstream_apis"

uv run python run.py --reload
```

### 这一步的作用

这些配置分别控制：

| 配置 | 作用 |
|---|---|
| `TOOL_EXECUTION_ENABLED` | 允许已发布 Tool 进入正式执行链 |
| `TOOL_DISCOVERY_MODE=eager` | `tools/list` 直接返回可见的业务 Tool 与内建 Meta Tool |
| `UPSTREAM_EGRESS_POLICY_ENABLED` | 启用 Upstream 出站安全检查 |
| `UPSTREAM_ALLOWED_PORTS=[9001]` | 允许本次 Demo 访问 Fake API 的 9001 端口 |
| `UPSTREAM_ALLOW_LOCAL_DEMO` | 仅在本地开发环境允许 Loopback Upstream |
| `OPENAPI_FIXTURE_ROOT` | 限定可导入的本地 OpenAPI Fixture 根目录 |

`run.py` 会继续完成：

1. 启动项目 PostgreSQL 18 + pgvector 容器；
2. 等待数据库健康；
3. 执行 `alembic upgrade head`；
4. Development Control Plane 幂等初始化 Local Tenant；
5. 启动 FastAPI；
6. 等待 `/health/ready` 通过。

因此这里不需要手动设置 `NEXUSMCP_DATABASE_URL`。如果 `.env` 或当前 Shell 已经显式设置连接地址，则显式
配置优先。

### 验证

```text
http://127.0.0.1:8000/health/ready
http://127.0.0.1:8000/admin/docs
```

`health/ready` 证明应用和数据库均已准备好；`admin/docs` 用于确认 Control Plane API 已启用。

## 5. 启动 Web Control Plane

在终端 C 执行：

```powershell
cd web
pnpm dev
```

访问：

```text
http://127.0.0.1:5173
```

### 这一步的作用

Vite 提供本地 React 页面，并将 `/admin` 和 `/health` 同源代理到 `127.0.0.1:8000`。Web UI 只是
Control Plane 的展示与操作入口，后端仍是业务状态机和权限判断的唯一事实源。

开发服务器不代理 `/mcp`，所以后面的 MCP Client 直接连接后端 `8000` 端口。

## 6. 注册 Upstream Service

进入“上游服务”→“注册上游服务”，填写：

| 字段 | 示例值 |
|---|---|
| Namespace | `demo_directory` |
| 名称 | `employee-directory-demo` |
| 负责人 | `people-platform` |
| 认证方案 | `无` |
| Endpoint | `http://127.0.0.1:9001` |
| 描述 | `本地 Employee Directory Fake API` |
| 非敏感 Config JSON | `{}` |

### 这一步的作用

Upstream Service 记录“能力来自哪个系统、由谁负责、通过什么地址和认证方式访问”。它没有创建 Tool，只是
建立一个受治理的外部系统身份。

几个字段的边界：

- Namespace：Tool 稳定名称的业务前缀；
- 名称：该 Upstream Service 自身的名称；
- Owner：负责该系统的团队或人员；
- Endpoint：真正执行 HTTP 请求时的基础地址；
- Config：非敏感连接配置，不能存放 Token 或密码。

提交后应进入：

```text
demo_directory.employee-directory-demo
```

重复实验时，可改用 `demo_directory_2` 等新 Namespace。

## 7. 导入 OpenAPI

进入“导入与审核”→“新建导入”，填写：

| 字段 | 示例值 |
|---|---|
| 已启用上游服务 | `demo_directory.employee-directory-demo` |
| Fixture 来源 | `employee_directory/openapi.json` |
| Operation Allowlist | `getEmployee` |

点击“提交导入”。

### 这一步的作用

OpenAPI Import 会：

1. 读取并校验 OpenAPI 文档；
2. 将 Path + Method 解析为标准化 Imported Operation；
3. 生成候选 Tool Name、Input Schema 和 Output Schema；
4. 检查命名、Schema 与现有 Catalog 是否冲突；
5. 等待人工 Review，而不是直接发布。

`Operation Allowlist=getEmployee` 表示本次只接入一个 Operation，便于观察最小完整链路。未填写时会导入
Fixture 中全部受支持的 Operation。

预期出现：

```text
getEmployee
GET /employees/{employee_id}
Tool：demo_directory.get_employee
```

## 8. Review、Submit 与 Publish

在 `getEmployee` 卡片中依次执行：

1. 点击“审核 Operation”；
2. 负责人填写 `people-platform`；
3. 可见范围选择“公开”；
4. 点击“接受并创建草稿”；
5. 点击“提交审核”；
6. 点击“发布版本”；
7. 在确认框点击“发布 Tool 版本”。

### 每一步的作用

| 动作 | 作用 |
|---|---|
| Review Operation | 人工确认自动生成的名称、Schema、Owner 与可见范围 |
| 接受并创建草稿 | 创建 Tool、ToolVersion 与 ToolBinding 草稿 |
| 提交审核 | 将 ToolVersion 从 `draft` 推进到 `review` |
| 发布版本 | 校验 Schema/Binding Digest，并原子发布 Version 与 Binding |

这里不会直接修改一个“Tool 接口”。NexusMCP 保留稳定 Tool 身份，并通过不可变 ToolVersion 管理 Contract
演进；ToolBinding 则记录该版本如何映射为 Upstream HTTP 请求。

发布成功后进入“工具目录”，应能看到：

```text
demo_directory.get_employee
```

### 8.1 生成 Tool Search Embedding（Hybrid 可选）

Tool 发布后会显示为“未索引”。进入“工具目录”顶部的“检索索引管理”，点击“更新检索索引”，确认后系统会：

```text
创建持久化 Reindex Job
→ 后台读取 Missing/Stale Tool
→ 构建 Canonical Search Document
→ 调用服务端 Embedding Provider
→ 写入 pgvector Projection
→ 状态变为“已索引”
```

该步骤只影响 Hybrid Tool Search，不影响 `tools/list` 或按已知名称执行 `tools/call`。已经 Current 的 Tool
不会在普通更新中重复调用付费 API。

## 9. 使用正式 MCP Client 发现并调用 Tool

在终端 D、项目根目录执行：

```powershell
@'
import asyncio
import json

from mcp import Client
from mcp.client.streamable_http import streamable_http_client


async def main() -> None:
    async with Client(
        streamable_http_client("http://127.0.0.1:8000/mcp")
    ) as client:
        listed = await client.list_tools()

        print("可见 Tools：")
        for tool in listed.tools:
            print(f"- {tool.name}")

        result = await client.call_tool(
            "demo_directory.get_employee",
            {"employee_id": "emp-001"},
        )

        if result.is_error:
            raise RuntimeError(f"Tool 调用失败：{result}")

        print("\n调用结果：")
        print(
            json.dumps(
                result.structured_content,
                ensure_ascii=False,
                indent=2,
            )
        )


asyncio.run(main())
'@ | uv run python -
```

### `tools/list` 的作用

`client.list_tools()` 对应 MCP `tools/list`。它不是查询数据库的调试接口，而是 Agent/MCP Client 正式发现
当前 Principal 可见 Tool 的协议入口。

在 `eager` 模式下，结果至少应包含：

```text
nexus.search_tools
demo_directory.get_employee
```

- `nexus.search_tools`：NexusMCP 内建的 Meta Tool；
- `demo_directory.get_employee`：刚刚接入并发布的企业业务 Tool。

如果数据库中已有其他已发布 Tool，它们也可能出现在列表中。

### `tools/call` 的作用

`client.call_tool(...)` 对应 MCP `tools/call`。调用不会直接跳到 Fake API，而是经过：

```text
MCP Request Context
→ Principal
→ Tool/Version/Binding Resolution
→ Visibility + Policy
→ Egress Policy
→ Credential Resolution（本例为 none）
→ Execution Plan
→ HTTP Executor
→ Fake Employee Directory
→ Execution / Attempt / Audit Persistence
→ MCP Result
```

预期结果：

```json
{
  "employee_id": "emp-001",
  "name": "Ada Chen",
  "department": "engineering",
  "status": "active",
  "email": "ada.chen@example.test"
}
```

## 10. 在 UI 中检查执行证据

进入“执行与审计”，找到：

```text
demo_directory.get_employee
状态：成功
Attempt：1
```

点击执行记录，检查：

- Execution ID：一次受治理调用的稳定记录；
- Request ID：应用日志关联标识；
- Trace ID：分布式追踪关联标识；
- Policy：本次调用采用的策略版本和原因；
- Attempt 时间线：实际 Upstream 尝试次数与 HTTP 状态；
- 审计时间线：允许、执行和终态等只追加事实。

这些页面有意不展示完整 Arguments、Result 或 Credential，避免管理界面成为敏感数据泄漏入口。

## 11. 成功判定

只有以下事实全部成立，才算主链验证通过：

- Fake API 可以直接访问；
- Upstream 注册成功；
- OpenAPI Import 完成且 Operation 无冲突；
- ToolVersion 与 ToolBinding 成功发布；
- `tools/list` 返回发布后的 Tool；
- `tools/call` 返回 `Ada Chen`；
- Execution 状态为成功；
- Attempt 记录 Upstream HTTP `200`；
- Audit 存在对应调用事实。

## 12. 常见问题

### 12.1 注册 Upstream 返回不安全地址

检查：

```powershell
$env:NEXUSMCP_UPSTREAM_ALLOWED_PORTS
$env:NEXUSMCP_UPSTREAM_ALLOW_LOCAL_DEMO
```

本地 Loopback 默认不应在生产环境开放。本流程显式打开它，只用于 Fake API Demo。

### 12.2 Import 找不到 Fixture

确认：

```powershell
$env:NEXUSMCP_OPENAPI_FIXTURE_ROOT = "examples/upstream_apis"
```

Fixture 来源填写相对路径：

```text
employee_directory/openapi.json
```

### 12.3 Operation 出现冲突

开发数据库可能已经存在相同 Canonical Tool。重新注册时更换 Namespace，例如：

```text
demo_directory_2
```

随后调用名称也要改为：

```text
demo_directory_2.get_employee
```

如果注册阶段出现 `upstream_conflict`，先确认当前版本已经执行最新 Migration 并重启后端。W4.6 起，
Development Control Plane 会自动初始化 `NEXUSMCP_LOCAL_TENANT_ID` 对应的 Tenant；数据库 Foreign Key
Error 也不会再伪装成名称冲突。

### 12.4 `tools/list` 看不到业务 Tool

依次检查：

- ToolVersion 是否已发布；
- ToolBinding 是否已发布；
- Upstream 是否为 Active；
- Visibility/Policy 是否允许当前 Principal；
- `NEXUSMCP_TOOL_DISCOVERY_MODE` 是否为 `eager`。

### 12.5 `tools/call` 找得到 Tool 但不能执行

检查：

- `NEXUSMCP_TOOL_EXECUTION_ENABLED=true`；
- Fake API 的 9001 端口仍在监听；
- Endpoint 是否为 `http://127.0.0.1:9001`；
- Egress Policy 是否允许本地 Demo 与 9001 端口；
- FastAPI 终端中的结构化错误码和 Request ID。

## 13. 停止与清理

在 Fake API、NexusMCP 和 Vite 三个终端分别按 `Ctrl+C`。

默认情况下，`run.py` 会停止由它启动的 PostgreSQL。若希望后续继续查看数据库，可使用：

```powershell
uv run python run.py --reload --keep-infra
```

该流程不会自动删除已经注册、导入和发布的开发数据。保留数据适合继续观察 Catalog、Execution 与 Audit；需要
隔离且可清空的自动化验证时，应使用 `nexusmcp_test` 和现有 Full-stack Playwright E2E，而不是清空开发库。
