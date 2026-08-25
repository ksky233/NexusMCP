## `use_cases.py` 的理解

「Use Case」来自软件工程方法论，这是一个有明确来源和严格边界的架构概念。

---

### 1. 这个词从哪来的？

**Use Case（用例）** 这个术语是软件工程方法论**「Unified Process（统一过程）」和「Clean Architecture（整洁架构）」**的核心概念：

| 方法论 | 对 Use Case 的定义 |
|---|---|
| **Ivar Jacobson / UML** | "一组动作的序列，系统执行这些动作能产生对某个 Actor（参与者）可观测的结果" |
| **Robert Martin / Clean Architecture** | "编排业务流程的应用层对象，表达『用户要做什么事』，但**不关心**用哪种框架、哪种数据库、哪种 UI" |

在 DDD（领域驱动设计）的**分层架构**里，Use Case 属于**「Application Layer（应用层）」**，夹在中间：

```
┌─────────────────────────────────────────────────────────────┐
│  Interfaces / Adapters（接口适配层）                          │ ← MCP Handler、FastAPI Router
│     例：interfaces/mcp/server.py 里的 on_list_tools         │   把 MCP 参数翻译成应用能懂的 Query
├─────────────────────────────────────────────────────────────┤
│ ★ Application Layer（应用层）= use_cases.py                 │ ← 你问的这一层
│     例：ListVisibleTools.execute()                          │   编排「列出可见 Tool」这一件事的完整步骤
├─────────────────────────────────────────────────────────────┤
│  Domain Layer（领域层）= domain.py + ports.py               │
│     例：ToolDefinition.is_visible_to()、ToolRepository Protocol │   纯业务规则，谁也不依赖
├─────────────────────────────────────────────────────────────┤
│  Infrastructure / Adapters（基础设施层）= adapters/in_memory.py │
│     例：InMemoryToolRepository.list_by_tenant()             │   真正去查数据库/缓存
└─────────────────────────────────────────────────────────────┘
```

---

### 2. 为什么必须有单独的文件？—— 不这样做会踩什么坑

先看看**如果没有 `use_cases.py`**，代码会写成什么样（S1 实验阶段就是这样的）：

```python
# S1 实验 examples/mcp_compatibility/dynamic_gateway.py L115-L132
async def list_visible_tools(ctx, _params):
    _observe_context(ctx)           # ← 协议细节（观测探针）
    principal = _principal(ctx)     # ← 协议细节（从 MCP Context 解析身份）
    visible = [tool for tool in TOOLS if principal in tool.visible_to]
    tools = [types.Tool(...) for tool in visible]  # ← 协议细节（组装 MCP 返回类型）
    return types.ListToolsResult(tools=tools)
```

问题一目了然：**协议适配逻辑、业务编排逻辑、领域规则，全揉在一个函数里了。**

| 问题 | 举例 |
|---|---|
| 🔴 **复用困难** | 如果以后要加一个 REST API（`GET /api/tools`），也要「列出可见 Tool」，那这段可见性过滤代码得再抄一遍 |
| 🔴 **难以单独测试** | 测业务规则必须启动整个 MCP Server，没法只测「列出可见 Tool」这个行为 |
| 🔴 **换传输协议要重写业务** | 以后加 SSE、stdio Transport，每个 Handler 都要重写一遍可见性逻辑 |
| 🔴 **依赖方向错了** | 业务逻辑 import 了 `mcp.types`，领域层反向依赖了框架 |

**`use_cases.py` 就是用来把「业务编排」从「协议适配」里抽出来的那把刀。**

---

### 3. 看本项目的实际实现：分层后每一层都只干自己的事

我们把「列出可见 Tool」这条链，按代码实际拆开看：

#### ① 领域层 `domain.py`：只表达「是什么」，不表达「怎么查」

[ToolDefinition.is_visible_to()](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/modules/catalog/domain.py#L62-L71) — 纯业务不变量：
- 不是 PUBLISHED 状态 → 不可见
- PUBLIC → 任何人可见
- AUTHENTICATED → 只要不是匿名就可见
- RESTRICTED → 在白名单里才可见

**特点：零依赖，纯函数，测起来一行 mock 都不用。**

#### ② 端口层 `ports.py`：声明「我需要什么」，但不管谁实现

[ToolRepository Protocol](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/modules/catalog/ports.py#L9-L13)：
```python
class ToolRepository(Protocol):
    async def list_by_tenant(self, tenant_id: str) -> Sequence[ToolDefinition]: ...
    async def get_published_by_name(...) -> ToolDefinition | None: ...
```
**特点：只写签名不写实现，Application 层依赖这个抽象，不依赖 PostgreSQL/内存。**

#### ③ 应用层 `use_cases.py`：★ 你问的文件 —— 编排「一件完整的事」

[ListVisibleTools.execute()](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/modules/catalog/use_cases.py#L19-L24)：

```python
async def execute(self, query: ListVisibleToolsQuery) -> tuple[ToolDefinition, ...]:
    # 步骤 1: 通过端口查某租户的所有 Tool（不管底层是内存还是 PostgreSQL）
    tools = await self._repository.list_by_tenant(query.context.tenant_id)
    # 步骤 2: 调领域对象的方法做可见性判断（纯业务规则）
    visible = [tool for tool in tools if tool.is_visible_to(query.context.principal_id)]
    # 步骤 3: 按规范排序，返回领域对象（绝不返回 MCP types）
    return tuple(sorted(visible, key=lambda tool: tool.canonical_name))
```

**特点：**
- 只依赖「端口（Protocol）」，不依赖具体实现（依赖倒置 DIP）
- 只编排步骤，不做框架细节
- 入参是 `ListVisibleToolsQuery`（协议无关的 DTO），出参是 `tuple[ToolDefinition]`（领域对象）
- **从头到尾没有 import `mcp`、`FastAPI`、任何传输层东西**—— 这就是 Clean Architecture 的核心：**框架无关**

#### ④ 接口适配层：把 Use Case 的「领域结果」翻译成「协议响应」

看 [bootstrap/app.py L29-L37](file:///E:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/bootstrap/app.py#L29-L37) 和对应的 `create_mcp_server`，它们把 MCP 收到的请求**翻译**成 Use Case 能懂的 Query，再把 Use Case 返回的 `ToolDefinition` **翻译**回 MCP 的 `types.Tool`。

---

### 4. Use Case = 「用例」的边界：什么东西应该放进来，什么不应该

| ✅ 应该在 use_cases.py 里 | ❌ 不应该在 use_cases.py 里 |
|---|---|
| 编排步骤（先查 A 再算 B 再存 C） | 手写 SQL、连 Redis、发 HTTP |
| 调用端口（Repository、Policy 等） | import MCP / FastAPI / gRPC 类型 |
| 协调多个领域对象之间的交互 | 直接操作 HTTP Header / MCP Context `_meta` |
| 事务边界（事务从这里开，从这里提交/回滚） | 计算可见性、计算校验和等**纯领域逻辑**（应放 domain.py） |
| 安全相关：调用前确保 Principal 已解析（这里拿到的是可信 RequestContext） | 从 Token / Cookie 解析 Principal（应放 auth 模块） |

一句话记忆：**Use Case 是「导演」，不是「演员」也不是「舞台」——它指挥谁先上场、谁后上场，但自己不演戏、也不搭建舞台。**

---

### 5. `ListVisibleToolsQuery` 为什么还要单独一个 dataclass？

```python
@dataclass(frozen=True, slots=True)
class ListVisibleToolsQuery:
    context: RequestContext
```

这是 **CQRS（命令查询职责分离）** 模式的最小版。好处：

1. **签名稳定**：以后加 `cursor`、`page_size`、`search_keyword` 等参数，改 Query 内部字段就行，`execute()` 的签名永远是 `execute(self, query)`。
2. **自我描述**：光看类型就知道这个 Use Case 要什么输入（对比 `execute(self, tenant_id, principal_id, cursor, page_size, keyword)` 一堆散参数根本看不出语义）。
3. **方便中间件拦截**：以后做 Logging、Metrics、Policy 中间件，可以统一拦截所有 `*Query` / `*Command` 对象。

---

### 6. 在 NexusMCP 架构中的映射关系

回到整体规划里的「核心请求链」，`use_cases.py` 这一层对应的是图中每一个「业务步骤方块」：

```
MCP Request
  ↓
Protocol Version / Method Routing           ← interfaces/mcp/*.py
  ↓
Authentication → Internal Principal        ← auth/*.py
  ↓
────────────────────────────────────────────────────────────
  ↓  下面进入 Application Layer = use_cases.py
  ↓
Server / Tool Resolution                    ← ListVisibleTools
  ↓
Visibility + Policy Decision                ← CallTool（未来）
  ↓
Credential Reference Resolution             ← InjectCredential（未来）
  ↓
Tool Execution / Upstream Proxy             ← ExecuteTool（未来）
  ↓
Response Normalization / Redaction          ← 各 Use Case 统一出参规约
────────────────────────────────────────────────────────────
  ↓
Trace + Metric + Audit                      ← observability/*.py
  ↓
MCP Response                                ← interfaces/mcp/*.py
```

所以这个文件现在只有 `ListVisibleTools` 一个用例是正常的——项目刚搭骨架，`tools/list` 是第一个闭环的能力。后续 `tools/call`、`OpenAPIImport`、`PublishTool`、`GetAuditEvents` 等都会以独立的 Use Case 类追加到这个文件里。

---

### 总结

| 维度 | 说明 |
|---|---|
| **单词来源** | Clean Architecture / DDD 术语，直译为「用例」 |
| **架构定位** | **Application Layer（应用层）**，介于 Interface 与 Domain/Infra 之间 |
| **核心职能** | 编排「一件用户想做的事」的完整步骤，协调领域对象与端口，但不关心具体技术 |
| **为什么要有单独文件** | 把业务编排从协议/框架里剥离出来，实现框架无关、可复用、可单独测试 |
| **依赖方向** | 只依赖 Domain（`ToolDefinition`）和 Ports（`ToolRepository` Protocol），绝不反向依赖 MCP/FastAPI |
| **本项目当前内容** | `ListVisibleTools` Use Case + `ListVisibleToolsQuery` 输入对象，对应 `tools/list` 的业务编排 |
| **未来扩展** | `CallTool`、`ImportOpenAPI`、`PublishTool` 等每个业务动作都是一个独立的 Use Case 类 |

简单记：**`domain.py` 定义「业务是什么」，`use_cases.py` 定义「业务怎么一步步做」，`adapters/` 决定「底层用什么做」，`interfaces/` 负责「谁来调用我」。**