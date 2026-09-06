# I03-1A｜Toolset Domain、Port 与 InMemory Adapter

> 状态：Completed
> 日期：2026-09-06
> 决策依据：[ADR-0020](../adr/0020-toolset-scoped-mcp-endpoints.md)
> 范围：纯 Domain/Port/InMemory Contract；不创建 Migration、不组装 Admin/MCP Runtime

## 1. 产出

新增 `modules/toolsets`：

```text
domain.py
ports.py
adapters/in_memory.py
adapters/in_memory_uow.py
```

Domain：

```text
Toolset
ToolsetMember
ToolsetAccessGrant
ToolsetKind
ToolsetDiscoveryMode
ToolsetStatus
ToolsetHealth
ToolsetMemberAvailability
```

Port：

```text
ToolsetRepository
ToolsetUnitOfWork / Factory
ToolsetCatalogReader
ToolsetCatalogSnapshot
```

## 2. Aggregate 行为

- Explicit Toolset 从 `DRAFT/direct/revision=1` 开始；
- 系统 `all_published` 从 `ACTIVE/search_first/revision=1` 开始；
- Slug 使用 lowercase kebab-case；
- Member/Grant 必须与 Aggregate Tenant/ID 一致并去重；
- Member/Grant Replace 对 ID 排序并生成确定性集合；
- 相同集合 Replace 是幂等 No-op，不推进 Revision；
- 集合发生变化时保留未变化关系原有的 Actor/Time Metadata；
- 所有实际变更推进 Revision 与 UpdatedAt；
- Expected Revision 不匹配 Fail Closed；
- Aggregate 时间不允许倒退；
- Active Explicit Toolset 不允许空 Member；
- 系统 Toolset 禁止显式 Member、改名和 Disable，但允许管理员手动切换 Discovery Mode。

Membership Digest 使用 Canonical JSON SHA-256：

```text
explicit      → kind + sorted distinct tool_ids
all_published → fixed all_published:v1 rule identity
```

## 3. Repository/UoW 契约

Repository 提供：

```text
add / save
get_by_id / get_for_update / get_by_slug
get_all_published
list_by_tenant
list_granted_active
```

InMemory Adapter 验证：

- ID、Tenant+Slug、Tenant System Toolset 唯一；
- Tenant-scoped Read/Write；
- Slug/Kind/Created Identity 不允许通过 Save 篡改；
- Granted Active Query 只返回当前 Principal 的 Active Toolset；
- UoW 使用事务副本，显式 Commit 才替换已提交状态；
- 正常退出未 Commit 和显式 Rollback 都不泄漏修改。

## 4. Catalog Read Port

`ToolsetCatalogReader` 是 Toolset UoW 的只读成员：

```text
Toolset Command Transaction
├── Lock/Read Toolset
├── Read Catalog Availability Snapshot
├── Replace/Activate Aggregate
└── Commit
```

I03-1A 只实现 InMemory Snapshot Adapter。I03-1B 的 PostgreSQL Adapter 必须与 Toolset Repository 共享同一个
AsyncSession，避免 Catalog 校验与 Toolset 写入跨事务。

## 5. 验证

```text
Toolset Domain/Repository/UoW/Architecture  21 passed
Ruff Lint                                 passed
Ruff Format                               passed
basedpyright                              0 errors / 0 warnings
```

## 6. 明确未做

- Alembic Migration；
- SQLAlchemy Model/Mapping/Repository；
- Create/Update/Replace/Activate Use Case；
- Admin API/Web；
- MCP Root/Scoped Endpoint；
- Toolset Search/Audit Runtime。

下一步进入 `I03-1B｜PostgreSQL Schema 与 Adapter`。
