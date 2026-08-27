# S4-2b｜Tool Embedding Reindex Pipeline 验收

> 日期：2026-08-27
> 状态：完成
> 范围：Canonical Document、EmbeddingProvider、SiliconFlow Adapter、Repository/UoW 与 Reindex CLI

## 1. 模块边界

S4 Search 从 Catalog 中拆为独立模块化单体 Module：

```text
Catalog
→ 提供 PublishedTool Projection

Tool Search
→ Document / Embedding / Reindex / Retrieval
```

`tool_search` 可以依赖 Catalog Public Domain/Port；Catalog、Execution、Registry 不反向依赖 Tool
Search。SiliconFlow/httpx/pgvector 只出现在 Tool Search Adapter。

## 2. Canonical Document

每条 Published ToolVersion 构建稳定文本：

```text
Canonical Name
Display Name
Namespace
Normalized Description
Sorted Tags
Side Effect
Flattened Input Field Summary
Owner
```

Nested Body Field 使用 `body.warehouse_id` 等 Path，包含 Type、Required/Optional 和安全 Description。
不复制完整 JSON Schema，也不加入 Examples/Defaults/Upstream URL/Secret。

Canonical Content 使用 SHA-256 得到 `source_digest`；内容相同则不重新生成向量。

## 3. EmbeddingProvider Port

Application 只依赖：

```text
model
dimensions
embed(tuple[text]) → tuple[EmbeddingVector]
```

`EmbeddingVector` 验证 Model、Dimension、Count 和所有数值有限。普通单元测试使用 Fake Provider，不
访问网络或产生费用。

## 4. SiliconFlow Adapter

Adapter 发送 Batch：

```text
model=Qwen/Qwen3-Embedding-8B
dimensions=2048
encoding_format=float
```

并归一化：

- 401/403 → Authentication Error；
- 429 → Rate Limit；
- Timeout/Network/5xx → Unavailable；
- 非 JSON、Count/Index/Dimension/Value 异常 → Invalid Response。

Key 使用 `SecretValue`，错误、Repr 和测试输出不包含 Key、完整 Text 或 Vector。

## 5. Repository 与 UoW

Scope：

```text
tenant_id
+ tool_version_id
+ embedding_model
+ embedding_dimensions
```

Repository 读取当前 Projection，并通过 PostgreSQL `ON CONFLICT DO UPDATE` 更新 Source Digest、Vector
和 Indexed Time；保留原 Projection ID。每个 Embedding Batch 使用独立短事务。

## 6. Reindex Use Case

```text
List Published Tools
→ Build Documents
→ Read Existing Projection Scope
→ Missing/Stale/Force Filter
→ Batch Embed
→ Upsert + Commit
→ Statistics
```

中途失败可能已提交前面 Batch，但重复运行会从 Digest 状态继续，不重复生成已经 Current 的 Vector。

## 7. CLI

```powershell
uv run nexusmcp reindex-tools --dry-run
uv run nexusmcp reindex-tools
uv run nexusmcp reindex-tools --force --batch-size 8
```

安全输出只包含 Published/Current/Pending/Embedded/Batch Count、Model、Dimensions 和 Dry Run。

真实验证：

```text
第一次：Published=1, Pending=1, Embedded=1, Batches=1
第二次：Published=1, Current=1, Pending=0, Embedded=0, Batches=0
```

## 8. 验收证据

- Canonical Document 确定性和 Semantic Change Digest；
- SiliconFlow Batch 顺序、错误归一化、Wrong Dimension/NaN；
- InMemory Reindex 的首次、重复、Stale、Dry Run；
- PostgreSQL Upsert 保留 ID 并更新 Digest；
- 真实 SiliconFlow Adapter External Smoke；
- 真实 CLI 首次索引与二次零调用；
- pgvector 2048 Round-Trip 与 Exact Cosine Test；
- 完整质量门禁。

## 9. 当前边界

- 尚未实现 Query Embedding/Vector Search；
- `hybrid` 仍返回 `tool_search_mode_unavailable`；
- 不建立 HNSW/IVFFlat；
- 不实现后台 Worker、Outbox、Retry 或实时 Index Freshness；
- 不删除 Retired Tool 的历史 Projection；
- 不做 Auto、Rerank 或 Tool 多 Chunk。

## 10. 下一步

进入 `S4-3｜Exact Vector Search 与 Hybrid RRF`：对 Agent Query 调用同一 EmbeddingProvider，按 Model、
Dimension、Tenant 和 Published Tool 过滤执行 Cosine Search，再与 FTS Candidate 使用 RRF 融合。
