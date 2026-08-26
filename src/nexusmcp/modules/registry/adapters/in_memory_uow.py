"""Registry 写用例的 InMemory Unit of Work。"""

from __future__ import annotations

from types import TracebackType

from nexusmcp.modules.registry.adapters.in_memory import InMemoryUpstreamRepository


class InMemoryRegistryUnitOfWork:
    def __init__(self, upstreams: InMemoryUpstreamRepository) -> None:
        self._committed_upstreams = upstreams
        self._transaction_upstreams: InMemoryUpstreamRepository | None = None

    @property
    def upstreams(self) -> InMemoryUpstreamRepository:
        if self._transaction_upstreams is None:
            raise RuntimeError("unit of work must be entered before accessing repositories")
        return self._transaction_upstreams

    async def __aenter__(self) -> InMemoryRegistryUnitOfWork:
        if self._transaction_upstreams is not None:
            raise RuntimeError("unit of work does not support nested entry")
        self._transaction_upstreams = self._committed_upstreams.clone()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._transaction_upstreams = None

    async def commit(self) -> None:
        self._committed_upstreams.replace_with(self.upstreams)

    async def rollback(self) -> None:
        _ = self.upstreams
        self._transaction_upstreams = self._committed_upstreams.clone()


class InMemoryRegistryUnitOfWorkFactory:
    def __init__(self, upstreams: InMemoryUpstreamRepository) -> None:
        self._upstreams = upstreams

    def __call__(self) -> InMemoryRegistryUnitOfWork:
        return InMemoryRegistryUnitOfWork(self._upstreams)
