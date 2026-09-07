
**两者都是，但分工不同：六边形架构是这个项目的「骨架」，DDD 战术模式是「血肉」。** 更精确的定性是：**模块化单体 + 六边形架构（Ports & Adapters）+ DDD 战术模式**，也就是常说的「Hexagonal + DDD Lite」组合。这两者本来就是正交的两件事，下面分别用证据说明。

---

## 一、六边形架构的证据（结构层面）

六边形架构（Cockburn, 2005）的核心只有两条：**核心不依赖外圈** + **所有交互都过 Port**。本项目完全符合：

```
                    ┌─────────── driving adapters（主动适配器）┐
                    │  interfaces/mcp · http · admin · cli    │
                    │  谁来调用核心（MCP Client、管理员、CLI）    │
                    └──────────────────┬──────────────────────┘
                                       ▼
        ┌───────────────────── 核心区 ─────────────────────┐
        │  modules/*/{use_cases, publish, review}.py      │   ← 应用层
        │  modules/*/domain.py                            │   ← 领域层
        │  modules/*/ports.py（Protocol）                  │   ← 被动端口
        └─────────────────────┬───────────────────────────┘
                              ▼
                    ┌─────────────────────────────────────────┐
                    │  driven adapters（被动适配器）             │
                    │  adapters/{in_memory, sqlalchemy_*}      │
                    │  infrastructure/{persistence, telemetry} │
                    │  核心调用谁（PostgreSQL、OTel、HTTP）       │
                    └─────────────────────────────────────────┘
                              ▲
                    bootstrap/ = Composition Root（组装点）
```

逐条对照六边形的经典要素：

| 六边形要素 | 项目落点 |
|---|---|
| Driving Port（主动端口） | MCP 协议 Handler、Admin Router、CLI 入口 |
| Driven Port（被动端口） | [ports.py](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/modules/toolsets/ports.py) 的 `ToolsetRepository`、`ToolsetUnitOfWork`、`ToolsetCatalogReader` 等 Protocol |
| Adapter 可替换 | 同一 Port 的 `in_memory` / `sqlalchemy_uow` 双实现，由契约测试保证行为等价 |
| 依赖方向 | `domain.py` 只 import `shared/`，绝不 import adapters / interfaces / mcp / fastapi / sqlalchemy |
| Composition Root | [bootstrap/](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/bootstrap/app.py) 手动组装，业务代码零全局依赖 |

> 注：Onion Architecture 和 Clean Architecture 都是六边形的精细化变体。本项目里 `use_cases.py` 对应 Clean 的「Use Cases 圈」，`domain.py` 对应「Entities 圈」，依赖规则一致。

---

## 二、DDD 的证据（建模层面）

DDD 分**战略设计**（限界上下文、通用语言）和**战术模式**（聚合、值对象、仓储等），本项目两边都有实打实的落地。

### 战略层：模块 = 限界上下文

`modules/` 下的 12 个模块（catalog、toolsets、registry、approval、execution、tool_search、openapi_import、credentials、identity、policy、connectors、audit）各自拥有**独立的** `domain.py + ports.py + adapters/`，彼此不共享领域模型——这就是限界上下文的物理边界。上下文之间只通过两个窄口交互：

- **Shared Kernel（共享内核）**：[shared/request_context.py](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/shared/request_context.py) 的 `RequestContext`、`tool_namespaces.py` —— 刻意保持极小的状态无关契约
- **跨上下文读取**：`ToolsetCatalogReader` 这类只读快照 Port，而不是直接读别的模块的表

### 战术层：模式逐一对应

这是最有说服力的部分。以 [toolsets/domain.py](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/modules/toolsets/domain.py) 为例：

| DDD 战术模式 | 项目代码 | 证据 |
|---|---|---|
| **Aggregate（聚合）** | `Toolset` | [L81](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/modules/toolsets/domain.py#L81) docstring 直说：「稳定 Endpoint 身份与当前 Member/Grant 集合**组成一个 Aggregate**」；[L354-L361](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/modules/toolsets/domain.py#L354-L361) 校验成员「crossed aggregate tenant or identity boundary」——聚合边界显式执法 |
| **Value Object（值对象）** | `ToolsetMember`、`ToolsetAccessGrant`、`ToolsetCatalogSnapshot` | 全部 `frozen=True` + `__post_init__` 不变量校验——不可变、按值判等，教科书式 VO |
| **Entity（实体）** | `Toolset` | 有稳定 `id` + `revision`（乐观并发版本号），按身份判等 |
| **聚合不变量（Invariant）** | `Toolset.__post_init__` | slug 格式、all_published 无显式成员、active 必须有成员、membership_digest 与成员一致（[L127](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/modules/toolsets/domain.py#L127)）——**任何时刻构造出的聚合都必须合法** |
| **充血模型（Rich Domain Model）** | `update_profile()`、`replace_members()`、`activate()`、`disable()` | 业务规则全部在领域对象上，Use Case 里没有 `if status == ...` 的散落逻辑；对比 Spring 教程的贫血 `@Entity` 是明显更强的 DDD |
| **Factory（工厂）** | `Toolset.create_explicit()` / `create_all_published()` [L130-L182](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/modules/toolsets/domain.py#L130-L182) | 类方法工厂，保证从第一步就构造合法聚合 |
| **Repository（仓储）** | `ToolsetRepository` Protocol + 双 Adapter | 上一轮讲过，集合语义按聚合整体存取 |
| **Unit of Work** | `ToolsetUnitOfWork` | 事务边界抽象，保证聚合 + Catalog 快照原子提交 |
| **Domain Event（领域事件）** | [catalog/events.py](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/modules/catalog/events.py) `ToolPublished` | docstring：「由**事务外消费者**处理」——标准的事件最终一致性设计 |
| **通用语言（Ubiquitous Language）** | `slug`、`membership_digest`、`revision`、`principal_id`、`grant` | 代码命名与规划文档（docs/项目规划）用语一致 |

特别值得看的是**乐观并发控制**：每个变更方法都要求 `expected_revision`（[L192-L201](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/modules/toolsets/domain.py#L192-L201)），冲突时抛 `revision conflict`——配合 Repository 的 `get_for_update()`，形成了「领域层表达意图、适配器层决定锁策略」的经典 DDD 分工。

---

## 三、与「教科书版」的差异（务实简化）

说它是 DDD，但不是 Evangelists 版的 DDD，几处刻意取舍：

| 教科书 DDD | 本项目 | 评价 |
|---|---|---|
| 聚合是可变对象图，根对象暴露命令 | **不可变聚合**：`dataclasses.replace()` 整体替换，每次变更产生新实例 | 更函数式、并发更安全；代价是成员多时 replace 开销大。这是 Python 生态的合理选择 |
| 聚合内强一致 + 跨聚合靠事件 | 已采用（`ToolPublished` 事务外消费） | 完整遵守 |
| 领域服务（Domain Service）层 | 只有零星纯函数（如 `derive_toolset_health`、`calculate_membership_digest`） | 没有形式化的 Domain Service 层，逻辑能进聚合就进聚合——避免过度分层，合理 |
| 各上下文完全隔离 | 保留小 Shared Kernel（`RequestContext`、`tool_namespaces`） | 允许极小共享内核是战略设计明文允许的选项 |
| 防腐层（ACL） | [interfaces/mcp/context.py](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/interfaces/mcp/context.py) 把 MCP Context 翻译成内部 `RequestContext` | 有 ACL 意识，但只在入站协议处，轻量 |

---

## 四、总结

```
DDD 战略设计   ──→  modules/ 划分 = 限界上下文 + 极小 Shared Kernel
六边形架构     ──→  ports.py Protocol + adapters/ 双实现 + interfaces/ + bootstrap 组装根
DDD 战术模式   ──→  聚合/值对象/实体/仓储/UoW/领域事件/工厂 + 充血领域模型
```

一句话：**用六边形架构组织依赖，用 DDD 战术模式塑造核心，用模块化单体控制部署复杂度**——这三件事分别回答「依赖朝哪指」「领域怎么建」「系统怎么长」。它不是某个单一范式的教条实现，而是三者（外加一点函数式风格）的务实融合，而且每一条都能在代码里找到对应证据，不是文档上贴的标签。