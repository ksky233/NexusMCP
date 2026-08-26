# 08｜ADR 与待决策清单

> 状态：持续维护
> 作用：区分已经拍板的架构决策、推荐默认值和需要实验后再定的事项。

## 1. 已确认决策

### D-001｜NexusMCP 是独立项目

- 不把 NexusGate/NexusLLM 代码塞入本仓库；
- 只定义必要的身份与 Trace Contract；
- Agent Runtime 仅作为 Demo Client。

### D-002｜Modern MCP 优先

- 主协议：`2026-07-28`；
- Legacy handshake/session 只做兼容；
- Modern Domain 不建立隐式 Transport Session。

### D-003｜使用官方 Python MCP SDK v2

- SDK 负责协议类型、编解码和版本协商；
- 手写代码聚焦 Gateway、Registry、Policy 和治理；
- `examples/mcp_compatibility` 用于理解和契约验证，不替代 SDK。

### D-004｜模块化单体

- 第一版一个部署单元；
- 代码内区分 Control Plane/Data Plane；
- 只有实测负载/安全/故障域触发拆分。

### D-005｜旧 Java 项目只读参考

- 不在旧项目上继续开发；
- 迁移 Contract/Fixture/领域知识；
- 不逐行 JavaToPython；
- 不复制 Session Transport 和明文 Key 模型。

### D-006｜Tool Search 从 FTS Baseline 演进为 Hybrid

- S2 先完成 name/description/tags/namespace/owner + PostgreSQL FTS；
- S4 增加内建 `nexus.search_tools`、Tool Embedding 与 Hybrid Retrieval；
- Agent-facing 只暴露 `lexical | hybrid`，详见 ADR-0013。

### D-007｜外部 Knowledge RAG Demo 移出主线

- Embedding/pgvector 学习直接服务 Tool Semantic Retrieval；
- 不建设文档摄取、Chunk、Citation 或 Knowledge Platform；
- 企业已有 RAG 未来仍可作为普通 OpenAPI/MCP Upstream 接入；
- 原决定由 ADR-0013 取代。

### D-008｜质量能力进入主线

- Eval、OpenTelemetry、安全、幂等、错误分类不是收尾装饰；
- Must Feature 没有测试和失败行为说明，不算完成。

### D-009｜src Layout 与领域优先模块组织

- 正式业务代码位于 `src/nexusmcp`；
- 使用 `bootstrap/interfaces/modules/infrastructure/shared` 一级职责；
- 业务按 Registry、Catalog、Connectors 等限界上下文组织；
- 不建立重复的 Control Plane/Data Plane 领域模型；
- 不预建没有真实 Use Case 的空模块。

决策记录：[ADR-0001](../adr/0001-python-project-layout.md)。

### D-010｜PostgreSQL 主存储与 Tool 版本分离

- PostgreSQL 是第一版唯一主业务数据库；
- Tool 保存稳定身份，ToolVersion 保存不可变对外契约；
- ToolBinding 精确绑定 ToolVersion；
- Publish ToolVersion + Binding 使用同一数据库事务；
- Redis、独立 Vector/Search DB 不进入默认基线。

决策记录：[ADR-0004](../adr/0004-postgresql-primary-store.md)。

### D-011｜Internal Principal 与 Trust Boundary

- 只有认证 Adapter 创建可信 Principal；
- 不信任客户端 Tenant/User Header；
- 不保存原始 Token/完整 Claims；
- 无匹配 Policy 默认 DENY。

决策记录：[ADR-0005](../adr/0005-identity-trust-boundary.md)。

### D-012｜SecretReference 与 Egress Credential 分离

- Inbound/Internal/Egress Credential 不混用；
- 数据库只保存 SecretReference；
- Policy/Approval 后才解析 Secret；
- SecretValue 只在 Executor 单次调用内存中存在。

决策记录：[ADR-0006](../adr/0006-credential-reference-and-injection.md)。

### D-013｜Side Effect 决定 Retry 与 Unknown Outcome

- Execution 区分 Failed 与 Unknown；
- Non-Idempotent After-Send Timeout 不自动 Retry；
- Read Only/具备 Key 的 Idempotent Write 才进入有限 Retry；
- 数据库事务不跨越 Upstream 调用。

决策记录：[ADR-0007](../adr/0007-side-effect-retry-and-unknown-outcome.md)。

## 2. 推荐但需在初始化时确认

### R-001｜Persistence 工程工具

已确认 Python 3.12、uv、FastAPI、Pydantic v2、pytest、Ruff 和 basedpyright。待第一个持久化模块出现时确认 SQLAlchemy 2 async、Alembic 和数据库 Driver。

版本通过 `pyproject.toml` 与 `uv.lock` 管理，不预装尚未使用的组件。

### R-003｜Redis 按需引入

只有以下能力需要时引入：

- distributed rate limit；
- shared cache；
- subscription bus；
- distributed lock；
- background job coordination。

Legacy Session 本身不构成新项目必须引入 Redis 的理由。

## 3. 实验决策

### 3.1 已完成

| ID | 问题 | 结论 | 决策证据 |
|---|---|---|---|
| Q-001 | Python MCP SDK 精确版本/commit | S1 锁定 `mcp==2.0.0` | Modern/Legacy Contract Test |
| Q-002 | SDK 原生路由还是自定义 ASGI Adapter | 使用公开低层 `Server` Callback + 官方 ASGI App | Dynamic Tool/FastAPI Context Test、ADR-0002 |
| Q-003 | Tool Version 独立表还是单表多版本 | Tool 与 ToolVersion 分表；Binding 精确绑定 Version | Publish/Rollback/Query 用例分析、ADR-0004 |
| Q-005 | Approval 完全使用 MRTR 还是保留 REST resolve | 短确认使用 MRTR；长审批保留持久化 Approval + Control Plane 恢复 | S3-4 MRTR/跨进程 E2E、ADR-0011 |
| Q-006 | Audit 同步/异步写入 | 核心 Audit 同库同步；外部投递后续使用 Outbox | S3-5 故障注入/事务 E2E、ADR-0010 |
| Q-010 | 是否增加 Semantic Tool Search | S4 增加内部 Tool Embedding/Hybrid Retrieval，替代外部 Knowledge RAG 主线 | Tool Selection 业务分析、ADR-0013 |
| Q-013 | Agent-facing 暴露哪些检索模式 | 一个 `nexus.search_tools`，只暴露必填 `lexical | hybrid`；Vector-only 供 Eval，Auto 延后 | 成本/Agent 自主路由分析、ADR-0013 |

### 3.2 待实验

| ID | 问题 | 触发阶段 | 决策证据 |
|---|---|---|---|
| Q-004 | Policy condition 最小表达式 | S3 | 真实 Policy Case，不提前上 Rego |
| Q-007 | Redis 是否进入默认 Compose | S5 | Cache/rate-limit/coordination 实测 |
| Q-008 | Embedding 模型 | S4 | 中文/英文 Retrieval Eval、成本 |
| Q-009 | pgvector index 类型 | S4/S5 | 数据规模与 Benchmark |
| Q-011 | 是否拆 Control/Data Plane | 后续 | 负载/权限/故障域证据 |
| Q-012 | 是否部署 Kubernetes | 后续 | JD/部署需求，不为展示而做 |

## 4. 当前不阻塞的问题

以下问题暂不影响 S1/S2：

- 管理 UI 技术栈；
- 完整 OIDC Provider；
- Vault/KMS；
- Federation；
- A2A；
- MCP Apps；
- Skills/Agent Registry；
- 多区域部署；
- 商业计费。

如果实现过程中开始讨论这些问题，应先确认是否已经完成当前阶段验收。

## 5. ADR 状态

| ADR | 状态 | 主题 |
|---|---|---|
| [0001](../adr/0001-python-project-layout.md) | Accepted | src Layout、模块组织与首批目录 |
| [0002](../adr/0002-mcp-protocol-and-sdk-adapter.md) | Accepted | MCP 协议时代与 SDK Adapter 层级 |
| 0003 | Covered by ADR-0001 | 模块化单体与拆分触发条件 |
| [0004](../adr/0004-postgresql-primary-store.md) | Accepted | PostgreSQL 主存储与 Tool 版本模型 |
| [0005](../adr/0005-identity-trust-boundary.md) | Accepted | Identity 与 Trust Boundary |
| [0006](../adr/0006-credential-reference-and-injection.md) | Accepted | Credential Reference |
| [0007](../adr/0007-side-effect-retry-and-unknown-outcome.md) | Accepted | Tool Retry、Side Effect 与 Unknown Outcome |
| 0008 | Covered by ADR-0004/S2-5 | Tool Search FTS |
| 0009 | Deferred outside mainline | 外部 Knowledge RAG Demo |
| [0010](../adr/0010-synchronous-audit-write-strategy.md) | Accepted | 同库同步 Audit 写入策略 |
| [0011](../adr/0011-asynchronous-approval-mrtr-and-resume.md) | Accepted | 异步 Approval、MRTR 与恢复 |
| [0012](../adr/0012-retry-idempotency-and-attempts.md) | Accepted | Retry、Idempotency 与 ExecutionAttempt |
| [0013](../adr/0013-built-in-meta-tool-and-hybrid-retrieval.md) | Accepted | 内建 Meta Tool 与 Hybrid Tool Retrieval |

不是现在一次性写完。每个 ADR 在相关实现前后完成。

## 6. ADR 模板

```markdown
# ADR-XXXX｜标题

## 状态

Proposed / Accepted / Superseded

## 背景

要解决什么问题，约束是什么。

## 决策

选择什么。

## 备选方案

考虑过哪些方案。

## 影响

获得什么、失去什么、新增什么风险。

## 验证

用哪些 Test/Metric/Eval 验证。

## 复审触发条件

什么时候需要重新考虑。
```

## 7. 决策纪律

1. 先有问题和触发条件，再引入组件；
2. “某热门项目用了”不是充分理由；
3. 架构决策必须能映射到测试或指标；
4. 不用 ADR 记录普通代码细节；
5. 已确认决策如被推翻，新增 ADR 并说明 supersede，不静默改文档；
6. 待决策项不应阻塞无依赖的当前工作。
