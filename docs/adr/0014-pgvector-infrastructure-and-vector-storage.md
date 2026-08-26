# ADR-0014｜PostgreSQL 18 pgvector 基础设施与 Vector Storage

> 状态：Accepted  
> 日期：2026-08-26

## Context

S4 Hybrid Tool Retrieval 需要保存 Tool Embedding 并执行 Cosine Nearest Neighbor Search。项目已经使用
PostgreSQL 18.6、SQLAlchemy Async 和 asyncpg；单独引入 Qdrant/Milvus 会增加部署、事务和状态所有权
复杂度。当前在线模型 `Qwen/Qwen3-Embedding-8B` 已通过 SiliconFlow Smoke Test 返回 2048 维向量。

pgvector 可以存储 2048 维 `vector`，但普通 Float32 `vector` 的 HNSW/IVFFlat 索引最多支持 2000 维；
`halfvec` 索引支持到 4000 维。因此 2048 维可以 Exact Search，但不能直接建立普通
`vector_cosine_ops` HNSW。

## Decision

1. NexusMCP 继续使用一个 PostgreSQL，不引入独立 Vector Database。
2. Local/CI 镜像固定为 `pgvector/pgvector:0.8.6-pg18-trixie`，不使用 Floating Tag。
3. PostgreSQL Major 固定为 18；镜像 Digest 可在发布/供应链阶段进一步固定。
4. 通过 Alembic 执行 `CREATE EXTENSION IF NOT EXISTS vector`，而不是启动脚本静默创建业务 Schema。
5. Python 使用 `pgvector` 官方 SQLAlchemy Type；SQLAlchemy `VECTOR` 自带 Text Bind/Result Processor，
   不在同一连接上重复注册 asyncpg Binary Codec。只有绕过 SQLAlchemy、直接使用 asyncpg 时才调用
   `pgvector.asyncpg.register_vector`。
6. 第一版 Tool Embedding 使用 `VECTOR(2048)` 保存 SiliconFlow Float32 输出。
7. 相似度使用 Cosine Distance（PostgreSQL `<=>`）。
8. 第一版不建立 Approximate Index，使用 Exact Search 获得完整 Recall 和正确性 Baseline。
9. 只有 500～2000+ 合成/真实 Tool Benchmark 证明需要时才增加 HNSW。
10. 2048 维后续 HNSW 优先使用 `embedding::halfvec(2048)` Expression Index，并在需要时用原始
    `VECTOR(2048)` 重新排序；也可以由 Eval 决定把模型维度降到 1536 后使用普通 Vector HNSW。
11. `vector` Extension 属于 Database Infrastructure；普通 Down Migration 删除项目表，但不默认
    `DROP EXTENSION ... CASCADE`。
12. 切换镜像不删除现有 Volume；先验证同 Major 数据目录和 Extension，再决定是否重建开发数据。

## Initial Projection

```text
ToolSearchEmbedding
- id
- tenant_id
- tool_version_id
- embedding_model
- embedding_dimensions = 2048
- source_digest
- embedding VECTOR(2048)
- indexed_at
```

Embedding 是 Published ToolVersion 的可重建 Search Projection，不承担 Tool Lifecycle 所有权。

## Rejected Alternatives

- 为 Tool Catalog 引入独立 Qdrant/Milvus/Weaviate；
- 继续使用不含 pgvector 的普通 PostgreSQL 镜像并在运行时临时编译；
- 使用 Floating `pg18`/`latest` Tag；
- 在 8 个 Tool 上直接建立 HNSW 并宣称性能提升；
- 对 2048 维 Float32 Vector 直接建立不受支持的普通 HNSW；
- 为了索引方便未经 Eval 直接把模型维度改成 1536；
- Down Migration 自动级联删除整个 Vector Extension。

## Consequences

- pgvector Debian Trixie 镜像大于原 Alpine 镜像，但减少自定义编译与兼容维护；
- Exact Search 适合当前规模，HNSW 学习与 Benchmark 延后但不阻塞 Semantic Retrieval；
- 2048 维原始 Float32 Vector 每行约 8 KiB（不含 Row/Index Overhead）；
- SQLAlchemy 与 asyncpg 的 Vector Codec 不能重复注册，否则 List 会先被 SQLAlchemy 转成 Text，再被
  Binary Codec 当作 List 二次编码；Round-Trip Test 固定该 Adapter 边界；
- Migration User 需要创建 Extension 的数据库权限；
- 更换 Embedding Model/Dimension 需要 Reindex，并可能需要 Schema Migration 或平行 Projection。

## Verification

- Compose 使用固定 pgvector PostgreSQL 18 Tag；
- `SELECT extversion FROM pg_extension WHERE extname='vector'` 返回 0.8.6；
- Alembic Upgrade 可重复执行且无 Schema Drift；
- SQLAlchemy + asyncpg 写入并读回 2048 个有限浮点数；
- Exact Cosine Query 返回预期最近 Tool；
- 原有 PostgreSQL Integration Test 全部通过；
- 切换镜像后现有 Volume、`nexusmcp` 与 `nexusmcp_test` Database 均可用。
