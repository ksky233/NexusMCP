"""NexusMCP 企业级 MCP 网关与注册中心。"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("nexusmcp")
except PackageNotFoundError:  # pragma: no cover - 仅可能发生在未安装 Package 的环境
    __version__ = "0.0.0"

__all__ = ["__version__"]
