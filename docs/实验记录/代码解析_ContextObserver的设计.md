## `_observe_context` 函数的理解

### 1. 命名拆解

| 部分 | 含义 |
|---|---|
| **`_`** | 模块私有前缀，同上，只在本文件内部使用，不对外导出。 |
| **observe** | 动词，/əbˈzɜːrv/，意思是**「观察、观测、记录」**。不是修改或干预，而是**被动采集**。 |
| **context** | 名词，/ˈkɒntekst/，意思是**「上下文」**。这里特指 MCP SDK 的 `ServerRequestContext` —— 每次请求携带的协议版本、Request ID、HTTP 请求、`_meta` 等运行时环境信息。 |

合起来 **`_observe_context()`** = 「本文件内部使用的、**采集并记录每次请求的上下文快照**的辅助函数」。

---

### 2. 在项目中的职能

#### 核心定位：**S1 实验的「测试探针（Test Probe）」**

它不参与业务逻辑（不返回值、不改状态、不鉴权、不执行 Tool），**唯一作用是把每次请求的关键上下文信息「快照」下来，存入一个列表，供测试用例断言。**

#### 具体采集了什么（[L96-L106](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/examples/mcp_compatibility/dynamic_gateway.py#L96-L106)）

每调用一次，就往全局 `CONTEXT_OBSERVATIONS` 列表追加一条 [ContextObservation](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/examples/mcp_compatibility/dynamic_gateway.py#L18-L28) 记录，包含 8 个字段：

| 字段 | 来源 | 验证目的 |
|---|---|---|
| `protocol_version` | `ctx.protocol_version` | 证明 SDK 正确传递了 MCP 协议版本（Modern 2026-07-28 vs Legacy） |
| `method` | `ctx.method` | 证明 Handler 知道当前处理的是 `tools/list` 还是 `tools/call` |
| `request_id` | `ctx.request_id` | 证明 JSON-RPC Request ID 可被下游拿到（未来用于 Trace 关联） |
| `principal` | 调 `_principal(ctx)` | 证明身份提取链路在两种 Transport 下都工作 |
| `has_http_request` | `ctx.request is not None` | 证明内存/HTTP 两种 Transport 的 Context 结构差异符合预期 |
| `traceparent` | HTTP Header `traceparent` | 证明 W3C Trace Context 可以从 HTTP 透传进来 |
| `mcp_session_id` | HTTP Header `mcp-session-id` | 证明旧版 Session ID 在新版请求中仍可识别（兼容链路） |

可以看到，这 8 个字段正好覆盖了 **S1 协议校准要验证的所有「Context 接缝」**：协议版本、传输层差异、身份、追踪、兼容 —— 这就是为什么注释 [L91](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/examples/mcp_compatibility/dynamic_gateway.py#L91) 写的是：

> 捕获协议版本、Method、Request ID 和 HTTP Header，**证明 Context 接缝可用**。

#### 为什么到处都调用？

你观察得很对 —— 它在 `list_visible_tools()` [L121](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/examples/mcp_compatibility/dynamic_gateway.py#L121) 和 `call_tool()` [L141](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/examples/mcp_compatibility/dynamic_gateway.py#L141) 这两个 MCP Handler 的**第一行**就被调用。

原因：**每个进入 Handler 的请求都必须被观测一次**，这样测试才能断言：
- `tools/list` 请求进来了 → 有 1 条 `method="tools/list"` 的记录
- 紧接着 `tools/call` 请求进来了 → 有 1 条 `method="tools/call"` 的记录
- 两条的 Principal、Protocol Version、Request ID 是否正确
- HTTP 场景下 traceparent 是否拿到了
- 内存场景下 has_http_request 是否为 False

---

### 3. 配合的测试断言（看看真正怎么用）

我们来看对应的测试文件验证一下这个设计意图：
 The user is asking about the `_observe_context` function and wants me to break down its naming, function, and where it's being called throughout the code. I should also reference the corresponding test file to give them a complete picture of how this observation mechanism works in practice.

好，目前这个测试文件里的两个用例只测了业务结果（Tool 可见性和调用权限），还没对 `CONTEXT_OBSERVATIONS` 做断言。那我们再看看和 ASGI/HTTP 相关的测试，那里应该会验证 `traceparent` 和 `mcp_session_id`：

找到确凿证据了。看 [test_asgi_context.py L58-L70](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/tests/contract/mcp/test_asgi_context.py#L58-L70) 的断言部分：

```python
# 从 Handler 侧探针取出 tools/list 的上下文，确认 HTTP 信息贯穿到了协议 Adapter。
tools_list_context = next(
    observation for observation in CONTEXT_OBSERVATIONS if observation.method == "tools/list"
)
assert tools_list_context.protocol_version == "2026-07-28"
assert tools_list_context.principal == "operator"
assert tools_list_context.has_http_request is True
assert tools_list_context.request_id != "None"
assert tools_list_context.mcp_session_id is None
assert tools_list_context.traceparent == "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
```

**`_observe_context()` 采集的数据，就是被这段断言消费的。** 它验证了：

1. FastAPI 层接收的 HTTP Header（principal、traceparent）**一路贯穿到了** MCP SDK 低层 Handler；
2. SDK 传递的 `protocol_version`、`request_id`、`method` 都正确；
3. HTTP 场景下 `has_http_request` 是 `True`（和内存 Transport 场景可区分）。

---

### 4. 总结：为什么这是「探针」而不是「正式审计」

文件顶部 [L31-L32](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/examples/mcp_compatibility/dynamic_gateway.py#L31-L32) 已经注释清楚了它的边界：

> 仅用于测试断言，**不是正式的 Trace/Audit 存储**，也**不适用于并发生产请求**。

| 维度 | `_observe_context`（S1 实验探针） | 正式 Audit/Trace（未来） |
|---|---|---|
| 存储 | 全局 `list`，内存，进程级 | PostgreSQL / OpenSearch / OTel Collector |
| 并发安全 | ❌ 无锁，只跑单线程测试 | ✅ 队列 + 批量写入 |
| 数据完整性 | 8 个字段，够断言即可 | 请求全链路、入参摘要、策略决策、凭据引用、延迟、上游响应等 |
| 调用时机 | Handler 第一行手工调 | Middleware / Interceptor 自动注入 |
| 生命周期 | 测试前 clear，测试后断言 | 持久化、可搜索、可告警 |

---

### 职能总览图

```
  MCP Request（Memory 或 HTTP）
        │
        ▼
  list_visible_tools / call_tool  ← 两个 Handler 的第一行都调用
        │
        ▼
  _observe_context(ctx)  ←── 你问的函数
        │
        ├─ 提取 protocol_version / method / request_id（来自 SDK Context）
        ├─ 提取 principal（复用 _principal()）
        ├─ 提取 has_http_request / traceparent / mcp_session_id（来自 HTTP Header）
        │
        ▼
  CONTEXT_OBSERVATIONS.append(ContextObservation(...))
        │
        ▼  测试代码消费
  test_asgi_context.py: L58-L70 断言确认所有 Context 接缝贯通 ✓
```

**一句话：`_observe_context` 是 S1 实验专门为测试打的「洞」，把 SDK Context 内部状态「引」出来给 pytest 看，证明「Context 接缝是通的」。正式项目会被 OTel + Audit Logging 中间件替代。**