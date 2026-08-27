# S4-4｜Retrieval Eval 与 S4 收口

> 日期：2026-08-27
> 状态：完成
> 范围：Dataset、Metrics、确定性回归、SiliconFlow Quality Snapshot 与 S4 决策收口

## 1. 数据边界

Eval 没有生成大规模随机数据，继续使用 OpenAPI Import → Review → Publish 产生的 8 个 Demo Tool：

```text
Directory  3
Operations 2
Inventory  3
```

Dataset 固定为 24 条人工标注 Query：22 条正例、2 条 No-Match，覆盖 Exact Keyword、Semantic Fuzzy、
Cross-Language、Filter 和 No-Match。每条 Case 保存 ID、Category、Query、Relevance Grade、可选 Namespace/
Side Effect 和 Forbidden Tool，不通过修改 Tool Description 迎合答案。

所有数据库 Eval 只接受名称包含 `test` 的 `nexusmcp_test`，并由现有 Fixture 只 TRUNCATE 明确列出的
NexusMCP 业务表。开发数据库 `nexusmcp` 不参与 Eval。

## 2. 两层证据

### 2.1 确定性 CI Eval

Fake Provider 只把 8 个 Tool/人工标签映射为 2048 维正交向量，用来验证：

- 8 Tool Reindex Coverage；
- Lexical/Vector/Hybrid Observation Matrix；
- Exact Search 与 RRF Pipeline；
- Top-1、Hit@3、MRR、nDCG@3、No-Match、Latency 与 Leakage 公式；
- Namespace/Side Effect Filter；
- 结果去重和稳定回归。

Fake 向量不作为模型质量证据。

### 2.2 SiliconFlow External Eval

显式设置 `NEXUSMCP_RUN_EXTERNAL_TESTS=1` 才运行：

```powershell
$env:NEXUSMCP_TEST_DATABASE_URL = "postgresql+asyncpg://.../nexusmcp_test"
$env:NEXUSMCP_RUN_EXTERNAL_TESTS = "1"
uv run pytest tests/integration/persistence/test_external_tool_search_retrieval_eval.py -q -s
```

成本控制：8 个 Tool Document 使用 1 个 Batch，24 个 Query 使用 2 个 Batch；三种 Strategy 复用已生成的
Query Vector，因此一次完整快照只有 3 次付费 Batch。普通 CI 和全量测试默认跳过。

## 3. 真实快照

运行配置：SiliconFlow、`Qwen/Qwen3-Embedding-8B`、2048 Dimensions、Cosine Exact Scan、RRF `k=60`。

| Strategy | Top-1 | Hit@3 | MRR | nDCG@3 | No-Match | P50* | P95* | Leakage |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Lexical | 45.45% | 45.45% | 45.45% | 45.45% | 100% | 6.78 ms | 13.47 ms | 0 |
| Vector | 95.45% | 100% | 97.73% | 98.32% | 0% | 11.33 ms | 20.08 ms | 0 |
| Hybrid | 95.45% | 100% | 97.73% | 98.32% | 0% | 12.66 ms | 19.95 ms | 0 |

`*` P50/P95 只包含预计算 Query Vector 后的 Database/Fusion 时间，不包含远程 Embedding 网络延迟。24 个
Query 的真实 Batch Embedding 总耗时为 788.86 ms；样本太小，不能把这些数字当成生产性能基准。

分类结果：

- Exact Keyword：三种 Strategy Top-1 都是 100%；
- Semantic Fuzzy：Lexical 0%，Vector/Hybrid 100%；
- Cross-Language：Lexical 0%，Vector/Hybrid Top-1 66.67%，Hit@3 100%；
- Filter：三种 Strategy Top-1 100%，Forbidden Leakage 为 0。

完整机器可读快照：
[2026-08-27_siliconflow_qwen3_embedding_8b.json](../../evals/tool_search/results/2026-08-27_siliconflow_qwen3_embedding_8b.json)。

## 4. 结果解释

Hybrid 与 Vector 在当前 Dataset 上指标相同，不应包装成“RRF 显著提升”：

- Exact Query 中 FTS 与 Vector 排名一致；
- Semantic/Cross-Language Query 中 FTS 通常为空，因此 Hybrid 退化为 Vector 排名；
- RRF 的当前价值是保留精确词通道和量纲隔离，而非已证明的净增益。

Cross-Language Contact Case 把 `directory.search_employees` 排在 `directory.get_employee` 前，但目标仍在
Top-2。该 Query 本身存在“搜索员工集合”与“读取单个员工联系方式”的语义歧义，保留原标签，不为了提高
Top-1 修改数据。

## 5. Eval 暴露的限制

Exact Vector Search 没有 Confidence Threshold，因此两个 No-Match Query 都返回最近的 3 个 Tool，导致
Vector/Hybrid No-Match Accuracy 为 0%。现在不能只凭 2 个负例选择阈值：不同模型、维度和 Catalog 密度
都会改变 Cosine Score 分布。

决策：

- S4 不临时加入拍脑袋的 Similarity Threshold；
- 后续扩充 Hard Negative/No-Match Dataset，记录正负 Score Distribution；
- 再通过 ROC/PR、False Activation Cost 选择 Threshold 或 Confidence Gate；
- 在此之前，Agent 必须把 Search Result 视为 Candidate，而非系统保证正确的最终 Tool。

## 6. S4 收口决策

- 保留 Agent-facing `lexical | hybrid`，不新增 Semantic/Auto；
- 保留 Exact Scan 与 RRF `k=60`，8 Tool 数据不支持 HNSW 或参数调优结论；
- 不新增 Rerank、Query Expansion、LLM Judge 或多 Chunk；
- External Eval 不设易抖动的在线模型硬断言，CI 只执行确定性契约；
- Unauthorized/Forbidden Leakage 必须持续为 0；
- Online Snapshot 必须记录 Provider、Model、Dimensions、Dataset Version、时间和调用批次。

## 7. S4 验收结论

S4 已完成：Meta Tool、Lexical FTS、Canonical Search Document、Embedding Projection、Reindex、Query
Embedding、Exact Vector Search、Hybrid RRF、治理过滤、动态 Activation 与 Retrieval Eval 均有可运行证据。

下一阶段进入 `S5｜工程证据`；No-Match Confidence Gate 作为有数据依据后再决策的 Retrieval Backlog。
