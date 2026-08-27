"""Upstream Egress Policy Port。"""

from typing import Protocol


class UpstreamEndpointPolicy(Protocol):
    async def validate(self, endpoint: str) -> None: ...


class AllowAllUpstreamEndpointPolicy:
    """只用于未启用安全策略的开发模式和隔离单元测试。"""

    async def validate(self, endpoint: str) -> None:
        _ = endpoint
