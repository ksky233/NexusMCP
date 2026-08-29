# 内建 Meta Tool 与 Hybrid Tool Search 设计

> 状态：S4 实现输入已冻结  
> 日期：2026-08-26  
> 范围：`nexus.search_tools`、Lexical/Hybrid Retrieval、Tool Embedding Projection、Eval 与动态激活接缝

## 1. 业务定位

NexusMCP 不内置 Agent。外部 MCP Host/Agent 接收用户自然语言，先调用始终可见的
`nexus.search_tools` 缩小候选，再由 Agent 结合上下文选择、获取 Schema 并调用业务 Tool。

```text
User Natural Language
→ External Agent Intent Understanding
→ nexus.search_tools
→ Top-K Visible Tool Metadata
→ Agent Final Selection
→ Activate Candidate Tool Schema
→ tools/call
→ Policy/Approval/Credential/Execution/Audit
```

Tool Search 只搜索“应该使用哪个 Tool”。SKU、Employee ID、Incident ID 等实体值属于后续业务 Tool
Arguments，不由 Tool Catalog Search 查询。

## 2. Built-in Meta Tool 与 Managed Tool

| 维度 | Built-in Meta Tool | Catalog Managed Tool |
|---|---|---|
| 示例 | `nexus.search_tools` | `inventory.get_status` |
| 来源 | NexusMCP 应用代码 | OpenAPI/MCP Upstream Import |
| Namespace | 保留 `nexus.*` | Tenant 业务 Namespace |
| ToolVersion/Publish | 随应用版本 | Control Plane Review/Publish |
| ToolBinding/Upstream | 无 | 有 |
| Credential Injection | 无 | 按 Binding |
| Authentication/Tenant/Policy | 有 | 有 |
| Execution Connector | 内部 Search Use Case | 当前为 HTTP Connector |
| Trace/Audit/Rate Limit | 有 | 有 |

Meta Tool 不写入 Catalog 伪装成普通 Tool，避免形成“搜索 Catalog 的 Tool 本身又依赖 Catalog 才能被
发现”的自举循环。`tools/list` 在 Search-First 模式下始终返回内建 Meta Tool 与少量 Pinned Tool。

## 3. Agent-facing Contract

第一版只暴露一个 Meta Tool：

```json
{
  "name": "nexus.search_tools",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "minLength": 1, "maxLength": 500},
      "retrieval_mode": {
        "type": "string",
        "enum": ["lexical", "hybrid"]
      },
      "limit": {"type": "integer", "minimum": 1, "maximum": 20},
      "namespace": {"type": ["string", "null"]},
      "side_effect": {"type": ["string", "null"]}
    },
    "required": ["query", "retrieval_mode"],
    "additionalProperties": false
  }
}
```

`retrieval_mode` 必填，不提供 Auto Default：

- `lexical`：用户意图包含明确名称、Namespace、Tags、缩写、代码或领域关键词；
- `hybrid`：用户表达模糊、同义、跨语言，或 Lexical 候选为空/不合适。

Agent 可以先 Lexical，再根据结果自主发起 Hybrid。NexusMCP 不在第一版重新实现 Agent 已经具备的
Query Routing 能力。

## 4. 内部 Retrieval Strategy

Application 层可保留三种 Strategy，用于实现和 Eval：

```text
FTS_ONLY      → Agent-facing lexical
VECTOR_ONLY   → Internal Eval/Ablation only
HYBRID        → Agent-facing hybrid
```

`AUTO` 不进入第一版。未来只有在 Agent 模式选择错误率、重复 Round Trip、Embedding Cost 等指标证明
需要时再新增，并且不应静默改变公共契约。

候选流：

```text
Lexical
→ PostgreSQL Weighted FTS
→ Filtered Top-K

Hybrid
├── PostgreSQL Weighted FTS Candidates
├── pgvector Cosine Candidates
└── Rank Fusion
    → Governance Filter
    → Final Top-K
```

首版使用 Reciprocal Rank Fusion：

```text
RRF Score(tool) = Σ 1 / (k + rank_in_strategy)
```

不直接相加 `ts_rank` 与 Cosine Similarity，因为二者量纲和分布不可直接比较。

## 5. Tool Search Document 与 Embedding Projection

普通 Tool 信息较短，第一版不做多 Chunk：

```text
One Published ToolVersion
→ One Canonical ToolSearchDocument
→ One Embedding per Model Version
```

Canonical Document 示例：

```text
Canonical Name: inventory.set_reorder_level
Display Name: Set reorder level
Namespace: inventory
Description: Set the desired reorder level for one SKU and warehouse.
Tags: inventory, warehouse, write, idempotent
Side Effect: idempotent_write
Inputs: sku, warehouse_id, reorder_level
Owner: inventory-platform
```

不直接 Embedding 完整 JSON Schema。结构关键字、重复类型声明和约束会增加噪声；第一版只提取稳定
Field Name/Description Summary。

建议 Projection：

```text
ToolSearchEmbedding
- id
- tenant_id
- tool_version_id
- embedding_model
- embedding_dimensions
- source_digest
- embedding vector(n)
- indexed_at
```

Embedding 与 FTS Search Document 都是 Published Catalog 的可重建 Projection，不反向拥有 ToolVersion
Lifecycle。

## 6. Indexing Flow

禁止在 Publish 数据库事务中调用 Embedding Provider：

```text
Publish Transaction
→ Commit ToolPublished
→ Search Projection Pending
→ CLI/Reindex Job
→ Build Canonical Document
→ EmbeddingProvider.embed(document)
→ Upsert ToolSearchEmbedding by Source Digest
```

S4 第一版使用显式 CLI/Reindex Job。实时 Outbox/Worker 只有在 Tool 更新频率和 Index Freshness 指标证明
需要时再实现。

## 7. 模块与 Port

建议 Application/Port：

```text
SearchTools
├── LexicalToolSearch Port
├── VectorToolSearch Port
├── ToolSearchDocumentBuilder
├── RankFusion
└── ToolSearchPolicyFilter

EmbeddingIndexTools
├── PublishedToolProjectionReader
├── EmbeddingProvider Port
└── ToolEmbeddingRepository
```

MCP Adapter 只负责 Meta Tool Schema 和 Result 映射，不 import SQLAlchemy/pgvector/Embedding SDK。
Vector-only Strategy 不出现在 Agent-facing Schema，但 Eval 可以直接调用 Application Query。

## 8. 安全与治理顺序

Search 不能成为 Catalog 侧信道：

```text
Resolve Internal Principal
→ Tenant Scope
→ Published/Active Filter
→ Visibility Filter
→ Search Policy Filter
→ Lexical/Vector Candidate Retrieval（带静态 SQL Filter）
→ Over-fetch + Dynamic Policy Filter
→ Top-K
→ Safe Metadata Result
```

动态 Policy 无法完全下推 SQL 时，需要 Over-fetch 后过滤；不能先取全局 Top-K 再过滤，否则合法候选
可能被隐藏候选挤出。日志/Audit 默认保存 Query Digest、Mode、Result Count 和 Latency，不保存可能包含
企业敏感信息的完整 Query。

## 9. Search Result 与动态 Activation

S4-0 Contract Test 已冻结第一版行为：Meta Tool 返回最多 10 个候选，并携带完整 Input/Output Schema：

```text
canonical_name
display_name
description
namespace
side_effect
version
match metadata
tool_version_id
input_schema / output_schema
```

候选范围已经从全 Catalog 缩小到 Top-K，因此第一版不再增加 `nexus.describe_tool` 或
`include_schema` 开关。Modern MCP SDK Contract 已验证：业务 Tool 即使未出现在初始 `tools/list`，Host
获得候选 Name/Schema 后仍可直接按名称调用：

```text
Search Result
→ Host Dynamic Activation
→ tools/call
```

Application Setting：

```text
tool_discovery_mode = eager
→ tools/list 返回 nexus.search_tools + 全部可见业务 Tool

tool_discovery_mode = search_first
→ tools/list 只返回 nexus.search_tools（Pinned Tool 后续再加）
```

禁止用一个无 Schema 的通用 `nexus.call_any_tool(name, arguments)` 绕过 Tool Contract、Policy 与模型
参数校验。

Hybrid 已进入正式 Data Plane。没有 Embedding Provider，或当前 Tenant/Filter Scope 存在 Published
Tool 但配置的 `Model@Dimensions` 完全没有 Projection 时，返回
`tool_search_mode_unavailable`，不把 FTS Fallback 伪装成 Hybrid。部分覆盖允许继续检索，其风险和收益
由 S4-4 的 Index Coverage/Freshness 指标评估。

## 10. Eval

Eval Dataset 至少覆盖：

- Exact Canonical Name；
- Namespace/Tags/业务关键词；
- 中文 Query → 英文 Tool Description；
- 同义/口语/模糊业务目标；
- 易混淆 Tool（Get/Set/Reserve）；
- No-Match；
- Cross-Tenant/Hidden/Restricted Tool。

内部比较：

```text
FTS-only
Vector-only
Hybrid
```

指标：Top-1、Hit@K、MRR、nDCG、Latency、Embedding Cost/Call Count、Index Coverage/Freshness、
Unauthorized Leakage。Agent-facing Contract Test 额外证明只暴露 `lexical | hybrid`，以及 Lexical 结果
不足时能够由 Host/Agent 发起第二次 Hybrid Search。

## 11. Deferred

- Auto Router/Confidence Gate；
- Cross-Encoder 或 LLM Rerank；
- Query Expansion/多个自动 Query；
- Tool 多 Chunk；
- 实时 Embedding Outbox Worker；
- 多模型在线 A/B；
- 外部 Knowledge RAG Demo；
- 文档 Chunk、Citation、GraphRAG、Knowledge Platform。

## 12. 关联决策

- [Tool 混合检索与 RRF 算法选择](../学习笔记/07_Tool混合检索与RRF算法选择.md)
- [ADR-0013｜内建 Meta Tool 与 Hybrid Tool Retrieval](../adr/0013-built-in-meta-tool-and-hybrid-retrieval.md)
- [ADR-0014｜PostgreSQL 18 pgvector 与 Vector Storage](../adr/0014-pgvector-infrastructure-and-vector-storage.md)
- [S4 阶段路书](../项目规划/06_阶段路书与验收标准.md)

## 13. S4-2a Infrastructure Confirmation

- Local/CI 镜像：`pgvector/pgvector:0.8.6-pg18-trixie`；
- 实际 Server：PostgreSQL 18.6 (Debian Trixie)，pgvector 0.8.6；
- Online Provider：SiliconFlow；
- Model：`Qwen/Qwen3-Embedding-8B`；
- Dimensions：2048；
- Storage：`VECTOR(2048)`；
- Distance：Cosine；
- Index：第一版 Exact Scan，无 HNSW/IVFFlat；
- Projection Table：`tool_search_embedding`；
- Python Adapter：pgvector SQLAlchemy Type Processor；不叠加 asyncpg Binary Codec；
- 真实 2048 维 Round-Trip 与 Exact Nearest Neighbor Integration Test 已通过。

## 14. S4-2b Reindex Pipeline Confirmation

代码所有权已迁移到独立 `modules/tool_search`：

```text
tool_search/
├── domain.py
├── ports.py
├── document_builder.py
├── search_tools.py
├── reindex_tools.py
└── adapters/
    ├── siliconflow.py
    ├── sqlalchemy_models.py
    ├── sqlalchemy_repository.py
    ├── sqlalchemy_uow.py
    └── in_memory.py
```

已完成：

- Published Tool → Canonical Document → SHA-256 Source Digest；
- Top-Level/Nested Input Field Summary，不 Embedding 完整 JSON Schema；
- Provider-neutral `EmbeddingProvider` Port；
- SiliconFlow Batch Adapter 的 Auth/Timeout/429/5xx/Count/Index/Dimension/Finite Value 验证；
- Projection Repository/UoW 的 Scope Query 与 PostgreSQL Upsert；
- Reindex 按 Digest 只处理 Missing/Stale Tool，每 Batch 短事务提交；
- `--dry-run/--force/--batch-size/--tenant-id` CLI；
- 真实首次索引后再次运行 `Embedded=0`，不重复调用付费 API。

## 15. S4-3 Hybrid Retrieval Confirmation

正式查询链路：

```text
SearchTools(over-fetch = final limit × 4)
→ SearchHybridTools
   ├── SearchPublishedTools → PostgreSQL Weighted FTS
   └── SearchVectorTools
       → EmbeddingProvider.embed((query,))
       → PostgreSQL Exact Cosine Search
→ ReciprocalRankFusion(k = 60)
→ Dynamic Policy Filter
→ Final Top-K
```

实现边界：

- Query Vector 只存在于单次请求内存，不写入 Projection；
- FTS 与 Query Embedding/Vector Search 使用 `asyncio.gather` 并发执行；
- Vector SQL 在距离计算前下推 Tenant、Active、Published Binding、Visibility、Namespace 与 Side Effect；
- Exact Scan 按 Cosine Distance 升序，同距离按 Canonical Name 稳定排序；
- RRF 只消费策略内名次，按 `tool_version_id` 去重，不混合 `ts_rank` 与 Cosine Raw Score；
- RRF 并列按 Canonical Name 和 Tool Version ID 确定性排序；
- Dynamic Policy 在融合后的 Over-fetched Candidate 上执行，再截取最终 Top-K；
- Agent-facing 仍只有 `lexical | hybrid`，Vector-only 只作为内部 Query/Eval 能力；
- MCP `_meta` 返回 `searchStrategyUsed`、`candidateCount` 和 Hybrid 的 `indexVersion`；
- `indexVersion` 第一版定义为 `Embedding Model@Dimensions`。

## 16. S4-4 Retrieval Eval Confirmation

Eval Dataset 已冻结为 8 个 Demo Tool、24 条人工标注 Query。确定性 Fake Embedding 只进入 CI 契约；
SiliconFlow Quality Snapshot 必须显式开启，并通过 Batch Precompute 把一次运行限制为 3 个付费请求。

真实 `Qwen/Qwen3-Embedding-8B` 快照：

```text
Lexical Top-1/Hit@3 = 45.45% / 45.45%
Vector  Top-1/Hit@3 = 95.45% / 100%
Hybrid  Top-1/Hit@3 = 95.45% / 100%
Unauthorized/Forbidden Leakage = 0
```

Hybrid 在该小 Dataset 上没有超过 Vector：精确 Query 中两路一致，模糊 Query 中 FTS 通常为空。该结果
支持继续保留 RRF 的量纲隔离与精确词保护，但不支持宣称 Fusion 已带来统计显著收益。

两个 No-Match Case 都被 Exact Vector 返回最近候选。S4 不用 2 个负例拍脑袋设置阈值；后续需要扩充
Hard Negative、记录正负 Cosine Score Distribution，再按 False Activation Cost 选择 Confidence Gate。

## 17. W4.6 Index Management 与 Search Diagnostics

Publish 事务仍不直接调用外部 Embedding Provider：

```text
Publish Commit
→ Tool Search Index 显示 Missing
→ Admin 创建 Reindex Job
→ 202 Accepted
→ In-process Background Task
→ Missing/Stale Document Batch Embedding
→ PostgreSQL Projection Upsert
→ Job Terminal Summary
```

`tool_search_reindex_job` 持久化请求人、Model@Dimensions、Force、Batch Size、状态、计数与安全错误码；
PostgreSQL Partial Unique Index 保证每个 Tenant 最多一个 `pending | running` Job。Web 进程重启时无法继续的
Active Job 会被标为 `failed/reindex_job_interrupted`，避免永远占用 Active Slot。

第一版后台任务与 Admin Web 进程同生命周期，适合模块化单体和本地作品集验证；多 Worker/多区域部署前需要将
Job Claim 与执行迁移到独立 Worker/Queue，不把 FastAPI Background Task 描述成分布式任务系统。

Search Lab 的 Admin-only Diagnostics 增加：

```text
RRF Score
Lexical Rank / ts_rank_cd
Vector Rank / Cosine Similarity
```

Agent-facing Meta Tool Contract 不依赖这些 Raw Diagnostics。RRF 仍然只使用名次，避免把 FTS 与 Cosine 的
不同量纲直接相加。
