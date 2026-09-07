## 一句话总览

**在自定义 ASGI 路由层、SDK Session Manager 之前，插了一个「协议版本门」：Scoped 路径上凡是 `mcp-protocol-version` Header 不是 Modern 版本的请求（包括缺失），一律在协议层用标准 JSON-RPC 错误码 -32022 直接拒掉，连请求体都不解析、Session 都不创建。**

---

## 1. 路由结构：Root 和 Scoped 共享一个 Session Manager

新文件 [http_transport.py](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/interfaces/mcp/http_transport.py) 替代了原来的 `mcp_server.streamable_http_app()`（见 [bootstrap/app.py](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/bootstrap/app.py) 的 diff）：

```python
manager = StreamableHTTPSessionManager(app=server, ..., stateless=False)
handler = StreamableHTTPASGIApp(manager)
app = Starlette(routes=[
    Route("/mcp", endpoint=handler),                        # Root：不做版本门
    Route("/mcp/toolsets/{toolset_slug}",
          endpoint=ModernToolsetEndpoint(handler)),          # Scoped：过门再进 SDK
])
```

关键点：**两条路径共用同一个 `StreamableHTTPSessionManager`**，Modern 请求在 Root 和 Scoped 上的协议协商、Session 管理行为完全一致；Scoped 只是外面多包了一层门。

## 2. 那道门：`ModernToolsetEndpoint`（[L55-L87](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/interfaces/mcp/http_transport.py#L55-L87)）

一个极薄的 ASGI 包装器，干三件事：

```python
async def __call__(self, scope, receive, send):
    if scope["type"] == "http":
        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", ())}          # ① 裸读 ASGI Headers
        requested_version = headers.get("mcp-protocol-version")
        if requested_version != MODERN_PROTOCOL_VERSION:          # ② 不是 2026-07-28 → 拒
            response = JSONResponse({
                "jsonrpc": "2.0", "id": None,
                "error": {
                    "code": UNSUPPORTED_PROTOCOL_VERSION,         # ③ 官方错误码 -32022
                    "message": f"Scoped Toolset endpoints require MCP {MODERN}.",
                    "data": {"errorCode": "unsupported_protocol",
                             "requested": requested_version},     # ④ 业务稳定码 + 诊断
                },
            }, status_code=400)
            await response(scope, receive, send)
            return
    await self._app(scope, receive, send)                         # ⑤ Modern → 原样放行
```

几个实现细节：

| 细节 | 说明 |
|---|---|
| **在 `scope["headers"]` 层面读** | 不依赖 FastAPI，不解析请求体，streaming 友好，开销接近零。latin-1 解码 + lowercase 是 ASGI 规范的 Header 处理标准姿势 |
| **缺失 Header 也拒** | `None != "2026-07-28"` 成立 → fail-closed（默认拒绝），而不是「没带就放行」 |
| **`id: None`** | 门在协议层，不解析 JSON-RPC body，拿不到真实 Request ID，只能回 null——这在协议上是合法的 error 响应 |
| **`code: -32022`** | 来自 SDK 官方常量 `mcp_types.UNSUPPORTED_PROTOCOL_VERSION`（[jsonrpc.py L79](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/.venv/Lib/site-packages/mcp_types/jsonrpc.py#L79)），不是自造数字 |
| **`data.errorCode: "unsupported_protocol"`** | NexusMCP 的稳定业务码，和 [shared/errors.py](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/src/nexusmcp/shared/errors.py) 的 Problem Code 体系（`toolset_not_found` 等）保持同一命名风格；`requested` 回显客户端自报的版本，方便诊断 |

## 3. 为什么必须在 Session Manager 之前拦？

这是设计核心（[实验记录 43](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/docs/实验记录/43_I03-3_ScopedMCPEndpoint.md) 明确写了动机）：

```
Legacy initialize（body: 2025-11-25）
        │
        ▼
ModernToolsetEndpoint ←—— 在这里拒：400 + unsupported_protocol
        │ （不进入 ↓）
StreamableHTTPSessionManager（stateless=False，会为 Legacy 建会话、发 mcp-session-id）
        │
        ▼
SDK Handler → tools/list / tools/call
```

如果放进 Session Manager 才处理，SDK 会为 Legacy 请求**创建真实 Session**（发 `mcp-session-id`、维护会话状态），然后才在 Handler 层报错——等于先给了一个不该存在的会话再撕票。门的位置保证了：**Legacy Scoped 请求永远不产生服务端状态**。而 Root `/mcp` 不设门，完整的 Modern/Legacy 双时代兼容在那里保持不变。

## 4. 最关键的疑问：Modern 客户端为什么不会被误伤？

这道门看起来很凶——**连 SDK 客户端的 `initialize` 都不带 `mcp-protocol-version` Header**。我在 SDK 源码里确认了这一点（[streamable_http.py L568-L571](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/.venv/Lib/site-packages/mcp/client/streamable_http.py#L568-L571)）：

```python
if self._is_initialization_request(message):
    # `initialize` is the negotiation, not a "subsequent request" — discard any
    # probe-stamped value so the discover→fallback path can't leak it onto the handshake.
    self._protocol_version_header = None
```

答案在 SDK v2 的连接时序（[_probe.py](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/.venv/Lib/site-packages/mcp/client/_probe.py) + [session.py L712](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/.venv/Lib/site-packages/mcp/client/session.py#L712)）：

```
Modern SDK 客户端（mode='auto'）连接 /mcp/toolsets/{slug}：
  ① 先发 server/discover 探测，send_discover 显式 stamp Header：
       headers={MCP_PROTOCOL_VERSION_HEADER: "2026-07-28", ...}   ← 有 Header 且是 Modern
  ② 门放行 → 服务器返回 discover 结果 → 客户端 adopt Modern
  ③ adopt 成功后走 discover 会话，不再发 initialize（initialize 仅是 fallback 路径）
  ④ 后续所有请求都带 stamp 过的 Header → 全部过门 ✓

Legacy 客户端（2025-11-25）连接 /mcp/toolsets/{slug}：
  ① 不认识 server/discover，直接发 initialize
  ② Header 缺失或为 Legacy 值 → 门拒绝，400 + -32022 ✓
```

也就是说，这道门利用了 SDK 的 auto 模式协议：**discover 探测自带版本自报，Modern 客户端在证明自己身份之后才会真正开始会话**。门不需要解析 body，仅凭 Header 就完成了无歧义的分流。

## 5. 测试证据

- 契约测试 [test_toolset_scoped_path.py L82-L86](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/tests/contract/mcp/test_toolset_scoped_path.py#L82-L86)：显式构造 Legacy initialize（Header `mcp-protocol-version: 2025-11-25`），断言 `status_code == 400` 且 `error.data == {"errorCode": "unsupported_protocol", "requested": "2025-11-25"}`；
- 集成测试 [test_toolset_scoped_mcp.py L189](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/tests/integration/persistence/test_toolset_scoped_mcp.py#L189)：真实 PostgreSQL 下同样断言；
- 同一测试文件里 Modern 客户端在两个 Scoped 路径上正常 `list_tools` + `call_tool`，证明门没有误伤。

## 6. 值得一提的边界与取舍

- **纵深防御仍在**：即使某个客户端带着 Modern Header 发了 body 版本为 Legacy 的 initialize，门会放行，但 SDK Session Manager 会按 body 协商并自行拒绝——两层校验。
- **`id: None` 是有意的**：门不读 body，代价是无法回显真实 JSON-RPC id；对拒绝响应来说可接受（客户端按 error 处理，不配对 id）。
- **硬编码字符串 `"mcp-protocol-version"`**：没有用 SDK 的 `MCP_PROTOCOL_VERSION_HEADER` 常量（那个在 `mcp.shared.inbound`），小瑕疵，值相同。
- **门槛只此一个判断**：Scoped = Modern-only 是产品决策（[ADR-0020](file:///e:/AI_Projects/LearnProjects/Projects/NexusAI/NexusMCP/docs/adr/0020-toolset-scoped-mcp-endpoints.md)），实现上用最小代码表达了它——没有配置项、没有 Legacy Scoped 的降级路径，拒绝语义确定且可测试。

一句话总结：**用 20 行 ASGI 包装器，在 Session 创建之前，把「Scoped 端点是否 Modern」这个决策前移到协议协商的最早时刻，错误码用官方 -32022，业务码用稳定 `unsupported_protocol`，并精确利用 SDK auto 模式的 discover 自报机制避免误伤 Modern 客户端。**