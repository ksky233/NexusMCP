# ADR-0013｜内建 Meta Tool 与 Hybrid Tool Retrieval

> 状态：Accepted  
> 日期：2026-08-26

## Context

企业 Catalog 达到数百或数千 Tool 时，不能把所有完整 Schema 一次放入 Agent Context。NexusMCP 已有
PostgreSQL FTS，但自然语言同义表达、中英文跨语言和描述不一致会降低 Lexical Recall。

Agent 已经具有前置意图理解能力：明确业务词、Canonical Name、Namespace、缩写适合低成本 Lexical
Search；模糊表达适合 Semantic Retrieval。Semantic-only 与 Hybrid 都要支付 Query Embedding 成本，
而额外 FTS 成本很小且能保留精确词召回。

外部 Knowledge RAG Demo 会引入文档摄取、Chunk、Citation 等与 Enterprise MCP Gateway 核心无关的
方向；Embedding/pgvector 学习可以直接服务 Tool Selection。

## Decision

1. NexusMCP 内建 `nexus.search_tools` Meta MCP Tool。
2. Meta Tool 在协议层是 Tool，但不进入 Catalog，不拥有 ToolVersion、ToolBinding、Upstream 或
   Credential；随 NexusMCP 应用版本发布。
3. `nexus.*` 是保留 Namespace，企业 Import/Publish 不能占用。
4. Agent-facing 只暴露一个 Search Meta Tool，不拆成 FTS/Vector/Hybrid 三个 Tool。
5. `retrieval_mode` 必填且仅允许：
   - `lexical`：PostgreSQL FTS；
   - `hybrid`：FTS + Tool Vector Retrieval + Rank Fusion。
6. 不向 Agent 暴露 `semantic`：Vector-only 仅作为内部 Eval/Ablation Strategy。
7. 第一版不实现 `auto`：Agent 可以根据意图明确程度选择模式，并在 Lexical 结果不足时自主改用
   Hybrid；只有真实指标证明路由不稳定或成本过高时才实现 Auto Router。
8. 一条 Published ToolVersion 默认对应一个 Canonical Tool Search Document 和 Embedding，不把普通
   Tool 强行切成多个 Chunk。
9. Search Document 由 Name、Description、Tags、Namespace、Owner、Side Effect 与 Input Field
   Summary 组成，不直接 Embedding 完整 JSON Schema。
10. Embedding 是可重建 Search Projection，独立于 ToolVersion 业务事实，保存 Model、Dimensions、
    Source Digest、Vector 和 Indexed Time。
11. Publish 事务不调用 Embedding Provider；通过 Post-Commit CLI/Reindex Job 构建 Projection。
12. Hybrid 首版使用 Rank-Based Fusion（优先 RRF），不直接相加量纲不同的 FTS/Vector Raw Score。
13. Tenant、Published、Visibility、Policy Filter 在返回候选前生效，Unauthorized Leakage 必须为 0。
14. 外部 Knowledge RAG Demo 移出 S4 主线；企业已有 RAG 未来仍可作为普通 OpenAPI/MCP Upstream
    被 NexusMCP 管理。

## Meta Tool Contract

```text
nexus.search_tools
- query: string
- retrieval_mode: lexical | hybrid（required）
- limit: integer
- namespace: optional
- side_effect: optional
```

返回最多 10 个 Top-K Tool Metadata 与完整 Input/Output Schema，由 Host 动态激活。Meta Tool 自身仍受
Authentication、Tenant Boundary、Search Policy、Rate/Trace/Audit 约束，但不走 Upstream
Credential/Execution Connector。

## Rejected Alternatives

- 暴露 `search_tools_fts/search_tools_vector/search_tools_hybrid` 三个重复 Meta Tool；
- 让所有请求默认执行 Hybrid；
- 第一版只暴露 Auto 并重新实现一套 Query Router；
- 向 Agent 暴露 Semantic-only，支付相同 Embedding 成本却失去精确词召回；
- 把 Embedding 直接写入 ToolVersion 业务表；
- 在 Publish 数据库事务中同步调用 Embedding Model；
- 为了学习 RAG 建设与主产品无关的 Knowledge Platform。

## Consequences

- Agent/Host 必须理解 Lexical 与 Hybrid 的选择说明；
- Lexical → Hybrid 的自主重试可能多一次 Round Trip，但避免所有明确 Query 支付 Embedding 成本；
- S4-0 已冻结 Top-K Full Schema + Host Dynamic Activation，不增加 Generic Call Meta Tool；
- PostgreSQL 运行环境需要增加 pgvector，并通过 Eval 决定 Embedding Model/Dimensions/Index；
- Vector-only、Auto、Rerank 保留为内部或 Deferred Strategy，不进入第一版公共协议；
- Meta Tool 的版本、Namespace 和权限规则必须与 Catalog Managed Tool 明确隔离。

## Verification

- 同一 Query 分别运行 FTS-only、Vector-only、Hybrid Eval；
- 精确名称/关键词 Case 验证 Lexical Latency 与命中；
- 模糊、同义、跨语言 Case 验证 Hybrid 净收益；
- Agent-facing Schema 只出现 `lexical | hybrid`；
- Lexical 无结果后由 Agent/测试流程再次调用 Hybrid；
- Hidden/Cross-Tenant Tool 在所有 Strategy 中均不泄漏；
- Publish 不依赖 Embedding Provider 可用性，Reindex 可重复且由 Source Digest 去重。

## Implementation Confirmation

S4-0/S4-1 已确认：

- `nexus.search_tools` 始终由 Application 组装，不写入 Catalog；
- Upstream/Catalog 拒绝保留的 `nexus` Namespace；
- `tool_discovery_mode=eager|search_first` 控制初始发现范围；
- Search-First 初始只列出 Meta Tool；
- Lexical 使用现有 PostgreSQL Weighted FTS，并接受 Namespace/Side Effect Filter；
- Candidate 在 Visibility 后继续执行粗粒度 Policy Filter；
- Top-K 最大 10，直接返回完整 Schema；
- SDK 可以调用未在初始 `tools/list` 中列出、但由 Search Result 激活的业务 Tool；
- Hybrid 在 Vector Index 缺失时返回稳定 Unavailable，不静默降级；
- 当前 8 个 Demo Tool 已建立 Lexical Eval Baseline 和已知 Semantic Gap Cases。
