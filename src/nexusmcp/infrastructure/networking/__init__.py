"""DNS 与 Upstream Egress 网络基础设施。"""

from nexusmcp.infrastructure.networking.egress import (
    StaticUpstreamEndpointPolicy,
    SystemHostResolver,
)

__all__ = ["StaticUpstreamEndpointPolicy", "SystemHostResolver"]
