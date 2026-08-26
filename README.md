# NexusMCP

[![CI](https://github.com/ksky233/NexusMCP/actions/workflows/ci.yml/badge.svg)](https://github.com/ksky233/NexusMCP/actions/workflows/ci.yml)

NexusMCP 是一个使用 Python 实现的 Enterprise MCP Gateway & Registry，负责将企业 HTTP/OpenAPI 服务和已有 MCP Server 纳入统一 Tool Catalog，并在 MCP 调用链上执行身份、策略、凭据、审批、审计与可观测性。

当前阶段：`S2-6｜S2 收口与 Control Plane 接缝完成`。

## 当前边界

- MCP `2026-07-28` 为 Modern 主线；
- Legacy Handshake/Session 只做兼容；
- 使用官方 Python MCP SDK v2；
- 正式业务代码使用 `src/nexusmcp` Layout 和领域优先模块化单体；
- 当前已建立 Application Factory、Health、动态 MCP `tools/list` Adapter；
- Catalog 已拆分 Tool、ToolVersion、PublishedTool，并建立 Repository/UoW Contract；
- GitHub Actions 会在 Push/PR 上使用云端 Ubuntu Runner 执行完整质量门禁；
- PostgreSQL、Tool/ToolVersion/ToolBinding 和 Publish 事务已经完成设计冻结；
- PostgreSQL 18.6、SQLAlchemy Async、Alembic Baseline 和 7 张首批 ORM 表已经建立；
- Catalog/Binding 已具有 SQLAlchemy Async Repository、显式 ORM Mapping 和每 Command 独立 UoW；
- 已建立协议无关安全错误、MCP/HTTP 映射接缝、结构化日志和 async Log Context；
- Publish 已实现 Tool/Version/Binding/Upstream 锁定、Digest 校验、原子状态切换与 Domain Event；
- Database Engine 由 Lifespan 管理，Readiness 反映 PostgreSQL 状态，正式 `tools/list` 可读取数据库；
- Employee Directory 已跑通 Local OpenAPI Import → Review → Publish → MCP `tools/list`；
- 三个 Demo 共 7 个接口已复用同一 Pipeline，并由 MCP 同时返回三个 Namespace；
- Catalog 已具有 PostgreSQL Weighted FTS、GIN Index、相关度排名和治理过滤；
- Local Admin REST 已覆盖 Registry、Import、Review、Publish、Search，并与 `/mcp` 隔离；
- S2 已完成；认证、Policy、Credential、Approval、Audit 和 `tools/call` 进入 S3。

## 代码语言约定

- 文件、目录、类、函数、变量和测试名称使用英文；
- MCP/OpenAPI 字段、错误码、日志事件、Metric 和 Trace Attribute 使用英文；
- 内部 Docstring 和解释“为什么”的架构注释使用中文；
- 模型可见错误默认使用英文，避免协议消费者绑定中文文本；
- 项目文档以中文为主，公开作品集阶段再补英文 Overview；
- 不逐行翻译显而易见的代码，不使用中英双语重复注释。

## 本地环境

```powershell
uv sync --frozen
uv run python -m pytest
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv build
uv run uvicorn nexusmcp.main:app --reload
```

## 本地 PostgreSQL

```powershell
docker compose up -d postgres

$env:NEXUSMCP_DATABASE_URL = "postgresql+asyncpg://nexusmcp:nexusmcp_dev@127.0.0.1:55432/nexusmcp"
uv run alembic upgrade head
uv run alembic check

$env:NEXUSMCP_TEST_DATABASE_URL = "postgresql+asyncpg://nexusmcp:nexusmcp_dev@127.0.0.1:55432/nexusmcp_test"
uv run python -m pytest tests/integration -q
```

## Local Control Plane

当前 `/admin` 是开发/学习阶段的 Local Control Plane，使用 Settings 中固定 Tenant/Principal，不接受
客户端 Tenant Header，且禁止在 `production` 启用。S3 Authentication 完成前不要将它暴露到非可信网络。

```powershell
Copy-Item .env.example .env
docker compose up -d postgres

$env:NEXUSMCP_DATABASE_URL = "postgresql+asyncpg://nexusmcp:nexusmcp_dev@127.0.0.1:55432/nexusmcp"
uv run alembic upgrade head

docker compose exec -T postgres psql -U nexusmcp -d nexusmcp -c `
  "INSERT INTO tenant (id, name, status) VALUES ('00000000-0000-0000-0000-000000000001', 'Local Tenant', 'active') ON CONFLICT (id) DO NOTHING;"

uv run uvicorn nexusmcp.main:app --reload
```

打开 `http://127.0.0.1:8000/admin/docs` 可以按顺序执行：

```text
POST /admin/upstreams
POST /admin/openapi/imports
GET  /admin/openapi/imports/{job_id}
POST /admin/openapi/operations/{operation_id}/review
POST /admin/tool-versions/{version_id}/submit-review
POST /admin/tools/{tool_id}/versions/{version_id}/publish
GET  /admin/catalog/search?q=employee
```

注册 Employee Directory 的 Curl 示例：

```powershell
curl.exe -X POST http://127.0.0.1:8000/admin/upstreams `
  -H "Content-Type: application/json" `
  -d '{"namespace":"directory","name":"employee-directory-api","owner":"people-platform","endpoint":"http://127.0.0.1:9001","auth_scheme":"none","config":{}}'
```

`/admin` 负责 Control Plane，`/mcp` 保持 MCP Protocol 边界，`/health/live` 与 `/health/ready` 保持独立。

停止 Container 但保留数据：

```powershell
docker compose stop postgres
```

## 文档

- [项目规划](./docs/项目规划/README.md)
- [核心业务主链与 Java 迁移评估](./docs/迁移分析/01_核心业务主链与Java迁移评估.md)
- [S1 协议与 SDK 实验计划](./docs/实验记录/01_S1协议与SDK实验计划.md)
- [S2-1 最小工程骨架验收](./docs/实验记录/02_S2-1最小工程骨架验收.md)
- [S2-1.5 CI 基线](./docs/实验记录/03_S2-1.5_CI基线.md)
- [S2-2B-1 PostgreSQL 与 Migration 基线](./docs/实验记录/04_S2-2B-1_PostgreSQL与Migration基线.md)
- [S2-2B-2 Catalog Domain 与 Port 契约](./docs/实验记录/05_S2-2B-2_Catalog领域与Port契约.md)
- [S2-2B-3 PostgreSQL Repository 与 Unit of Work](./docs/实验记录/06_S2-2B-3_PostgreSQLRepository与UnitOfWork.md)
- [S2-2B-3.5 Error 与 Logging 基线](./docs/实验记录/07_S2-2B-3.5_Error与Logging基线.md)
- [S2-2B-4 Publish 事务 Use Case](./docs/实验记录/08_S2-2B-4_Publish事务UseCase.md)
- [S2-2B-5 Database Bootstrap 与正式 Catalog Query](./docs/实验记录/09_S2-2B-5_DatabaseBootstrap与正式CatalogQuery.md)
- [S2-3 Employee Directory OpenAPI 纵向切片](./docs/实验记录/10_S2-3_EmployeeDirectoryOpenAPI纵向切片.md)
- [S2-4 Operations / Inventory 通用性验证](./docs/实验记录/11_S2-4_OperationsInventory通用性验证.md)
- [S2-5 Catalog PostgreSQL FTS](./docs/实验记录/12_S2-5_CatalogPostgreSQLFTS.md)
- [S2-6 S2 收口与 Control Plane 接缝](./docs/实验记录/13_S2-6_S2收口与ControlPlane接缝.md)
- [业务词汇、核心用例与限界上下文](./docs/架构/01_业务词汇核心用例与限界上下文.md)
- [持久化模型与发布事务](./docs/架构/02_持久化模型与发布事务.md)
- [ADR-0001：Python 项目布局](./docs/adr/0001-python-project-layout.md)
- [ADR-0002：MCP 协议与 SDK Adapter](./docs/adr/0002-mcp-protocol-and-sdk-adapter.md)
- [ADR-0004：PostgreSQL 主存储](./docs/adr/0004-postgresql-primary-store.md)
