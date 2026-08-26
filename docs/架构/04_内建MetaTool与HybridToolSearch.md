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
→ Describe/Activate Tool Schema
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
| Execution Connector | 内部 Search Use Case | HTTP/MCP Connector |
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

Meta Tool 返回轻量候选：

```text
canonical_name
display_name
description
namespace
side_effect
version
match metadata
tool_version_id
```

不在 Search Result 中默认返回所有完整 JSON Schema。S4-0 必须通过 Modern MCP SDK/目标 Host Contract
Test 冻结以下接缝之一：

```text
Search Result
→ Describe/Get Schema
→ Host Dynamic Activation/Refresh
→ tools/call
```

禁止用一个无 Schema 的通用 `nexus.call_any_tool(name, arguments)` 绕过 Tool Contract、Policy 与模型
参数校验。

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

- [ADR-0013｜内建 Meta Tool 与 Hybrid Tool Retrieval](../adr/0013-built-in-meta-tool-and-hybrid-retrieval.md)
- [S4 阶段路书](../项目规划/06_阶段路书与验收标准.md)
