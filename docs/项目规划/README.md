# NexusMCP 项目规划索引

> 状态：初步规划
> 基线日期：2026-08-24
> 说明：本目录是 NexusMCP 的项目级设计与重构入口。它聚焦项目本身，不重复个人求职路书中的算法、八股和简历安排。

## 1. 项目定位

NexusMCP 是一个以 Python 实现的 Enterprise MCP Gateway & Registry，负责治理：

```text
Agent / MCP Client
        ↓
    NexusMCP
        ↓
MCP Server / OpenAPI / Enterprise Tool
```

核心价值不是“再写一个 MCP Proxy”，而是把 Tool 纳入统一的发现、发布、访问控制、凭据注入、审计和可观测体系。

## 2. 文档阅读顺序

| 顺序 | 文档 | 解决的问题 |
|---:|---|---|
| 1 | [00｜整体规划](./00_整体规划.md) | 为什么做、做到哪里、当前不做什么 |
| 2 | [01｜协议基线与兼容策略](./01_协议基线与兼容策略.md) | 最新 MCP 与旧项目协议如何区分、如何双时代兼容 |
| 3 | [02｜Java 旧项目利用与 Python 迁移](./02_Java旧项目利用与Python迁移.md) | 旧源码哪些复用、哪些只对照、哪些禁止照搬 |
| 4 | [03｜Python 目标架构与工程结构](./03_Python目标架构与工程结构.md) | 新项目怎样分层、模块依赖和请求链如何设计 |
| 5 | [04｜数据模型与状态所有权](./04_数据模型与状态所有权.md) | Registry、Tool、Policy、Credential、Audit 分别拥有什么状态 |
| 6 | [05｜功能范围与新增特性](./05_功能范围与新增特性.md) | Must/Should/Could、RAG 边界和核心 Demo |
| 7 | [06｜阶段路书与验收标准](./06_阶段路书与验收标准.md) | 按什么顺序实现、建议投入多少小时、何时停止扩展 |
| 8 | [07｜质量、评测、可观测性与安全](./07_质量评测可观测性与安全.md) | 怎样证明项目可靠、安全、可解释，而不只是能运行 |
| 9 | [08｜ADR 与待决策清单](./08_ADR与待决策清单.md) | 已确认决策、待实验决策以及如何记录取舍 |

## 3. 决策层级

文档中的内容分为三类：

```text
已确认
= 当前直接执行，修改时应补 ADR

推荐
= 初始默认，可以在实现前通过实验调整

待决策
= 不阻塞当前阶段，达到触发条件再决定
```

## 4. 当前已确认事项

- Python 为主语言；
- MCP `2026-07-28` 为现代协议主线；
- 兼容旧版 handshake/session 客户端，但不复制旧项目的 Session 架构；
- 使用官方 Python MCP SDK v2 承担协议编解码和版本协商；
- 第一版采用模块化单体，逻辑区分 Control Plane 与 Data Plane；
- PostgreSQL 为主存储，Redis 不是无条件前置依赖；
- Tool Catalog 先使用 PostgreSQL FTS，并在 S4 增加 Tool Embedding、pgvector 与 Hybrid Retrieval；
- `nexus.search_tools` 是内建 Meta Tool，不属于 Catalog Managed Tool；Agent-facing 只暴露
  `lexical | hybrid`，Vector-only 仅供 Eval，Auto 延后；
- 外部 `knowledge.search` RAG Demo 移出当前主线，RAG/Embedding 学习直接服务 Tool Semantic
  Retrieval；
- Evaluation、OpenTelemetry、安全、幂等和错误分类属于主线；
- 不建设大而全管理后台，不追求支持所有 MCP Extension。

## 5. 维护方式

1. 总体边界变化优先更新 `00` 和 ADR；
2. 协议行为变化只在 `01` 维护，其他文档引用它；
3. 阶段状态和实际投入只在 `06` 回填；
4. 测试结果、Benchmark 和风险只在 `07` 维护；
5. 不把临时想法直接写成 Must Feature，先进入 `08` 的待决策清单。

## 6. 外部基线

- MCP `2026-07-28`：<https://blog.modelcontextprotocol.io/posts/2026-07-28/>
- MCP Python SDK：<https://github.com/modelcontextprotocol/python-sdk>
- Python SDK 新版协议说明：<https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/whats-new.md>
- Python SDK 旧客户端兼容：<https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/legacy-clients.md>
- 旧 Java 学习项目：`LearnForNexusAI/AI-MCP-Gateway/`
