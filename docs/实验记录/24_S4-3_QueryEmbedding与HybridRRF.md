# S4-3｜Query Embedding、Exact Vector Search 与 Hybrid RRF 验收

> 日期：2026-08-26
> 状态：完成
> 范围：Query Embedding、pgvector Exact Search、RRF、Hybrid 编排与 Meta Tool 接入

## 1. 纵向链路

```text
nexus.search_tools(retrieval_mode="hybrid")
→ SearchTools：计算 Over-fetch Candidate Limit
→ SearchHybridTools
   ├── PostgreSQL Weighted FTS
   └── SiliconFlow Query Embedding → PostgreSQL pgvector Exact Cosine Search
→ Reciprocal Rank Fusion
→ Principal/Policy Filter
→ Final Top-K + Full Tool Schema
```

Query Embedding 使用与 Reindex 相同的 `EmbeddingProvider`、Model 和 Dimensions。Query Vector 只服务
当前请求，不进入 `tool_search_embedding`；Projection Table 只保存 Published Tool Document Vector。

## 2. Exact Vector Search

新增 `VectorToolSearch` Port 与 `SqlAlchemyExactVectorToolSearch` Adapter。SQL 在计算距离前约束：

- Tenant；
- Active Tool；
- Published ToolVersion 与 ToolBinding；
- Public/Authenticated Visibility；
- 可选 Namespace 与 Side Effect；
- Embedding Model 与 Dimensions。

第一版使用 Cosine Exact Scan，不创建 HNSW/IVFFlat。结果按 Distance 升序，同距离按 Canonical Name
稳定排序；内部 Vector Hit 的 Rank 表达 `1 - cosine_distance`，RRF 只使用它产生的顺序。

## 3. Index Coverage 边界

Vector Adapter 同时返回当前 Filter Scope 的 Eligible Count 与 Indexed Count：

- Eligible 为 0：正常返回空结果；
- Eligible 大于 0 且 Indexed 为 0：返回 `tool_search_mode_unavailable`；
- Partial Coverage：第一版继续检索，不伪造完整覆盖，交由 S4-4 Eval 量化风险。

这个边界避免“完全没有 Vector Projection 却把 FTS 结果冒充 Hybrid”，同时避免一次新 Tool 尚未 Reindex
就让整个 Tenant 的 Hybrid 全部不可用。

## 4. RRF

实现无数据库依赖的 `ReciprocalRankFusion`：

```text
score(tool) = Σ 1 / (60 + rank_in_strategy)
```

- 不相加 `ts_rank` 与 Cosine Similarity；
- 按 `tool_version_id` 跨策略合并；
- 同一策略重复行只计第一次；
- 最终并列按 Canonical Name、Tool Version ID 排序；
- FTS 与 Vector Candidate 通过 `asyncio.gather` 并发获取。

## 5. 治理顺序

```text
SQL Static Scope
→ FTS/Vector Candidate
→ RRF
→ Dynamic Policy Filter
→ Final Top-K
```

`SearchTools` 先把最终 Limit 放大 4 倍，最大 50；Policy Deny Candidate 被过滤后再截取最终 Limit，避免
不可见候选挤占合法 Top-K。Search 不返回 Restricted/Cross-Tenant Tool。

## 6. MCP Contract

公共协议没有新增模式：

```text
retrieval_mode = lexical | hybrid
```

Vector-only 只保留给内部 Eval。Hybrid Result `_meta` 增加：

```text
com.nexusmcp/searchStrategyUsed = hybrid
com.nexusmcp/candidateCount = n
com.nexusmcp/indexVersion = Qwen/Qwen3-Embedding-8B@2048
```

`indexVersion` 诊断当前 Query 与 Projection 的模型契约，不向 Agent 暴露 Provider Key、Vector 或完整
Query。

## 7. 验收证据

- Query Text Trim、单 Vector Count/Model/Dimensions Contract；
- PostgreSQL 2048 维 Exact Cosine 排名；
- Tenant、Lifecycle、Binding、Visibility、Namespace、Side Effect Filter；
- 跨 Tenant 候选即使最相似也不泄漏；
- 零 Index Coverage 稳定失败；
- RRF Raw Score 隔离、去重、`k=60` 与稳定 Tie-break；
- Fusion 后 Dynamic Policy Filter；
- 正式 MCP Search-First 模式调用 Hybrid，返回 Full Schema 与 Index Version；
- Ruff、basedpyright、全量测试、Alembic Drift 与 Build 门禁。

## 8. 下一步

进入 `S4-4｜Retrieval Eval 与 S4 收口`：使用现有 8 个 Demo Tool 和 Eval Cases 对比 FTS-only、
Vector-only、Hybrid 的 Top-1、Hit@K、MRR、nDCG、Latency、Cost 与 Unauthorized Leakage。
