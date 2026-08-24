# NexusMCP

NexusMCP 是一个使用 Python 实现的 Enterprise MCP Gateway & Registry，负责将企业 HTTP/OpenAPI 服务和已有 MCP Server 纳入统一 Tool Catalog，并在 MCP 调用链上执行身份、策略、凭据、审批、审计与可观测性。

当前阶段：`S1｜协议与 SDK 校准`。

## 当前边界

- MCP `2026-07-28` 为 Modern 主线；
- Legacy Handshake/Session 只做兼容；
- 使用官方 Python MCP SDK v2；
- 当前只建立协议实验、契约测试与文档；
- `src/nexusmcp` 正式业务骨架将在 S1 验收和领域边界评审后创建。

## 本地环境

```powershell
uv sync --frozen
uv run python -m pytest
uv run ruff check .
```

## 文档

- [项目规划](./docs/项目规划/README.md)
- [核心业务主链与 Java 迁移评估](./docs/迁移分析/01_核心业务主链与Java迁移评估.md)
- [S1 协议与 SDK 实验计划](./docs/实验记录/01_S1协议与SDK实验计划.md)
- [业务词汇、核心用例与限界上下文](./docs/架构/01_业务词汇核心用例与限界上下文.md)
- [ADR-0001：Python 项目布局](./docs/adr/0001-python-project-layout.md)
- [ADR-0002：MCP 协议与 SDK Adapter](./docs/adr/0002-mcp-protocol-and-sdk-adapter.md)
