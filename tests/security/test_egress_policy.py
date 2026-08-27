"""Static Egress Allowlist、Metadata Hard Deny 与 DNS 复检安全测试。"""

import ipaddress

import pytest

from nexusmcp.infrastructure.networking.egress import StaticUpstreamEndpointPolicy
from nexusmcp.shared.errors import UnsafeUpstreamEndpointError


class MutableResolver:
    def __init__(self, addresses: dict[str, tuple[str, ...]]) -> None:
        self.addresses = addresses
        self.calls: list[tuple[str, int]] = []

    async def resolve(
        self,
        host: str,
        port: int,
    ) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
        self.calls.append((host, port))
        return tuple(ipaddress.ip_address(value) for value in self.addresses[host])


@pytest.mark.asyncio
async def test_allowlisted_enterprise_host_and_private_cidr_are_permitted() -> None:
    resolver = MutableResolver({"employee-api.corp.example": ("10.20.1.5",)})
    policy = StaticUpstreamEndpointPolicy(
        resolver=resolver,
        allowed_hosts=("employee-api.corp.example",),
        allowed_cidrs=("10.20.0.0/16",),
        allowed_ports=(443, 8443),
    )

    await policy.validate("https://employee-api.corp.example:8443/api")
    await policy.validate("https://10.20.1.7/api")

    assert resolver.calls == [("employee-api.corp.example", 8443)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint",
    [
        "file:///etc/passwd",
        "http://user:password@employee-api.corp.example",
        "https://employee-api.corp.example:9443",
        "https://untrusted.example.test",
        "http://[fe80::1%25eth0]",
        "http://169.254.169.254/latest/meta-data",
        "http://100.100.100.200/latest/meta-data",
        "http://metadata.google.internal/computeMetadata/v1",
    ],
)
async def test_untrusted_scheme_authority_port_and_metadata_are_rejected(
    endpoint: str,
) -> None:
    policy = StaticUpstreamEndpointPolicy(
        resolver=MutableResolver(
            {
                "employee-api.corp.example": ("10.20.1.5",),
                "untrusted.example.test": ("203.0.113.10",),
            }
        ),
        allowed_hosts=("employee-api.corp.example", "metadata.google.internal"),
        allowed_cidrs=("10.20.0.0/16", "100.64.0.0/10", "169.254.0.0/16"),
        allowed_ports=(80, 443),
    )

    with pytest.raises(UnsafeUpstreamEndpointError):
        await policy.validate(endpoint)


@pytest.mark.asyncio
async def test_mixed_dns_answer_and_rebinding_change_fail_closed() -> None:
    resolver = MutableResolver({"inventory-api.corp.example": ("10.20.1.5",)})
    policy = StaticUpstreamEndpointPolicy(
        resolver=resolver,
        allowed_hosts=("inventory-api.corp.example",),
        allowed_ports=(443,),
    )

    await policy.validate("https://inventory-api.corp.example")
    resolver.addresses["inventory-api.corp.example"] = (
        "10.20.1.5",
        "169.254.169.254",
    )

    with pytest.raises(UnsafeUpstreamEndpointError):
        await policy.validate("https://inventory-api.corp.example")
    assert resolver.calls == [
        ("inventory-api.corp.example", 443),
        ("inventory-api.corp.example", 443),
    ]


@pytest.mark.asyncio
async def test_loopback_requires_explicit_local_demo_mode() -> None:
    resolver = MutableResolver({"localhost": ("127.0.0.1", "::1")})
    denied = StaticUpstreamEndpointPolicy(
        resolver=resolver,
        allowed_hosts=("localhost",),
        allowed_ports=(9001,),
    )
    allowed = StaticUpstreamEndpointPolicy(
        resolver=resolver,
        allowed_hosts=("localhost",),
        allowed_ports=(9001,),
        allow_local_demo=True,
    )

    with pytest.raises(UnsafeUpstreamEndpointError):
        await denied.validate("http://localhost:9001")
    await allowed.validate("http://localhost:9001")
    await allowed.validate("http://127.0.0.1:9001")
