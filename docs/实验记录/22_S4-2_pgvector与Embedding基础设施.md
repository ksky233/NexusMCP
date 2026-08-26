# S4-2a｜pgvector 与 Embedding API 基础设施验收

> 日期：2026-08-26  
> 状态：完成  
> 范围：SiliconFlow Connectivity、PostgreSQL 18 pgvector、VECTOR(2048) Projection 与 Exact Search

## 1. Embedding API

配置统一为：

```text
NEXUSMCP_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B
NEXUSMCP_EMBEDDING_DIMENSIONS=2048
NEXUSMCP_EMBEDDING_API_URL=https://api.siliconflow.cn/v1/embeddings
NEXUSMCP_EMBEDDING_API_KEY=<Secret，仅 .env>
```

显式 External Smoke Test 结果：

```text
batch=2
dimensions=2048
total_tokens=39
HTTP 200
```

外部测试默认跳过，只有 `NEXUSMCP_RUN_EXTERNAL_TESTS=1` 才产生网络请求和费用。真实 Key 不进入
`.env.example`、日志或测试输出。

## 2. PostgreSQL Image

Compose 从：

```text
postgres:18.6-alpine
```

切换为：

```text
pgvector/pgvector:0.8.6-pg18-trixie
```

使用 `docker compose up -d --force-recreate postgres` 重建 Container，但未删除
`nexusmcp_postgres_data` Volume。启动日志确认 Existing Database 被复用，没有重新初始化。

实际版本：

```text
PostgreSQL 18.6 (Debian 18.6-1.pgdg13+2)
pgvector 0.8.6
```

`nexusmcp` 与 `nexusmcp_test` 两个 Database 均成功启用 Extension。

## 3. Migration 与 Projection

Migration `f6b8d0e32c47`：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

并创建第 12 张业务表：

```text
tool_search_embedding
- id / tenant_id / tool_version_id
- embedding_model
- embedding_dimensions = 2048
- source_digest
- embedding VECTOR(2048)
- indexed_at
```

Down Migration 删除 Projection 表但不执行 `DROP EXTENSION ... CASCADE`，避免误删其他 Vector
Projection。

## 4. Search Baseline

第一版：

```text
Distance = Cosine
Execution = Exact Scan
Approximate Index = None
```

2048 维可以存储和 Exact Search，但普通 Float32 Vector HNSW 最多支持 2000 维。只有规模 Benchmark
证明需要时，才评估：

- 降到 VECTOR(1536) + 普通 HNSW；
- 保留 VECTOR(2048) + HALFVEC(2048) Expression HNSW；
- Approximate Candidate 后使用原始 Vector Re-rank。

## 5. Adapter 问题与修正

首次测试同时使用：

```text
pgvector.sqlalchemy.VECTOR Bind Processor
+ pgvector.asyncpg Binary Codec
```

导致 Vector 被重复编码：SQLAlchemy 先把 `list[float]` 转成 Text，Binary Codec 又把 Text 当作 List。
最终边界为：

- SQLAlchemy 路径只使用 `pgvector.sqlalchemy.VECTOR` Type Processor；
- 不在同一 SQLAlchemy/asyncpg Connection 上重复注册 Binary Codec；
- 只有直接使用原生 asyncpg API 时才执行 `pgvector.asyncpg.register_vector`。

## 6. 验收证据

- Compose 固定 Image Tag；
- Existing PostgreSQL 18 Volume 无损复用；
- 两个 Database Extension Version 都是 0.8.6；
- Alembic Upgrade 成功；
- SQLAlchemy + asyncpg 写入两个 2048 维 Vector；
- `vector_dims()` 返回 2048；
- Exact Cosine Query 返回预期最近记录；
- Round-Trip 返回 2048 个有限浮点数；
- 原有 Persistence Integration Test 将在完整门禁中回归。

## 7. 下一步

进入 `S4-2b`：实现 Canonical Tool Search Document、EmbeddingProvider Port、SiliconFlow Adapter、
ToolEmbedding Repository 和可重复 Reindex CLI。仍不建立 HNSW。
