# S4-0/1｜内建 Meta Tool 与 Lexical Search 验收

> 日期：2026-08-26  
> 状态：完成  
> 范围：Built-in Meta Tool、保留 Namespace、Search-First、PostgreSQL FTS Data Plane 与 Eval Baseline

## 1. Built-in Meta Tool

`nexus.search_tools` 在 MCP 协议层是 Tool，但不属于 Catalog Managed Tool：

```text
Application Version
→ Built-in Meta Tool Definition
→ tools/list
```

它不拥有 ToolVersion、ToolBinding、Upstream 或 Credential，不经过 OpenAPI Import/Review/Publish。
`nexus.*` 是保留 Namespace，Registry 与 Catalog Domain 都拒绝 Tenant 占用。

## 2. Agent-facing Contract

```text
nexus.search_tools
- query
- retrieval_mode: lexical | hybrid（required）
- limit: 1..10（default 5）
- namespace（optional）
- side_effect（optional）
```

第一版只实现 Lexical。Hybrid 名称和 Schema 已冻结，但 Vector Index 尚未建立时明确返回：

```text
tool_search_mode_unavailable
```

不使用 FTS 静默伪装 Hybrid，也不暴露 Semantic-only/Auto。

## 3. Discovery Mode

```text
eager
→ nexus.search_tools + 全部可见业务 Tool

search_first
→ 初始 tools/list 只返回 nexus.search_tools
```

Search-First 调用返回 Top-K Candidate 的 Name、Metadata 与完整 Input/Output Schema。Modern MCP SDK
Contract 已证明：Client 可以按 Candidate Name 直接调用未出现在初始 `tools/list` 的业务 Tool，因此不
增加危险的 `nexus.call_any_tool`。

## 4. Lexical Data Plane

Meta Tool 复用现有 `SearchPublishedTools` 与 PostgreSQL Weighted FTS/GIN：

```text
Request Context
→ Tenant + Published + Active
→ Visibility Filter
→ Namespace / Side Effect Static Filter
→ FTS Over-fetch
→ CALL Policy 粗粒度 Filter
→ Top-K
→ Full Schema Candidate Result
```

动态 Policy 无法完全下推 SQL，因此先按静态治理条件检索并 Over-fetch，再去掉 DENY Candidate，避免
隐藏 Tool 占满最终 Top-K。

## 5. Eval Baseline

当时新增 12 条 Lexical Baseline；S4-4 已将其升级并替换为
`evals/tool_search/retrieval_cases.json` 的 24 条统一 Retrieval Dataset：

- 8 个明确名称/关键词 Positive Cases；
- 4 个模糊、同义或中文跨语言 Semantic Target Cases；
- Positive 要求 Top-1 ≥ 0.75、Hit@3 = 1.0；
- 至少保留两个 FTS Semantic Miss，作为 S4-2/3 Hybrid 净收益的输入证据。

这避免在 pgvector 实现后只展示成功例子，而没有可比较的 FTS Baseline。

## 6. 安全边界

- Meta Tool 仍先建立可信 RequestContext；
- Cross-Tenant、非 Published、Disabled、不可见或 Policy DENY Tool 不返回；
- Search 日志记录 Mode、Candidate Count、Latency，不记录完整 Query；
- Top-K 限制为 10，避免通过一次 Search 搬运全部 Catalog Schema；
- Meta Tool 不进入 Upstream Execution/Credential 链；候选业务 Tool 的正式调用仍走完整 S3 治理链。

## 7. 当前边界

- Hybrid 尚未实现；
- Restricted Tool 的独立 Discovery Policy 仍待更细模型；
- Meta Tool Search Audit 当前是结构化日志，尚未写独立持久化 Search Audit；
- Pinned Tool 尚未实现；
- Embedding Model、Dimensions、pgvector Index 尚未决定；
- 不支持 Auto Router、Semantic-only Agent Mode 或 Rerank。

## 8. 下一步

进入 `S4-2｜Tool Search Document、EmbeddingProvider 与 pgvector Projection`。先冻结可重建的
Canonical Tool Search Document 和 Embedding Port，再决定 PostgreSQL pgvector 镜像与实际多语言
Embedding Model，不能把模型调用放入 Publish 事务。
