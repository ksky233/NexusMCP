# S2-5｜Catalog PostgreSQL FTS 验收

> 日期：2026-08-26  
> 范围：Search Snapshot、Weighted `tsvector`、GIN Index、Migration Backfill、
> SearchPublishedTools、Tenant/Lifecycle/Visibility、Ranking Integration Test

## 1. 目标

当企业 Catalog 从 7 个 Tool 增长到数百或数千个时，调用方需要按关键词找到相关 Published Tool，而
不是把整个 Catalog 送入上下文。

```text
SearchPublishedToolsQuery
→ Tenant + Principal Visibility
→ PostgreSQL websearch_to_tsquery
→ GIN / @@ Match
→ ts_rank_cd
→ PublishedToolSearchHit[]
```

FTS 是 Catalog Core 能力，不是新的 Demo 系统。

## 2. Search Snapshot

ToolVersion Persistence 增加三个去规范化文本字段：

```text
search_name
= namespace + canonical_name + display_name

search_tags
= tags

search_description
= description
```

Repository Mapping 在新增/保存 Version 时维护这些字段。Domain `ToolVersion` 不包含 PostgreSQL Search
类型，MCP Published Contract 也不暴露内部 Search Vector。

Tool Identity 的 Namespace/Canonical Name 在版本中形成搜索快照，符合 Published Version 不原地改变的
原则。

## 3. Weighted tsvector

PostgreSQL Stored Generated Column：

```text
search_name        → Weight A
search_tags        → Weight B
search_description → Weight C
```

概念表达式：

```sql
setweight(to_tsvector('simple', search_name), 'A') ||
setweight(to_tsvector('simple', search_tags), 'B') ||
setweight(to_tsvector('simple', search_description), 'C')
```

名称直接命中的 Tool 应排在只在 Description 中提到关键词的 Tool 前面。

选择 `simple`：

- Tool Name/Namespace/Tags 以英文技术标识为主；
- 不删除英文 Stop Word；
- 不在当前阶段引入语言相关 Stemming；
- 中文分词、`pg_trgm`、pgvector 留给有真实数据和 Eval 后再决策。

## 4. GIN Index 与 Migration

Migration `9a41d8e62f7b`：

1. 新增三个 Search Text 字段；
2. 从 Tool + ToolVersion + Tags JSONB Backfill 既有 Version；
3. 新增 Stored Generated `search_vector`；
4. 创建 `ix_tool_version_search_vector_gin`。

真实 Migration Test 从 FTS 前一个 Revision 插入旧 ToolVersion，再 Upgrade Head，证明：

- Name/Tags/Description 被正确 Backfill；
- Generated Vector 含预期 Lexeme；
- Index Definition 使用 `USING gin`；
- Downgrade/Upgrade 链仍可执行。

## 5. Application Query 与 Port

```text
SearchPublishedToolsQuery
├── RequestContext
├── text
└── limit

PublishedToolSearch
└── search_published(tenant, text, visibilities, limit)

PublishedToolSearchHit
├── PublishedTool
└── rank
```

输入约束：

- Trim 后不能为空；
- 最长 200 字符；
- Limit 1～50；
- 使用 Bind Parameter 进入 `websearch_to_tsquery`，不拼接用户 SQL。

## 6. Visibility 与治理过滤

Application 根据 Principal 推导允许的粗粒度 Visibility：

```text
Anonymous     → public
Authenticated → public + authenticated
Restricted    → S3 Policy 接入前 Fail Closed
```

SQL 必须同时满足：

```text
Tool Tenant = Request Tenant
Version Tenant = Request Tenant
Binding Tenant = Request Tenant
Tool = active
Version = published
Binding = published
Version Visibility IN allowed
search_vector @@ tsquery
```

先在 SQL 中过滤治理条件，再 Rank/Limit，避免“先取 Top 10，再在内存中过滤”导致结果不足或跨 Tenant
候选进入应用层。

## 7. Ranking 证据

测试数据中：

```text
inventory.reserve_stock
→ stock 命中 Name（A）

inventory.get_status
→ stock 只命中 Description（C）
```

搜索 `stock` 时 `reserve_stock` Rank 更高。Integration Test 同时证明：

- Draft 不返回；
- Disabled Tool 不返回；
- Restricted 不返回；
- Anonymous 看不到 Authenticated；
- Authenticated 可以看到 Authenticated；
- Cross-Tenant 不返回；
- Limit 在数据库查询中生效。

## 8. 当前 Interface 边界

S2-5 提供 Application Query/Port 与 PostgreSQL Adapter，但不发明非标准 MCP `tools/search` 方法。

后续可以由：

- Admin REST/CLI；
- 内部 Tool Selection；
- RAG/Agent Catalog Gateway；

调用同一个 `SearchPublishedTools`。标准 MCP `tools/list` 继续保持原协议行为。

## 9. 有意不做

- 中文分词扩展；
- Typo/Fuzzy Search；
- Synonym Dictionary；
- Highlight/Snippet；
- pgvector/Embedding；
- Search Cache；
- 外部 Elasticsearch/OpenSearch；
- 非标准 MCP Search Method。

## 10. 代码位置

```text
migrations/versions/9a41d8e62f7b_add_tool_catalog_fts.py
src/nexusmcp/modules/catalog/domain.py
src/nexusmcp/modules/catalog/ports.py
src/nexusmcp/modules/catalog/search.py
src/nexusmcp/modules/catalog/adapters/sqlalchemy_models.py
src/nexusmcp/modules/catalog/adapters/sqlalchemy_mapping.py
src/nexusmcp/modules/catalog/adapters/sqlalchemy_search.py
tests/unit/modules/catalog/test_search_published_tools.py
tests/integration/persistence/test_postgresql_fts_migration.py
tests/integration/persistence/test_postgresql_fts_search.py
```

## 11. 下一步

进入 `S2-6｜S2 收口与 Control Plane 接缝`：

1. 复核 S2 路书所有验收项；
2. 补 Registry Register/Update/Disable Application Use Case；
3. 为 Import/Review/Publish/Search 建立最小 CLI 或 Admin REST 调用接缝；
4. 不建设复杂 UI；
5. 完成 S2 总验收后再进入 S3 Gateway/Policy/Credential/Execution。

以上内容已在
[S2-6 S2 收口与 Control Plane 接缝](./13_S2-6_S2收口与ControlPlane接缝.md)
完成。
