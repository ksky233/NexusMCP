# 10｜小型知识 RAG 扩展规划

> 状态：推荐的封版后微型扩展；不阻塞 W5/S6 首次公开发布
> 建议投入：12～20 小时
> 定位：补齐 Knowledge RAG 实践，不建设新的知识库平台，不修改 NexusMCP Core

## 1. 为什么需要这个扩展

NexusMCP 当前完成的 Hybrid Tool Retrieval 解决的是：

```text
用户表达
→ 找到应该调用的 Tool
```

Knowledge RAG 解决的是另一个问题：

```text
用户问题
→ 从业务文档中检索相关 Chunk
→ 返回可引用的事实依据
```

二者都使用 Embedding/pgvector，但检索对象、数据模型、评测集和失败语义不同。Tool Retrieval 不能在求职叙事中替代知识库 RAG。

本扩展只增加一个独立的 Demo Knowledge HTTP Upstream，经现有 OpenAPI Import Pipeline 发布成 MCP Tool：

```text
Demo Documents
    ↓ CLI Ingest
Parse / Chunk
    ↓
Embedding
    ↓
PostgreSQL + pgvector
    ↓
Knowledge Search HTTP API
    ↓ OpenAPI Import / Review / Publish
NexusMCP knowledge.search Tool
    ↓ Policy / Trace / Audit
Agent / MCP Client
```

这条路径复用 NexusMCP 已有能力，不需要 Remote MCP Federation，也不在 Core 中加入 RAG 分支。

## 2. 目标与非目标

### 2.1 目标

- 理解并实现 Parse → Chunk → Embed → Retrieve → Cite；
- 将知识检索作为普通 HTTP/OpenAPI Upstream 接入 NexusMCP；
- 提供 `knowledge.search` MCP Tool；
- 支持 Metadata Filter 和来源引用；
- 建立 20～30 条人工标注 Retrieval Eval；
- 展示 Tenant/Policy/Trace/Audit 对 RAG Tool 的治理；
- 能解释何时关键词、向量和 Hybrid 各自更合适。

### 2.2 非目标

- 完整知识库管理后台；
- 多模态文档解析；
- GraphRAG、知识图谱或逻辑推理平台；
- Cross-Encoder/LLM Rerank；
- 自动生成大规模评测集；
- 文档权限协作和增量同步平台；
- Remote MCP Server Proxy；
- 生产级分布式向量数据库；
- 将 Demo RAG 表混入 NexusMCP Tool Search Projection。

## 3. 工程边界

建议目录：

```text
examples/upstream_apis/knowledge_search/
├── app.py
├── models.py
├── repository.py
├── retrieval.py
├── ingest.py
├── documents/
└── README.md
```

约束：

- Demo Upstream 不 import `nexusmcp.modules.*`；
- 通过公开 HTTP/OpenAPI Contract 与 NexusMCP 交互；
- 可以复用相同 Embedding Provider 配置模式，但不复用 Tool Search Domain Model；
- 可以使用同一 PostgreSQL Container，但使用独立表或 Schema；
- Demo 文档只使用公开资料或完全虚构的业务手册；
- 禁止使用易宝支付源码、真实接口、内部制度、客户数据或未公开业务文档。

## 4. Tool Contract

第一版只提供一个核心查询接口：

```python
knowledge.search(
    query: str,
    top_k: int = 5,
    filters: dict[str, str] | None = None,
)
```

建议返回：

```json
{
  "items": [
    {
      "document_id": "...",
      "chunk_id": "...",
      "text": "...",
      "source": "...",
      "score": 0.82,
      "metadata": {}
    }
  ],
  "retrieval_mode": "vector",
  "index_version": "model@dimensions:digest"
}
```

可选提供只读详情接口：

```text
knowledge.get_document(document_id)
```

不向 Agent 暴露 `knowledge.ingest`。文档摄取使用离线 CLI，避免模型获得知识库写权限。

## 5. 朴素 RAG 实现

### 5.1 文档

第一版只支持：

- Markdown；
- TXT；
- 少量文本型 PDF（有余力再加）。

推荐使用两类公开数据之一：

1. NexusMCP 自身公开文档；
2. 完全虚构的支付/运营业务手册。

如果使用虚构业务手册，应明确标注 `synthetic demo data`。

### 5.2 Chunk

第一版固定一种可解释策略：

- 优先按 Markdown Heading/Paragraph 切分；
- 超长段落再按 Token/字符长度切分；
- 保留标题路径和 source metadata；
- 使用少量 overlap；
- 记录 chunker version；
- 不为调参建立复杂策略框架。

### 5.3 Embedding 与存储

- 复用当前 SiliconFlow/OpenAI-compatible Embedding 配置经验；
- PostgreSQL + pgvector；
- 文档、Chunk、Embedding 使用独立表；
- 保存 source digest、embedding model、dimensions 和 indexed_at；
- Embedding 模型/维度变化时重新索引；
- 数据规模较小时使用 Exact Search，不默认创建 HNSW。

### 5.4 Retrieval

第一版：

```text
Query Embedding
→ Metadata/Tenant Filter
→ Exact Cosine Top-K
→ Result + Source
```

有余力时增加 PostgreSQL FTS，并使用 RRF 做 Hybrid：

```text
FTS Candidates
      +
Vector Candidates
      ↓
RRF
      ↓
Top-K
```

不要直接复制 Tool Search 表和 Repository；只复用已经验证过的算法思路和测试方法。

## 6. Evaluation

准备约 20～30 条人工标注：

```text
query
relevant_document_ids
relevant_chunk_ids
expected_no_match
tenant/metadata filter
```

第一版确定性指标：

- Recall@K；
- MRR；
- Top-1 Accuracy；
- No-Match 行为；
- Citation Hit Rate；
- Cross-Tenant Leakage；
- Retrieval p50/p95；
- 经过 NexusMCP Policy/Trace/Audit 后的额外延迟。

如果 Agent 负责最终回答，再可选增加回答层指标：

- Context Precision/Recall；
- Faithfulness；
- Answer Relevancy；
- Human Review。

## 7. 框架取舍

### 7.1 第一版：不使用大型 RAG 框架

第一版直接使用：

```text
FastAPI
SQLAlchemy/PostgreSQL
pgvector
Embedding API
少量 Parser/Tokenizer 库
pytest/Eval Script
```

这样能够直接展示 Chunk、Index、Filter、Retrieval、Citation 和 Eval，不让一行框架 API 隐藏关键机制。

### 7.2 LangChain / LlamaIndex

可以作为 Loader/Parser 等薄适配层，但不让它们拥有核心状态：

- 可以复用复杂格式 Loader；
- Retriever Contract 和数据模型保持项目自有；
- README 说明框架可以替换；
- 不使用 `from_documents()` 一行隐藏完整链路作为主要实现。

### 7.3 Ragas

Ragas 比图 RAG 框架更值得作为第二阶段可选依赖，因为它直接增强求职中重要的 Evaluation 证据。

使用顺序：

```text
先实现确定性 Retrieval Metrics
→ 再选少量 Ragas Answer-level Metrics
```

使用前锁定版本和 API；不默认接受 LLM-as-Judge 分数，保留人工样例和逐条结果。

官方项目：<https://github.com/vibrantlabsai/ragas>

### 7.4 Microsoft GraphRAG

当前不采用。

适用问题：

- 全局主题和社区摘要；
- 大量文档间实体关系；
- 普通 Chunk Retrieval 无法回答的 Global Query。

不采用原因：

- 官方明确定位为研究项目并进入维护模式；
- 索引可能消耗大量 LLM 资源；
- Prompt/Entity/Community Pipeline 明显扩大本扩展范围；
- 当前评测集尚未证明需要图结构。

官方项目：<https://github.com/microsoft/graphrag>

### 7.5 LightRAG

当前不作为主实现，可在朴素 RAG 完成后做可选对照。

它使用图结构与向量的双层索引，并提供 API Server、WebUI 和多种存储后端。适合：

- 实体关系明显；
- 需要跨文档全局上下文；
- 普通向量检索在多跳问题上持续失败；
- 需要研究增量图索引。

只有在同一评测集上证明有净收益时才采用。

官方项目：<https://github.com/HKUDS/LightRAG>

### 7.6 OpenSPG KAG

当前不采用。

KAG 适合有明确领域 Schema、专家规则、结构化/非结构化混合知识和多跳逻辑推理的专业知识库。它依赖 OpenSPG 和更完整的 Knowledge Builder/Solver，已经超出微型补点范围。

官方项目：<https://github.com/OpenSPG/KAG>

## 8. 何时才升级图 RAG

必须同时满足：

1. 朴素/Hybrid RAG 已完成且有稳定评测集；
2. Bad Case 明确属于关系、多跳或全局问题；
3. Metadata/Chunk/Hybrid/Rerank 无法合理解决；
4. 图索引成本可接受；
5. 使用同一数据集证明质量提升；
6. 不影响 NexusMCP 封版和求职主线。

否则不因为框架热度升级。

## 9. 工作包与投入

| 工作包 | 内容 | 建议投入 |
|---|---|---:|
| R0｜Contract/Dataset | Tool Contract、公开/虚构文档、20～30条Query | 2～3小时 |
| R1｜Ingest | Parse、Chunk、Digest、Embedding、pgvector表 | 3～5小时 |
| R2｜Retrieve | Vector Top-K、Filter、Citation、错误行为 | 3～5小时 |
| R3｜NexusMCP接入 | OpenAPI Import、Publish、Policy、Trace、Audit | 2～3小时 |
| R4｜Eval/Docs | Retrieval Eval、Benchmark、README、Demo | 2～4小时 |

总计约 12～20 小时。

## 10. 验收标准

- 一条命令或简短步骤完成文档摄取；
- OpenAPI Import 可以生成并发布 `knowledge.search`；
- MCP Client 可通过 NexusMCP 调用；
- 返回结果包含 Chunk、Source 和 Score；
- Metadata/Tenant Filter 有自动化测试；
- 20～30条Eval可复现；
- 记录 Recall@K/MRR/Top-1/Latency；
- Cross-Tenant Leakage = 0；
- Trace 能串起 MCP → Policy → HTTP Upstream → Retrieval → Audit；
- README 明确 Tool Retrieval 与 Knowledge RAG 的区别；
- 不引入 GraphRAG/KAG/新Web后台；
- 完成后停止扩展，回到 BaseForJob 和投递主线。

## 11. 执行顺序

```text
先完成 W5/S6 首次封版并推送
        ↓
如果仍有项目开发容量
        ↓
实现本微型 RAG 扩展
        ↓
更新 Demo/README/Evidence
        ↓
停止 NexusMCP Feature 扩展
```

本扩展不能成为推迟投递的理由。
