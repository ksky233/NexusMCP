# ADR-0004｜PostgreSQL 作为主存储

## 状态

Accepted

## 背景

NexusMCP 的 Registry、OpenAPI Import、Catalog、Tool Version/Binding、Policy、Approval、Execution 和 Audit 需要：

- 可靠事务和并发约束；
- JSON Schema、Normalized Operation 和非敏感 Binding Config；
- Tenant Scope Unique Constraint；
- Partial Unique Index；
- Tool Catalog FTS；
- 后续 RAG Demo 的 pgvector；
- 可复现 Migration、Integration Test 和备份恢复路径。

旧 Java 项目使用 MySQL，但旧表只作为迁移输入，不决定新项目主存储。

## 决策

1. PostgreSQL 是 NexusMCP 第一版唯一主业务数据库。
2. Python Persistence 使用 SQLAlchemy 2 Async；Migration 使用 Alembic；Driver 使用 asyncpg。
3. JSON Schema、Normalized Operation、Binding Config 使用 JSONB。
4. Tool Catalog 第一版搜索使用 PostgreSQL FTS；RAG 阶段按需启用 pgvector。
5. Redis 不进入默认持久化基线，只在分布式限流、缓存、锁或 Subscription Bus 有实证需求时引入。
6. 数据库精确版本在 Docker Compose/Migration 实现时锁定，并记录在部署文档和 CI Integration Job 中。
7. Alembic 是唯一 Schema Source of Truth，不使用 `create_all()` 管理开发或生产 Schema。

## Tool 版本决策

同时解决 Q-003：

```text
Tool 1 ── N ToolVersion
ToolVersion 1 ── 1 ToolBinding（S2）
```

- Tool 保存稳定 Identity；
- ToolVersion 保存不可变 Schema/Metadata；
- ToolBinding 精确绑定 ToolVersion；
- 一个 Tool 同时最多一个 Published Version；
- 发布新版本时旧版本 Retire，不覆盖历史契约。

## 备选方案

### MySQL

拒绝作为新主存储。它可以实现基础事务和 JSON，但 NexusMCP 同时需要 PostgreSQL FTS、Partial Index、未来 pgvector 和更统一的 JSONB/约束能力。继续使用 MySQL 的主要收益只是贴近旧 Java 项目，不足以决定新架构。

### SQLite

仅适合极小本地 Demo，不作为主存储。它无法提供目标部署和并发行为的充分生产一致性，会让 Migration、Lock、JSON/FTS 和 Integration Test 产生两套语义。

### PostgreSQL + 独立 Vector/Search 数据库

当前拒绝。S2/S4 数据规模没有证据需要额外系统；优先使用 PostgreSQL FTS 和 pgvector，避免增加部署、事务和备份复杂度。

### 继续只使用 InMemory Repository

仅保留为 Unit Test/本地 Adapter，不能证明 Migration、事务、Tenant 隔离、并发发布和恢复能力。

## 影响

正面影响：

- Registry/Catalog/Binding 可以共享事务和约束；
- 完整 Tool Schema 可使用 JSONB 保存；
- Partial Unique Index 保证单 Published Version；
- FTS/pgvector 复用同一运维体系；
- Integration Test 更贴近目标部署。

代价：

- 本地开发需要 PostgreSQL 或容器；
- 需要管理 Async Session、Connection Pool 和 Migration；
- PostgreSQL 特有索引/JSONB 降低数据库可移植性；
- 测试需要严格隔离数据库和并发事务。

## 验证

S2-2B 必须证明：

- Docker/测试环境可以启动锁定版本 PostgreSQL；
- 空库 Alembic Upgrade/Downgrade 通过；
- SQLAlchemy Async Repository 与 InMemory Adapter 通过同一 Port Contract；
- Tenant/Unique/Foreign Key/Partial Index 约束生效；
- Publish ToolVersion + Binding 原子提交；
- JSONB Schema/Binding 可确定性往返；
- 测试不连接开发或生产数据库。

## 复审触发条件

- 目标部署环境禁止 PostgreSQL；
- 实际规模证明 FTS/pgvector 无法满足延迟或容量；
- Control/Data Plane 拆分后出现必须独立存储的故障域；
- 合规要求需要独立 Audit Store 或 Secret Store；
- 备份恢复、跨区域或可用性目标要求新的存储拓扑。

## 实施记录

2026-08-25 已完成第一阶段验证：

- PostgreSQL 固定为 `18.6-alpine`；
- SQLAlchemy `2.0.x` Async + asyncpg；
- Alembic Async Environment 与首份 Baseline Revision；
- 7 张 S2 首批表 Upgrade/Downgrade 通过；
- Alembic Metadata Drift Check 通过；
- JSONB 往返和单 Published Version Partial Unique Index 通过真实数据库测试；
- 本地开发库和测试库由独立 Compose Container 提供。
