# NexusMCP Project Rules

## 语言

- 文件路径、标识符、API 和测试名使用英文。
- 内部注释与 Docstring 使用中文，标准技术术语保留英文。
- 协议字段、错误码、Log/Metric/Trace Key 和模型可见错误使用英文。
- 注释解释原因、风险或边界；不复述显而易见的代码，不做中英双语重复。

## 验证

按改动风险选择最小充分验证：

- 仅文档/注释：检查 Diff 并运行 `git diff --check`；未改变行为时不跑测试。
- 小型局部 Python 改动：运行相关测试及受影响路径的 Ruff；类型、签名或 Import 变化时运行 basedpyright。
- 依赖、打包、协议、共享契约或跨模块改动：运行相关完整门禁。
- 里程碑/发版：运行 Frozen Sync、全部测试、Ruff Lint/Format、basedpyright；涉及打包时再运行 Build。
- 只报告实际执行的检查；跳过预期检查时说明原因。
