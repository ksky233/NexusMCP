# Tool 混合检索与 RRF 算法选择

> 用途：S4 Hybrid Tool Retrieval 学习笔记与面试讲解材料
> 场景：PostgreSQL FTS + pgvector Semantic Search → Top-K Tool Candidate

## 1. 要解决的业务问题

企业 Catalog 可能包含数百到数千个 Tool。Agent 不能每次加载全部 Schema，需要先根据自然语言检索
少量候选。

单独使用一种检索方法存在明显短板：

```text
Lexical / FTS
→ 擅长 Canonical Name、Namespace、Tags、缩写和精确领域词
→ 不擅长同义表达、口语、中文 Query 对英文描述

Semantic / Vector
→ 擅长同义、模糊意图、跨语言
→ 可能弱化精确代码、缩写和 Tool Name
```

因此 NexusMCP 的 Hybrid 模式同时召回两组候选，再融合排名：

```text
Query
├── PostgreSQL Weighted FTS → Lexical Ranking
└── Qwen Query Embedding → Exact Cosine Ranking
                         ↓
                    RRF Fusion
                         ↓
                Governance Filter + Top-K
```

## 2. 为什么不直接相加原始分数

FTS 使用 `ts_rank_cd`，Vector Search 使用 Cosine Distance/Similarity：

```text
FTS Rank Score       = 0.42
Cosine Similarity    = 0.87
```

二者不能直接比较：

- 数值范围不同；
- 分布不同；
- 数据量变化后的缩放不同；
- FTS 权重、文档长度会改变 `ts_rank_cd`；
- Embedding Model 升级会改变 Cosine 分布。

直接使用：

```text
0.5 × FTS + 0.5 × Vector
```

意味着需要额外做 Score Normalization、权重调参与版本校准。没有 Eval 证据时，这些权重只是主观常数。

## 3. RRF 是什么

RRF 全称：

```text
Reciprocal Rank Fusion
```

中文常译为“倒数排名融合”。它忽略不可比的原始分数，只使用每个候选在各检索器中的名次。

公式：

```text
RRF Score(document) = Σ 1 / (k + rank_i(document))
```

其中：

- `rank_i`：候选在第 i 个结果列表中的 1-based Rank；
- 候选未出现在某个列表中时，该列表贡献 0；
- `k`：平滑常数，不是 Top-K；
- 第一版使用常见 Baseline `k = 60`，最终由 Eval 调整。

RRF 的直觉是：

> 同时被多个独立检索器排在前面的 Tool，比只被一种算法偶然排在前面的 Tool 更可信。

## 4. 计算示例

用户 Query：

```text
设置库存补货阈值
```

候选排名：

| Tool | FTS Rank | Vector Rank |
|---|---:|---:|
| `inventory.get_status` | 1 | 3 |
| `inventory.set_reorder_level` | 2 | 1 |
| `inventory.reserve_stock` | 3 | 2 |

使用 `k = 60`：

```text
set_reorder_level
= 1/(60+2) + 1/(60+1)
≈ 0.032522

get_status
= 1/(60+1) + 1/(60+3)
≈ 0.032266

reserve_stock
= 1/(60+3) + 1/(60+2)
≈ 0.032002
```

最终：

```text
1. inventory.set_reorder_level
2. inventory.get_status
3. inventory.reserve_stock
```

注意：RRF Score 只是排序分数，不是概率或置信度，不能向 Agent 表述为“相关概率 3.25%”。

## 5. k 参数的含义

`k` 控制头部 Rank 差异的强弱：

```text
k 较小
→ Rank 1 与 Rank 5 的差异更明显
→ 更相信单个检索器的头部

k 较大
→ 相邻 Rank 得分更接近
→ 更重视多个列表共同命中
```

第一版使用 60 的原因：

- 是 RRF 常见 Baseline；
- 不需要在实现前虚构权重；
- 当前 Candidate List 较短，先建立可复现对照；
- 后续通过 Top-1/Hit@K/MRR/nDCG 调整，而不是凭感觉调参。

## 6. Candidate Over-fetch

Agent 请求 Top-5 时，FTS 和 Vector 不能各只返回 5 个：

```text
Agent Limit = 5
Over-fetch Factor = 4

FTS Candidates = 20
Vector Candidates = 20
RRF + Policy Filter
Final Results = 5
```

原因：

- 两个列表可能高度重叠；
- Candidate 可能被 Visibility/Policy 拒绝；
- 只取 Top-5 会过早丢失可融合候选；
- Approximate Index 出现后还需要为 Recall 留出空间。

第一版沿用 `factor = 4`、内部最大 50 的边界，后续根据 Eval/Latency 调整。

## 7. 确定性排序与 Tie-Break

相同 RRF Score 必须有稳定顺序，避免同一 Query 多次返回不同 Tool：

```text
1. RRF Score DESC
2. 命中的 Retrieval List 数量 DESC
3. Best Individual Rank ASC
4. Canonical Name ASC
```

稳定 Tie-Break 对以下场景重要：

- Golden Eval；
- MCP Response Cache；
- Agent 行为复现；
- Embedding Model A/B 对比；
- 线上问题排查。

## 8. Governance Filter 放在哪里

搜索不能成为隐藏 Tool 的侧信道。

静态条件尽量下推 FTS/Vector SQL：

```text
tenant_id
Active Tool
Published ToolVersion
Published Binding
Visibility
Embedding Model / Dimensions
Namespace / Side Effect Filter
```

动态 Policy 可能无法完全下推 SQL，因此：

```text
Static Filter
→ Over-fetch Candidates
→ RRF
→ Dynamic Policy Filter
→ Final Top-K
```

不能先从全 Tenant/全局 Catalog 取 Top-K 再做权限过滤，否则：

- 不可见 Tool 可能挤掉合法候选；
- Rank/Result Count 可能泄漏隐藏 Tool 的存在；
- 不同 Principal 的缓存结果可能串用。

验收要求：

```text
Unauthorized Leakage = 0
```

## 9. Exact Vector Search 的算法选择

第一版使用：

```sql
ORDER BY embedding <=> :query_vector
LIMIT :candidate_limit
```

`<=>` 是 Cosine Distance，越小越相似。

先选 Exact Scan，而不是 HNSW：

- 当前真实 Tool 只有 8 个；
- Exact Recall = 100%；
- 没有 `m/ef_construction/ef_search` 调参；
- 可以先验证 Document、Embedding 和 Hybrid 算法正确性；
- HNSW 在小数据上无法形成有意义的性能证据；
- 2048 维普通 Float32 Vector 不能直接建立普通 HNSW。

只有 500～2000+ Tool Benchmark 证明 Exact Latency 不达标，才评估 HalfVec HNSW 或降维。

## 10. Missing/Stale Embedding

Tool 已发布但尚未 Reindex 时：

```text
FTS List    → 仍然可能召回
Vector List → 不包含该 Tool
RRF         → 使用现有列表正常计算
```

因此部分 Index Coverage 不会让 Hybrid 完全不可用，但需要返回诊断 Metadata：

```text
embedding_model
embedding_dimensions
vector_coverage
search_strategy_used
```

如果 Query Embedding Provider 本身失败，第一版返回稳定错误，不静默把 FTS 伪装成 Hybrid。Agent 可以
自主重新调用 `retrieval_mode=lexical`。

## 11. 复杂度与主要成本

令：

- `N`：当前 Tenant 可检索 Tool Vector 数量；
- `D`：Embedding Dimensions，当前 2048；
- `C`：两组 Candidate 去重后的数量。

第一版：

```text
Exact Vector Distance ≈ O(N × D)
RRF Fusion            ≈ O(C)
Final Sort            ≈ O(C log C)
```

当前最大的实际成本通常不是 RRF，而是：

```text
SiliconFlow Query Embedding Network Latency
+ Exact Vector Distance
```

FTS 与 Query Embedding 可以并行执行，减少 Hybrid Wall Time。第一版不增加 Query Cache，避免提前处理
Principal/Tenant/敏感 Query 的 Cache Scope。

## 12. 备选算法与拒绝原因

### Raw Score Weighted Sum

```text
α × normalized_fts + β × normalized_vector
```

需要可靠归一化和权重训练。没有足够 Eval 时先不采用。

### Semantic-only

Query Embedding 成本与 Hybrid 相同，却丢失精确名称/代码召回，只保留内部 Ablation Eval。

### Max Rank / 只取任一列表最高名次

不能奖励两个检索器共同命中的 Tool，鲁棒性低于 RRF。

### Cross-Encoder / LLM Rerank

可能提升精排，但增加模型成本、延迟、批量 Token 和新的 Provider 依赖；只有 Hybrid Eval 不达标时再加。

### Auto Router

需要额外置信度、成本和路由 Eval。第一版由外部 Agent 在 `lexical | hybrid` 中选择。

## 13. Eval 设计

对相同 Case 分别运行：

```text
FTS-only
Vector-only
Hybrid RRF
```

指标：

- Top-1 Accuracy；
- Hit@3 / Hit@K；
- MRR；
- nDCG；
- Query Embedding Latency；
- Exact Vector Query Latency；
- Hybrid Total Latency；
- Embedding Cost/Call Count；
- Unauthorized Leakage。

当前 FTS 已知 Gap：

```text
设置库存补货阈值
→ inventory.set_reorder_level

查找公司员工的联系方式
→ directory.get_employee

mark an outage as handled
→ ops.acknowledge_incident
```

S4-3 的目标不是证明 Vector“看起来高级”，而是量化 Hybrid 相对 FTS Baseline 的净收益。

## 14. 面试表达模板

可以用两分钟说明：

> 我们的 Tool Catalog 同时包含精确 API 名称和自然语言描述。FTS 对 Canonical Name、Tags 和领域缩写
> 很强，但中文到英文、同义表达的 Recall 不足；Embedding 对语义更强，但原始 Cosine Score 与
> PostgreSQL `ts_rank_cd` 不同量纲。我们没有主观地做加权求和，而是采用 Reciprocal Rank Fusion，
> 只融合各检索器 Rank。第一版使用 k=60、每路 over-fetch 4 倍，并用确定性 Tie-Break。静态权限过滤
> 下推 SQL，动态 Policy 在 over-fetch 后过滤，保证 Unauthorized Leakage 为 0。由于当前规模小，我们
> 先用 Exact Cosine Search 获得完整 Recall，再用 500～2000 Tool Benchmark 决定是否上 HNSW。最终通过
> Top-1、Hit@K、MRR、nDCG 和延迟对比 FTS/Vector/Hybrid，而不是只展示几个成功例子。

## 15. 一句话总结

```text
FTS 保证精确词召回
Vector 补充语义召回
RRF 在不校准异构 Raw Score 的前提下稳定融合两者
Eval 决定它是否真正优于 FTS Baseline
```
