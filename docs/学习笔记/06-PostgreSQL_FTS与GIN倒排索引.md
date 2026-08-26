# PostgreSQL FTS 与 GIN 倒排索引：从算法到 NexusMCP 实现

> 对应阶段：S2-5｜Catalog PostgreSQL FTS  
> 学习目标：理解 FTS、倒排索引、PostgreSQL GIN 三者的关系，并能把概念映射到 NexusMCP 的
> Migration、ORM、Repository、Use Case 和测试。

## 1. 先给出三层结论

```text
FTS（Full-Text Search）
= 要解决的问题：如何按文本关键词查找相关文档

倒排索引（Inverted Index）
= 常用算法思想：从“文档包含哪些词”反转为“词出现在哪些文档”

GIN（Generalized Inverted Index）
= PostgreSQL 提供的通用倒排索引访问方法
```

因此：

> GIN 可以理解为 PostgreSQL 对倒排索引的通用工程实现；PostgreSQL FTS 可以使用 GIN 加速
> `tsvector @@ tsquery`。

GIN 不只服务 FTS，也可以索引 Array、JSONB、Trigram 等“一个 Item 包含多个 Key”的复合值。

## 2. NexusMCP 为什么需要 FTS

当前 Demo 只有 7 个 Tool：

```text
directory.get_employee
ops.acknowledge_incident
inventory.reserve_stock
...
```

但企业 Catalog 未来可能有数百或数千个 Tool。如果每次把全部 Tool 都送给调用方：

- 数据库和网络传输增加；
- Agent Context 被无关 Tool 占用；
- 人工管理难以定位 Tool；
- 相关性无法排序。

FTS 让调用方执行：

```text
reserve stock
→ inventory.reserve_stock

acknowledge incident
→ ops.acknowledge_incident
```

它解决“找得到”问题，不负责调用 Tool，也不替代 Policy、Approval 或 Credential。

## 3. 正向索引与倒排索引

假设有三份 Tool 文档：

```text
D1: Reserve stock for a warehouse order
D2: Get current stock availability
D3: Acknowledge an operations incident
```

### 3.1 正向结构

普通文档结构是：

```text
Document → Terms

D1 → reserve, stock, warehouse, order
D2 → get, current, stock, availability
D3 → acknowledge, operations, incident
```

如果搜索 `stock`，最直接的算法是遍历每份文档：

```python
for document in documents:
    if "stock" in tokenize(document):
        results.append(document)
```

文档数量越多，每次查询扫描的内容越多。

### 3.2 反转映射方向

倒排索引改成：

```text
Term → Documents

acknowledge  → [D3]
availability → [D2]
incident     → [D3]
order        → [D1]
reserve      → [D1]
stock        → [D1, D2]
warehouse    → [D1]
```

搜索 `stock` 时直接读取：

```text
index["stock"] → [D1, D2]
```

不需要重新扫描 D1、D2、D3 的全文。

### 3.3 Posting List

词条后面的文档/行位置集合叫 Posting List：

```text
stock → [D1, D2]
```

在数据库中通常不是业务 ID，而是能定位 Heap Row 的 Row ID/TID。

通用搜索引擎的 Posting 还可能保存：

- 词频；
- 词语位置；
- 字段；
- 权重；
- 文档长度等。

但 PostgreSQL `tsvector` GIN Index 主要索引 Lexeme 与匹配行位置；Weight Label 不保存在 GIN Entry
中，需要时 PostgreSQL会读取原始 `tsvector` 重新判断或计算 Rank。

## 4. 倒排索引构建算法

概念算法：

```python
inverted_index = {}

for document_id, document in documents:
    terms = normalize(tokenize(document))

    for term in unique(terms):
        inverted_index[term].append(document_id)
```

完整过程通常包含：

```text
Raw Text
→ Parser / Tokenizer
→ Token
→ Dictionary / Normalize
→ Lexeme
→ 去重或记录位置
→ 更新 Posting List
```

例如英文配置可能做词干还原：

```text
reservations
reserving
reserved
→ reserv
```

NexusMCP 当前使用 `simple` Configuration，不进行语言相关 Stemming，主要面向：

- Namespace；
- Canonical Tool Name；
- 英文 Display Name；
- 英文 Tags；
- 英文技术 Description。

## 5. 多关键词查询算法

倒排索引最大的价值是可以操作 Posting List。

### 5.1 AND

查询：

```text
reserve AND stock
```

Posting：

```text
reserve → [D1, D5]
stock   → [D1, D2, D5]
```

求交集：

```text
[D1, D5] ∩ [D1, D2, D5]
→ [D1, D5]
```

如果 Posting List 已排序，可以使用双指针线性求交集：

```python
i = 0
j = 0

while i < len(left) and j < len(right):
    if left[i] == right[j]:
        result.append(left[i])
        i += 1
        j += 1
    elif left[i] < right[j]:
        i += 1
    else:
        j += 1
```

### 5.2 OR

```text
reserve OR availability
→ Posting List 并集
```

### 5.3 NOT

```text
stock NOT audit
→ stock Posting 中排除 audit Posting
```

### 5.4 Phrase

```text
"reserve stock"
```

只知道 D1 同时有两个词还不够，还要查看 Lexeme Position 是否相邻。Position 属于 `tsvector`，GIN
帮助找候选行，PostgreSQL再根据实际向量完成必要判断。

## 6. PostgreSQL FTS 数据结构

### 6.1 tsvector

`tsvector` 是标准化后的文档：

```sql
to_tsvector('simple', 'Reserve stock for a warehouse order')
```

概念结果：

```text
'a':4 'for':3 'order':6 'reserve':1 'stock':2 'warehouse':5
```

它不是普通字符串，而是：

- 已标准化 Lexeme；
- Lexeme Position；
- 可选 Weight Label。

### 6.2 tsquery

查询也要标准化：

```sql
websearch_to_tsquery('simple', 'reserve stock')
```

概念上得到：

```text
'reserve' & 'stock'
```

`websearch_to_tsquery` 支持接近 Web 搜索框的语法：

```text
"reserve stock"   → Phrase
reserve OR stock  → OR
-audit            → NOT
```

### 6.3 @@

匹配操作符：

```sql
search_vector @@ websearch_to_tsquery('simple', :query_text)
```

左侧是文档向量，右侧是查询表达式。

### 6.4 Ranking

匹配只回答 True/False，Rank 回答谁更相关：

```sql
ts_rank_cd(search_vector, tsquery)
```

NexusMCP 按 Rank 降序，再按 Canonical Name 稳定排序。

## 7. GIN 的“Generalized”是什么

GIN 不理解“文章”“Tool”或“员工 API”。它只理解：

```text
Item
= 被索引的复合值，例如一行 tsvector

Key
= 从 Item 中提取的元素，例如 Lexeme "stock"

Posting List
= 包含该 Key 的 Row ID 集合
```

逻辑结构：

```text
Key                    Posting
----------------------------------------
acknowledge         → [TID-3]
inventory           → [TID-1, TID-2]
reserve             → [TID-1]
stock               → [TID-1, TID-2]
```

“Generalized” 的关键是 Operator Class 定义语义：

```text
extractValue
→ 从被索引 Item 中提取 Keys

extractQuery
→ 从查询条件中提取 Query Keys

consistent / triConsistent
→ 根据各 Query Key 是否出现，判断 Row 是否满足或可能满足查询
```

GIN 本身负责 Tree、Concurrency、WAL、Search 等通用工作。

对于 `tsvector_ops`：

```text
Indexed Item = tsvector
Key          = lexeme
Operator     = @@
```

## 8. PostgreSQL GIN 内部算法

官方实现可以简化理解为两层树。

### 8.1 Entry Tree

GIN 内部首先有一棵针对 Key 的 B-tree：

```text
                     [m ...]
                    /       \
          [ack ... inventory] [reserve ... stock]
```

这棵树解决：

> 给定 Lexeme `stock`，快速找到它对应的 Posting。

Leaf Entry 保存：

```text
Key
+ Posting List
```

或：

```text
Key
+ Posting Tree Pointer
```

### 8.2 Posting List

如果某个 Key 只匹配少量 Row，Row ID 集合可以和 Key 一起放在一个 Index Tuple：

```text
reserve → [TID-1, TID-7, TID-20]
```

这叫 Posting List。

### 8.3 Posting Tree

高频词可能匹配大量 Row：

```text
tool → 数十万 TID
```

Posting List 无法塞进一个 Tuple 时，GIN 使用另一棵 B-tree 保存 Heap Pointer：

```text
Entry Tree
└── key = tool
    └── Posting Tree
        ├── TID range 1
        ├── TID range 2
        └── TID range 3
```

因此可以把 GIN 简化成：

```text
Entry Tree：Key → Posting
Posting Tree：当 Posting 很大时，进一步组织 Row ID
```

### 8.4 查询步骤

查询 `reserve stock`：

```text
1. extractQuery 得到 [reserve, stock]
2. Entry Tree 查 reserve
3. Entry Tree 查 stock
4. 读取两个 Posting List/Tree
5. 按 tsquery 语义求交集
6. 得到候选 TID
7. 访问 Heap Row
8. 必要时 Recheck
9. 计算 ts_rank_cd
10. 排序和 Limit
```

GIN 不直接完成业务过滤。NexusMCP 仍要在同一 SQL 中验证 Tenant、Published、Binding 和 Visibility。

## 9. GIN Fast Update 与 Pending List

倒排索引写入比 B-tree 复杂：一行文档可能产生多个 Key。

插入：

```text
inventory.reserve_stock Reserve stock warehouse write
```

可能要分别更新：

```text
inventory
inventory.reserve_stock
reserve
stock
warehouse
write
```

如果每次都立即修改 Entry Tree 和多个 Posting，前台写入会变慢。

GIN 的 `fastupdate` 会先把新 Entry 放入临时、未排序的 Pending List：

```text
New Rows
→ Pending List
→ 后续批量合并 Main GIN Tree
```

触发清理/合并的场景包括：

- `VACUUM`；
- `AUTOVACUUM/ANALYZE`；
- `gin_clean_pending_list()`；
- Pending List 超过 `gin_pending_list_limit`。

优点：

- 多数前台写入更快；
- 可以批量整理 Key/Posting；
- 清理工作可由后台 Autovacuum 执行。

代价：

- 查询还要扫描 Pending List；
- Pending List 太大时查询变慢；
- 恰好触发前台 Cleanup 的那次写入可能突然很慢；
- Autovacuum 配置不当会带来延迟抖动。

如果业务更重视稳定查询延迟而非写入吞吐，可以对 Index 关闭 `fastupdate`，但不能凭感觉调整，应先测量
Pending List、写入量和查询延迟。

NexusMCP Tool Publish 属于低频 Control Plane 写入，所以当前保留 PostgreSQL 默认 `fastupdate` 即可。

## 10. GIN 与 B-tree 的区别

### B-tree

适合一个 Row 对应一个可排序标量 Key：

```text
tenant_id
created_at
canonical_name
version
```

结构：

```text
Value → Row
```

擅长：

- `=`；
- `<` / `>`；
- Range；
- ORDER BY；
- Unique。

### GIN

适合一个 Row 内含很多元素：

```text
tsvector → 很多 Lexeme
jsonb    → 很多 Key/Value
array    → 很多 Element
```

结构：

```text
Element Key → Rows containing the Element
```

不应使用 GIN 取代 `(tenant_id, canonical_name)` B-tree Unique Index。两者解决的问题不同。

## 11. NexusMCP 的 Search Snapshot

实现：[`sqlalchemy_mapping.py`](../../src/nexusmcp/modules/catalog/adapters/sqlalchemy_mapping.py)

ToolVersion Persistence 保存：

```text
search_name
= namespace + canonical_name + display_name

search_tags
= tags

search_description
= description
```

为什么去规范化？

`search_vector` 属于 `tool_version`，但 Namespace/Canonical Name 属于 `tool`。PostgreSQL Generated Column
不能跨表读取另一个 Row，因此 Repository 在创建 Version 时形成搜索快照。

这也符合 Version 语义：

> 一次 Published Version 的可发现文档应当稳定，不应因后续动态 Join 产生不可追踪变化。

这些字段不进入 Domain Entity，只属于 Persistence Adapter。

## 12. Weighted Generated tsvector

ORM：[`sqlalchemy_models.py`](../../src/nexusmcp/modules/catalog/adapters/sqlalchemy_models.py)

Migration：
[`9a41d8e62f7b_add_tool_catalog_fts.py`](../../migrations/versions/9a41d8e62f7b_add_tool_catalog_fts.py)

权重：

```text
search_name        → A
search_tags        → B
search_description → C
```

概念 SQL：

```sql
setweight(to_tsvector('simple', search_name), 'A') ||
setweight(to_tsvector('simple', search_tags), 'B') ||
setweight(to_tsvector('simple', search_description), 'C')
```

`search_vector` 是 Stored Generated Column：

- Application 不手工计算 `tsvector`；
- Search Text 变化时 PostgreSQL 自动重算；
- 数据库保证 Vector 与三个文本字段一致；
- GIN Index 直接索引生成结果。

## 13. Migration 为什么需要 Backfill

数据库升级前已经可能有 ToolVersion。

Migration 不能直接新增非空 Search 字段而不给旧 Row 赋值，所以执行：

```text
1. 添加 Search Text 字段
2. JOIN tool 回填 Namespace/Canonical Name
3. 展开 tags_json 回填 Tags
4. 回填 Description
5. 添加 Generated search_vector
6. 创建 GIN Index
```

Integration Test 会先停在旧 Revision，插入旧 Version，再 Upgrade Head，验证旧数据也能被搜索。

## 14. SearchPublishedTools

Use Case：[`search.py`](../../src/nexusmcp/modules/catalog/search.py)

Adapter：[`sqlalchemy_search.py`](../../src/nexusmcp/modules/catalog/adapters/sqlalchemy_search.py)

输入：

```text
RequestContext
text
limit
```

校验：

- Trim 后非空；
- 最长 200；
- Limit 1～50。

Application 根据 Principal 得出 Visibility：

```text
anonymous     → public
authenticated → public + authenticated
restricted    → S3 Policy 前 Fail Closed
```

概念 SQL：

```sql
SELECT tool, version,
       ts_rank_cd(version.search_vector, query) AS rank
FROM tool
JOIN tool_version AS version
JOIN tool_binding AS binding
WHERE tool.tenant_id = :tenant_id
  AND version.tenant_id = :tenant_id
  AND binding.tenant_id = :tenant_id
  AND tool.status = 'active'
  AND version.status = 'published'
  AND binding.status = 'published'
  AND version.visibility IN (:allowed_visibilities)
  AND version.search_vector @@ query
ORDER BY rank DESC, tool.canonical_name
LIMIT :limit;
```

治理过滤必须在 SQL Rank/Limit 前完成，否则会出现：

- Top 10 中包含其他 Tenant；
- 内存过滤后不足 10 个；
- Restricted 候选进入 Application；
- Draft/Disabled 干扰排名。

## 15. 排名实例

测试数据：

```text
inventory.reserve_stock
display_name = Reserve stock
→ stock 命中 Name，Weight A

inventory.get_status
description = Inspect current stock availability
→ stock 只命中 Description，Weight C
```

搜索 `stock`：

```text
1. inventory.reserve_stock
2. inventory.get_status
```

需要注意：PostgreSQL 官方说明 GIN 对 FTS 只保存 Lexeme，不保存 Weight Label。因此 GIN 负责快速找候选
Row，涉及 Weight/Ranking 时仍会读取实际 `tsvector` 完成计算或 Recheck。

## 16. 性能与工程权衡

### 优点

- PostgreSQL 原生能力，无新服务；
- 事务与 Catalog 状态一致；
- GIN 对关键词查找高效；
- Tenant/Lifecycle/Visibility 可在同一 SQL 过滤；
- 可解释，测试简单。

### 成本

- 每次 Version 写入要更新多个 Lexeme；
- GIN 占用额外磁盘；
- Pending List 需要 Autovacuum 维护；
- Rank 通常仍需处理候选 Row；
- 高频词可能产生很大的 Posting Tree；
- `simple` 不解决中文分词、同义词和拼写错误。

### 为什么当前不用 Elasticsearch

当前 Catalog 数据量小，PostgreSQL 已经是事实源。增加 Elasticsearch/OpenSearch 会引入：

- 双写/同步；
- 索引一致性；
- 新部署和监控；
- 额外故障边界。

没有真实规模证据前，PostgreSQL FTS 更合适。

### 为什么当前不用 pgvector

FTS 解决关键词匹配，Vector Search 解决语义相似：

```text
FTS: "reserve stock" ↔ 文档中明确出现 reserve/stock
Vector: "hold products for order" ↔ stock reservation
```

只有在固定 Eval 上证明语义搜索显著优于 FTS，才值得引入 Embedding/pgvector。

## 17. 如何阅读实现

推荐顺序：

1. [`12_S2-5_CatalogPostgreSQLFTS.md`](../实验记录/12_S2-5_CatalogPostgreSQLFTS.md)
2. [`9a41d8e62f7b_add_tool_catalog_fts.py`](../../migrations/versions/9a41d8e62f7b_add_tool_catalog_fts.py)
3. [`sqlalchemy_models.py`](../../src/nexusmcp/modules/catalog/adapters/sqlalchemy_models.py)
4. [`sqlalchemy_mapping.py`](../../src/nexusmcp/modules/catalog/adapters/sqlalchemy_mapping.py)
5. [`search.py`](../../src/nexusmcp/modules/catalog/search.py)
6. [`sqlalchemy_search.py`](../../src/nexusmcp/modules/catalog/adapters/sqlalchemy_search.py)
7. [`test_postgresql_fts_migration.py`](../../tests/integration/persistence/test_postgresql_fts_migration.py)
8. [`test_postgresql_fts_search.py`](../../tests/integration/persistence/test_postgresql_fts_search.py)

## 18. 最后记住

```text
FTS 是需求
倒排索引是算法思想
GIN 是 PostgreSQL 的通用倒排索引访问方法
tsvector 是文档
tsquery 是查询
@@ 是匹配
ts_rank_cd 是排名
```

在 NexusMCP 中：

> GIN 只负责快速找出文本候选；Tenant、生命周期、Visibility 和 Published Binding 仍然是不可省略的
> 业务治理条件。

## 19. 官方参考

- [PostgreSQL 18｜Full Text Search](https://www.postgresql.org/docs/18/textsearch.html)
- [PostgreSQL 18｜Text Search Functions and Operators](https://www.postgresql.org/docs/18/functions-textsearch.html)
- [PostgreSQL 18｜Preferred Index Types for Text Search](https://www.postgresql.org/docs/18/textsearch-indexes.html)
- [PostgreSQL 18｜GIN Indexes](https://www.postgresql.org/docs/18/gin.html)
