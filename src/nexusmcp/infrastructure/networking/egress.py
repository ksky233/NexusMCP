"""静态 Host/CIDR/Port Allowlist 与 DNS 执行时复检。"""

import asyncio
import ipaddress
import socket
from collections.abc import Iterable
from typing import Protocol
from urllib.parse import urlsplit

from nexusmcp.shared.errors import UnsafeUpstreamEndpointError

type IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
type IpNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

_METADATA_ADDRESSES = frozenset(
    {
        ipaddress.ip_address("100.100.100.200"),
        ipaddress.ip_address("169.254.169.254"),
    }
)
_METADATA_HOSTS = frozenset(
    {
        "metadata.google.internal",
        "metadata.google.internal.",
    }
)
_LOCAL_DEMO_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class HostResolver(Protocol):
    async def resolve(self, host: str, port: int) -> tuple[IpAddress, ...]: ...


class SystemHostResolver:
    async def resolve(self, host: str, port: int) -> tuple[IpAddress, ...]:
        try:
            results = await asyncio.get_running_loop().getaddrinfo(
                host,
                port,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            )
        except (socket.gaierror, OSError):
            raise UnsafeUpstreamEndpointError("upstream endpoint DNS resolution failed") from None
        addresses = {
            ipaddress.ip_address(sockaddr[0])
            for _family, _type, _proto, _canonical_name, sockaddr in results
        }
        if not addresses:
            raise UnsafeUpstreamEndpointError("upstream endpoint DNS returned no addresses")
        return tuple(sorted(addresses, key=lambda address: (address.version, int(address))))


class StaticUpstreamEndpointPolicy:
    def __init__(
        self,
        *,
        resolver: HostResolver,
        allowed_hosts: Iterable[str] = (),
        allowed_cidrs: Iterable[str] = (),
        allowed_ports: Iterable[int] = (80, 443),
        allow_local_demo: bool = False,
    ) -> None:
        self._resolver = resolver
        self._allowed_hosts = frozenset(_normalize_host(host) for host in allowed_hosts)
        try:
            self._allowed_networks: tuple[IpNetwork, ...] = tuple(
                ipaddress.ip_network(cidr, strict=False) for cidr in allowed_cidrs
            )
        except ValueError:
            raise ValueError("egress allowed CIDR was invalid") from None
        self._allowed_ports = frozenset(allowed_ports)
        if not self._allowed_ports or any(
            isinstance(port, bool) or not 1 <= port <= 65535 for port in self._allowed_ports
        ):
            raise ValueError("egress allowed ports were invalid")
        self._allow_local_demo = allow_local_demo

    async def validate(self, endpoint: str) -> None:
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
            raise UnsafeUpstreamEndpointError("upstream endpoint scheme or host was invalid")
        if parsed.username is not None or parsed.password is not None:
            raise UnsafeUpstreamEndpointError("upstream endpoint contained URL credentials")
        if parsed.fragment:
            raise UnsafeUpstreamEndpointError("upstream endpoint contained a fragment")
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError:
            raise UnsafeUpstreamEndpointError("upstream endpoint port was invalid") from None
        if port not in self._allowed_ports:
            raise UnsafeUpstreamEndpointError("upstream endpoint port was not allowed")

        try:
            host = _normalize_host(parsed.hostname)
        except ValueError:
            raise UnsafeUpstreamEndpointError("upstream endpoint host was invalid") from None
        if host in _METADATA_HOSTS:
            raise UnsafeUpstreamEndpointError("upstream endpoint targeted cloud metadata")
        literal_address = _literal_address(host)
        if literal_address is not None:
            self._validate_address(literal_address, host=host)
            return
        if host not in self._allowed_hosts:
            raise UnsafeUpstreamEndpointError("upstream endpoint host was not allowlisted")
        addresses = await self._resolver.resolve(host, port)
        for address in addresses:
            self._validate_address(address, host=host)

    def _validate_address(self, address: IpAddress, *, host: str) -> None:
        if address.is_loopback:
            if self._allow_local_demo and host in _LOCAL_DEMO_HOSTS:
                return
            raise UnsafeUpstreamEndpointError("upstream endpoint resolved to loopback")
        if (
            address in _METADATA_ADDRESSES
            or address.is_link_local
            or address.is_unspecified
            or address.is_multicast
            or address.is_reserved
        ):
            raise UnsafeUpstreamEndpointError("upstream endpoint resolved to a hard-denied address")
        if host in self._allowed_hosts:
            return
        if not any(address in network for network in self._allowed_networks):
            raise UnsafeUpstreamEndpointError("upstream endpoint address was not allowlisted")


def _normalize_host(value: str) -> str:
    host = value.strip().rstrip(".").lower()
    if not host:
        raise ValueError("egress allowed host must not be blank")
    if "%" in host:
        raise ValueError("IPv6 zone identifiers are not allowed in egress hosts")
    if _literal_address(host) is None and any(
        character.isspace() or character in "/\\@:" for character in host
    ):
        raise ValueError("egress allowed host was invalid")
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        raise ValueError("egress allowed host was invalid") from None


def _literal_address(host: str) -> IpAddress | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None
