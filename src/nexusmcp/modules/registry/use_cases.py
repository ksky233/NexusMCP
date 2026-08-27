"""Upstream Registry 的注册、更新、禁用与查询 Use Case。"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from nexusmcp.modules.registry.domain import (
    UpstreamService,
    UpstreamServiceType,
    UpstreamStatus,
)
from nexusmcp.modules.registry.egress_ports import (
    AllowAllUpstreamEndpointPolicy,
    UpstreamEndpointPolicy,
)
from nexusmcp.modules.registry.ports import RegistryUnitOfWorkFactory
from nexusmcp.shared.errors import (
    InvalidArgumentsError,
    UpstreamConflictError,
    UpstreamNotFoundError,
)
from nexusmcp.shared.identifiers import IdentifierGenerator
from nexusmcp.shared.request_context import ActorContext
from nexusmcp.shared.tool_namespaces import is_reserved_tool_namespace

_NAMESPACE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SENSITIVE_CONFIG_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "authorization_header",
    "client_secret",
    "cookie",
    "credential",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "token",
}


@dataclass(frozen=True, slots=True)
class RegisterUpstreamCommand:
    context: ActorContext
    namespace: str
    name: str
    description: str | None
    owner: str
    endpoint: str
    auth_scheme: str | None
    config: Mapping[str, Any]
    service_type: UpstreamServiceType = UpstreamServiceType.HTTP
    transport_type: str = "http"


@dataclass(frozen=True, slots=True)
class UpdateUpstreamCommand:
    context: ActorContext
    upstream_service_id: str
    description: str | None
    owner: str
    endpoint: str
    auth_scheme: str | None
    config: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class DisableUpstreamCommand:
    context: ActorContext
    upstream_service_id: str


class RegisterUpstream:
    def __init__(
        self,
        unit_of_work_factory: RegistryUnitOfWorkFactory,
        identifier_generator: IdentifierGenerator,
        endpoint_policy: UpstreamEndpointPolicy | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._identifier_generator = identifier_generator
        self._endpoint_policy = endpoint_policy or AllowAllUpstreamEndpointPolicy()

    async def execute(self, command: RegisterUpstreamCommand) -> UpstreamService:
        _validate_namespace(command.namespace)
        if not command.name.strip():
            raise InvalidArgumentsError("upstream name must not be blank")
        if not command.transport_type.strip():
            raise InvalidArgumentsError("upstream transport type must not be blank")
        _validate_registration(
            owner=command.owner,
            endpoint=command.endpoint,
            config=command.config,
            service_type=command.service_type,
        )
        await self._endpoint_policy.validate(command.endpoint)
        tenant_id = command.context.tenant_id
        async with self._unit_of_work_factory() as unit_of_work:
            existing = await unit_of_work.upstreams.get_by_name(
                tenant_id,
                command.namespace,
                command.name,
            )
            if existing is not None:
                raise UpstreamConflictError(
                    f"upstream {command.namespace}/{command.name} already exists"
                )
            upstream = UpstreamService(
                id=self._identifier_generator.new_id(),
                tenant_id=tenant_id,
                namespace=command.namespace,
                name=command.name,
                description=command.description,
                owner=command.owner,
                service_type=command.service_type,
                transport_type=command.transport_type,
                endpoint=command.endpoint,
                protocol_min=None,
                protocol_max=None,
                auth_scheme=command.auth_scheme,
                config=dict(command.config),
                status=UpstreamStatus.ACTIVE,
            )
            await unit_of_work.upstreams.add(tenant_id, upstream)
            await unit_of_work.commit()
        return upstream


class UpdateUpstream:
    def __init__(
        self,
        unit_of_work_factory: RegistryUnitOfWorkFactory,
        endpoint_policy: UpstreamEndpointPolicy | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._endpoint_policy = endpoint_policy or AllowAllUpstreamEndpointPolicy()

    async def execute(self, command: UpdateUpstreamCommand) -> UpstreamService:
        tenant_id = command.context.tenant_id
        async with self._unit_of_work_factory() as observer_unit_of_work:
            observed = await observer_unit_of_work.upstreams.get_by_id(
                tenant_id,
                command.upstream_service_id,
            )
        if observed is None:
            raise UpstreamNotFoundError(
                f"upstream {command.upstream_service_id} was not found in tenant"
            )
        _validate_registration(
            owner=command.owner,
            endpoint=command.endpoint,
            config=command.config,
            service_type=observed.service_type,
        )
        # DNS/Policy 检查必须在写事务之外，避免数据库行锁跨越网络调用。
        await self._endpoint_policy.validate(command.endpoint)
        async with self._unit_of_work_factory() as unit_of_work:
            upstream = await unit_of_work.upstreams.get_for_update(
                tenant_id,
                command.upstream_service_id,
            )
            if upstream is None:
                raise UpstreamNotFoundError(
                    f"upstream {command.upstream_service_id} was not found in tenant"
                )
            updated = upstream.update(
                description=command.description,
                owner=command.owner,
                endpoint=command.endpoint,
                auth_scheme=command.auth_scheme,
                config=dict(command.config),
            )
            await unit_of_work.upstreams.save(tenant_id, updated)
            await unit_of_work.commit()
        return updated


class DisableUpstream:
    def __init__(self, unit_of_work_factory: RegistryUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def execute(self, command: DisableUpstreamCommand) -> UpstreamService:
        tenant_id = command.context.tenant_id
        async with self._unit_of_work_factory() as unit_of_work:
            upstream = await unit_of_work.upstreams.get_for_update(
                tenant_id,
                command.upstream_service_id,
            )
            if upstream is None:
                raise UpstreamNotFoundError(
                    f"upstream {command.upstream_service_id} was not found in tenant"
                )
            disabled = upstream.disable()
            await unit_of_work.upstreams.save(tenant_id, disabled)
            await unit_of_work.commit()
        return disabled


class ListUpstreams:
    def __init__(self, unit_of_work_factory: RegistryUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def execute(self, context: ActorContext) -> tuple[UpstreamService, ...]:
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.upstreams.list_by_tenant(context.tenant_id)


def _validate_namespace(namespace: str) -> None:
    if not _NAMESPACE_PATTERN.fullmatch(namespace):
        raise InvalidArgumentsError("upstream namespace is invalid")
    if is_reserved_tool_namespace(namespace):
        raise InvalidArgumentsError("upstream namespace is reserved by NexusMCP")


def _validate_registration(
    *,
    owner: str,
    endpoint: str,
    config: Mapping[str, Any],
    service_type: UpstreamServiceType,
) -> None:
    if not owner.strip():
        raise InvalidArgumentsError("upstream owner must not be blank")
    if not endpoint.strip():
        raise InvalidArgumentsError("upstream endpoint must not be blank")
    if service_type is UpstreamServiceType.HTTP:
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise InvalidArgumentsError("HTTP upstream endpoint must use http or https")
        if parsed.username is not None or parsed.password is not None:
            raise InvalidArgumentsError("upstream endpoint must not contain credentials")
    if _contains_sensitive_key(config):
        raise InvalidArgumentsError("upstream config must not contain secret values")


def _contains_sensitive_key(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized_key = str(key).strip().lower().replace("-", "_")
            if normalized_key in _SENSITIVE_CONFIG_KEYS or _contains_sensitive_key(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False
