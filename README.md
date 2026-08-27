# NexusMCP

[![CI](https://github.com/ksky233/NexusMCP/actions/workflows/ci.yml/badge.svg)](https://github.com/ksky233/NexusMCP/actions/workflows/ci.yml)

NexusMCP 是一个使用 Python 实现的 Enterprise MCP Gateway & Tool Registry，当前负责将企业 HTTP/OpenAPI
服务转化为受治理的 MCP Tool，并在接入、发现和调用链上执行身份、策略、凭据、审批、审计与可观测性。

当前阶段：`W0｜Admin API Contract 固化已完成`；下一步进入 `W1｜Admin Query API`。

## 当前边界

- MCP `2026-07-28` 为 Modern 主线；
- Legacy Handshake/Session 只做兼容；
- 使用官方 Python MCP SDK v2；
- 正式业务代码使用 `src/nexusmcp` Layout 和领域优先模块化单体；
- 当前已建立 Application Factory、Health、动态 MCP `tools/list` Adapter；
- Catalog 已拆分 Tool、ToolVersion、PublishedTool，并建立 Repository/UoW Contract；
- GitHub Actions 会在 Push/PR 上使用云端 Ubuntu Runner 执行完整质量门禁；
- PostgreSQL、Tool/ToolVersion/ToolBinding 和 Publish 事务已经完成设计冻结；
- PostgreSQL 18.6 + pgvector 0.8.6、SQLAlchemy Async、Alembic Baseline 和 12 张 ORM 表已经建立；
- Catalog/Binding 已具有 SQLAlchemy Async Repository、显式 ORM Mapping 和每 Command 独立 UoW；
- 已建立协议无关安全错误、MCP/HTTP 映射接缝、结构化日志和 async Log Context；
- Publish 已实现 Tool/Version/Binding/Upstream 锁定、Digest 校验、原子状态切换与 Domain Event；
- Database Engine 由 Lifespan 管理，Readiness 反映 PostgreSQL 状态，正式 `tools/list` 可读取数据库；
- Employee Directory 已跑通 Local OpenAPI Import → Review → Publish → MCP `tools/list`；
- 三个 Demo 共 8 个接口已复用同一 Pipeline，并由 MCP 同时返回三个 Namespace；
- Catalog 已具有 PostgreSQL Weighted FTS、GIN Index、相关度排名和治理过滤；
- Local Admin REST 已覆盖 Registry、Import、Review、Publish、Search，并与 `/mcp` 隔离；
- S2 已完成；S3 已冻结 Principal、Policy、Credential、Approval、Execution/Audit 与 Retry 边界；
- Modern MCP `tools/call` 已跑通 Read-Only HTTP GET、Schema Validation、Static Policy 和 Execution；
- Static Bearer Principal 与 Rule-Based ALLOW/DENY Policy 已接入调用阶段；
- CredentialBinding 已支持 Principal/Role/Tenant 特异性解析、Environment Secret Provider 与
  Header/Query Injection，DENY 不解析 Secret；
- Approval 已支持 PostgreSQL 持久化、Modern MCP MRTR、异步 Control Plane 决策、加密防篡改
  `requestState` 和行锁单次消费；
- ToolExecution 与脱敏 Audit 已持久化；Approval Consume、Running Execution、ALLOWED Audit 在同一
  短事务，终态与终态 Audit 在另一短事务；
- 一个 Execution 支持多个持久化 Attempt；Read-Only/Idempotent Write 具有有界 Retry，幂等 Key
  具有数据库唯一 Claim、参数冲突和并发去重；
- Inventory `set_reorder_level` 已作为唯一受控 PUT 幂等写纵向切片，其他 POST/非幂等写仍被拒绝；
- 内建 `nexus.search_tools` 已接通 PostgreSQL FTS；Eager 模式与业务 Tool 一起返回，Search-First
  模式初始只返回 Meta Tool；Top-K 候选携带可动态激活的完整 Schema；
- Agent-facing Search Contract 只暴露必填 `lexical | hybrid`；Hybrid 已接通 Query Embedding、
  pgvector Exact Cosine Search、RRF 与治理过滤，零索引覆盖时不静默降级；
- SiliconFlow `Qwen/Qwen3-Embedding-8B` 2048 维 Smoke Test 已通过；`VECTOR(2048)` Projection、
  pgvector Extension、Exact Cosine Round-Trip 已完成，第一版不建立 HNSW；
- 独立 `tool_search` Module 已建立；Canonical Search Document、EmbeddingProvider Port、SiliconFlow
  Adapter、PostgreSQL Repository/UoW 与幂等 Reindex CLI 已跑通；
- Hybrid 的 FTS/Vector Candidate 并发获取并使用 RRF 融合；MCP `_meta` 返回实际 Strategy 与
  `Model@Dimensions` Index Version；
- Retrieval Eval 使用 8 个 Demo Tool 与 24 条人工标注 Query；真实 SiliconFlow 快照中 Hybrid
  `Top-1=95.45%`、`Hit@3=100%`、Leakage=0，同时确认 No-Match Confidence Threshold 尚未实现；
- OpenTelemetry 已在正式 MCP Boundary 接入 W3C Trace Propagation、Count/Duration Metric、
  Console/OTLP HTTP Exporter 和敏感 Attribute 白名单；SDK Provider 由 Application Lifespan 管理；
- Egress Policy 已支持静态 Host/CIDR/Port Allowlist、Metadata Hard Deny、全 A/AAAA 校验、Registry/
  Secret/Executor 三道检查、Production Fail-Closed 和显式 Local Demo；
- Policy/Security 已建立 10 条 Golden Case 与 15 条 Evidence Manifest，覆盖 Tenant、Secret、Approval
  Replay、Idempotency 与 SSRF；
- Protocol 已建立 15 条 Modern/Legacy Matrix，覆盖 Raw JSON-RPC Error、Session、MRTR、Trace 与 Dynamic
  Activation；Failure Injection 已汇总 14 条 DB/Audit/Retry/Approval/Embedding/Egress 状态证据；
- 本机 Benchmark 已覆盖 Modern/Legacy List、Lexical/Hybrid Search 与 Read-Only Call；Threat Model 和 S5
  Unified Report 已记录所有证据、限制与残余风险；
- Remote MCP Federation/Proxy 已按 ADR-0017 延后：当前不管理开发者个人 MCP，也不声称透明代理全部 MCP
  Capability；只有出现明确组织级 Remote MCP Upstream 场景后才重新评估；
- Admin API 已冻结 13 个稳定 `operationId`、RFC 9457-compatible Problem Details、Offset Pagination
  Envelope 与确定性 OpenAPI Snapshot；公开 Upstream Contract 只允许 HTTP；
- S6 前置增强优先补齐 Admin Query API 与 Web Control Plane MVP，用可视化方式展示 Upstream、Import、
  Review、Publish、Catalog、Approval、Execution 与 Audit；
- 真实 JWT/OIDC、生产 Secret Store、CredentialBinding 持久化、跨调用 Result Replay、通用写 Tool
  与 Reconciliation 尚未实现。

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
uv run nexusmcp export-admin-openapi --output contracts/admin.openapi.json
uv run uvicorn nexusmcp.main:app --reload
```

Read-Only `directory.get_employee` 调用需要另一个终端启动 Fake Upstream：

```powershell
uv run uvicorn examples.upstream_apis.employee_directory.app:app --port 9001
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
GET  /admin/approvals/{approval_id}
POST /admin/approvals/{approval_id}/approve
POST /admin/approvals/{approval_id}/reject
```

注册 Employee Directory 的 Curl 示例：

```powershell
curl.exe -X POST http://127.0.0.1:8000/admin/upstreams `
  -H "Content-Type: application/json" `
  -d '{"namespace":"directory","name":"employee-directory-api","owner":"people-platform","endpoint":"http://127.0.0.1:9001","auth_scheme":"none","config":{}}'
```

`/admin` 负责 Control Plane，`/mcp` 保持 MCP Protocol 边界，`/health/live` 与 `/health/ready` 保持独立。

## Tool Embedding Reindex

真实 Key 只放在 Git 忽略的 `.env`：

```text
NEXUSMCP_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B
NEXUSMCP_EMBEDDING_DIMENSIONS=2048
NEXUSMCP_EMBEDDING_API_URL=https://api.siliconflow.cn/v1/embeddings
NEXUSMCP_EMBEDDING_API_KEY=<secret>
```

先检查 Missing/Stale Projection，不调用付费 API：

```powershell
uv run nexusmcp reindex-tools --dry-run
```

执行幂等 Reindex：

```powershell
uv run nexusmcp reindex-tools
```

可选参数：

```text
--tenant-id <uuid>
--batch-size 16
--force
--dry-run
```

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
- [S3-0 Call/Policy/Credential/Execution 模型与 ADR](./docs/实验记录/14_S3-0_Call治理模型与ADR.md)
- [S3-1 Read-Only HTTP tools/call](./docs/实验记录/15_S3-1_ReadOnlyHTTPToolsCall.md)
- [S3-2 Principal 与 ALLOW/DENY Policy](./docs/实验记录/16_S3-2_Principal与AllowDenyPolicy.md)
- [S3-3 CredentialBinding 与 Secret Injection](./docs/实验记录/17_S3-3_CredentialBinding与SecretInjection.md)
- [S3-4 Approval Gate 与单次消费](./docs/实验记录/18_S3-4_ApprovalGate与单次消费.md)
- [S3-5 持久化 ToolExecution 与 Audit 接缝](./docs/实验记录/19_S3-5_持久化Execution与Audit接缝.md)
- [S3-6 Retry/Idempotency 执行与 S3 收口](./docs/实验记录/20_S3-6_Retry与Idempotency执行.md)
- [S4-0/1 Meta Tool 与 Lexical Search](./docs/实验记录/21_S4-0_MetaTool与LexicalSearch.md)
- [S4-2a pgvector 与 Embedding API 基础设施](./docs/实验记录/22_S4-2_pgvector与Embedding基础设施.md)
- [S4-2b Tool Embedding Reindex Pipeline](./docs/实验记录/23_S4-2b_ToolEmbeddingReindex.md)
- [S4-3 Query Embedding、Exact Vector Search 与 Hybrid RRF](./docs/实验记录/24_S4-3_QueryEmbedding与HybridRRF.md)
- [S4-4 Retrieval Eval 与 S4 收口](./docs/实验记录/25_S4-4_RetrievalEval与S4收口.md)
- [S5-0/1 OpenTelemetry 基线](./docs/实验记录/26_S5-0_1_OpenTelemetry基线.md)
- [S5-2 Security 与 Policy Regression](./docs/实验记录/27_S5-2_Security与PolicyRegression.md)
- [S5-3 Protocol Compatibility 与 Failure Injection](./docs/实验记录/28_S5-3_Protocol与FailureInjection.md)
- [S5-4 Benchmark、Threat Model 与 S5 收口](./docs/实验记录/29_S5-4_BenchmarkThreatModel与S5收口.md)
- [W0 Admin API Contract 固化](./docs/实验记录/30_W0_AdminAPIContract固化.md)
- [S5 统一工程证据报告](./docs/工程证据/06_S5统一报告.md)
- [S5 工程证据矩阵](./docs/工程证据/01_S5证据矩阵.md)
- [业务词汇、核心用例与限界上下文](./docs/架构/01_业务词汇核心用例与限界上下文.md)
- [持久化模型与发布事务](./docs/架构/02_持久化模型与发布事务.md)
- [tools/call 治理执行模型](./docs/架构/03_tools_call治理执行模型.md)
- [内建 Meta Tool 与 Hybrid Tool Search](./docs/架构/04_内建MetaTool与HybridToolSearch.md)
- [Tool 混合检索与 RRF 算法选择](./docs/学习笔记/07_Tool混合检索与RRF算法选择.md)
- [ADR-0001：Python 项目布局](./docs/adr/0001-python-project-layout.md)
- [ADR-0002：MCP 协议与 SDK Adapter](./docs/adr/0002-mcp-protocol-and-sdk-adapter.md)
- [ADR-0004：PostgreSQL 主存储](./docs/adr/0004-postgresql-primary-store.md)
- [ADR-0005：Identity 与 Trust Boundary](./docs/adr/0005-identity-trust-boundary.md)
- [ADR-0006：Credential Reference 与 Injection](./docs/adr/0006-credential-reference-and-injection.md)
- [ADR-0007：Side Effect、Retry 与 Unknown Outcome](./docs/adr/0007-side-effect-retry-and-unknown-outcome.md)
- [ADR-0010：同库同步 Audit 写入策略](./docs/adr/0010-synchronous-audit-write-strategy.md)
- [ADR-0011：异步 Approval、MRTR 与恢复](./docs/adr/0011-asynchronous-approval-mrtr-and-resume.md)
- [ADR-0012：Retry、Idempotency 与 ExecutionAttempt](./docs/adr/0012-retry-idempotency-and-attempts.md)
- [ADR-0013：内建 Meta Tool 与 Hybrid Tool Retrieval](./docs/adr/0013-built-in-meta-tool-and-hybrid-retrieval.md)
- [ADR-0014：PostgreSQL 18 pgvector 与 Vector Storage](./docs/adr/0014-pgvector-infrastructure-and-vector-storage.md)
- [ADR-0015：手工 OpenTelemetry Boundary](./docs/adr/0015-manual-opentelemetry-boundary.md)
- [ADR-0016：Upstream Egress 与 SSRF 防护边界](./docs/adr/0016-upstream-egress-and-ssrf-boundary.md)
- [ADR-0017：延后 Remote MCP，优先 Web Control Plane](./docs/adr/0017-defer-remote-mcp-and-focus-web-control-plane.md)
- [ADR-0018：Web Control Plane 工程布局与技术栈](./docs/adr/0018-web-control-plane-engineering.md)
