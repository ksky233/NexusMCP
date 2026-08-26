"""Registry Register/Update/Disable 与安全配置测试。"""

from collections.abc import Iterator

import pytest

from nexusmcp.modules.registry.adapters.in_memory import InMemoryUpstreamRepository
from nexusmcp.modules.registry.adapters.in_memory_uow import InMemoryRegistryUnitOfWorkFactory
from nexusmcp.modules.registry.domain import UpstreamStatus
from nexusmcp.modules.registry.use_cases import (
    DisableUpstream,
    DisableUpstreamCommand,
    ListUpstreams,
    RegisterUpstream,
    RegisterUpstreamCommand,
    UpdateUpstream,
    UpdateUpstreamCommand,
)
from nexusmcp.shared.errors import InvalidArgumentsError, UpstreamConflictError
from nexusmcp.shared.request_context import ActorContext


class SequenceIdentifierGenerator:
    def __init__(self, *values: str) -> None:
        self._values: Iterator[str] = iter(values)

    def new_id(self) -> str:
        return next(self._values)


def context() -> ActorContext:
    return ActorContext(
        request_id="request-registry",
        trace_id="8" * 32,
        tenant_id="tenant-a",
        principal_id="admin-a",
        authn_method="test",
    )


def register_command(**overrides: object) -> RegisterUpstreamCommand:
    values = {
        "context": context(),
        "namespace": "directory",
        "name": "employee-directory-api",
        "description": "Employee Directory",
        "owner": "people-platform",
        "endpoint": "http://127.0.0.1:9001",
        "auth_scheme": "none",
        "config": {"timeout_seconds": 5},
    }
    values.update(overrides)
    return RegisterUpstreamCommand(**values)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_register_update_list_and_disable_upstream() -> None:
    repository = InMemoryUpstreamRepository()
    factory = InMemoryRegistryUnitOfWorkFactory(repository)
    registered = await RegisterUpstream(
        factory,
        SequenceIdentifierGenerator("upstream-1"),
    ).execute(register_command())

    assert registered.status is UpstreamStatus.ACTIVE
    assert await ListUpstreams(factory).execute(context()) == (registered,)

    updated = await UpdateUpstream(factory).execute(
        UpdateUpstreamCommand(
            context=context(),
            upstream_service_id=registered.id,
            description="Updated directory",
            owner="platform-team",
            endpoint="http://127.0.0.1:9011",
            auth_scheme="none",
            config={"timeout_seconds": 10},
        )
    )
    disabled = await DisableUpstream(factory).execute(
        DisableUpstreamCommand(
            context=context(),
            upstream_service_id=registered.id,
        )
    )

    assert updated.endpoint == "http://127.0.0.1:9011"
    assert disabled.status is UpstreamStatus.DISABLED


@pytest.mark.asyncio
async def test_duplicate_upstream_is_rejected() -> None:
    repository = InMemoryUpstreamRepository()
    factory = InMemoryRegistryUnitOfWorkFactory(repository)
    register = RegisterUpstream(
        factory,
        SequenceIdentifierGenerator("upstream-1", "upstream-2"),
    )
    await register.execute(register_command())

    with pytest.raises(UpstreamConflictError):
        await register.execute(register_command())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"endpoint": "ftp://internal.example.test"},
        {"endpoint": "http://user:password@internal.example.test"},
        {"config": {"nested": {"api_key": "do-not-store"}}},
        {"namespace": "Invalid Namespace"},
        {"namespace": "nexus"},
    ],
)
async def test_registry_rejects_invalid_or_sensitive_configuration(
    overrides: dict[str, object],
) -> None:
    use_case = RegisterUpstream(
        InMemoryRegistryUnitOfWorkFactory(InMemoryUpstreamRepository()),
        SequenceIdentifierGenerator("upstream-1"),
    )

    with pytest.raises(InvalidArgumentsError):
        await use_case.execute(register_command(**overrides))
