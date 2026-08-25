"""供 Contract Test 使用的确定性内存 ToolBinding Adapter。"""

from __future__ import annotations

from collections.abc import Iterable

from nexusmcp.modules.connectors.domain import ToolBinding


class InMemoryToolBindingRepository:
    def __init__(self, bindings: Iterable[ToolBinding] = ()) -> None:
        self._bindings = {binding.id: binding for binding in bindings}
        self._validate_seed_uniqueness()

    async def add(self, tenant_id: str, binding: ToolBinding) -> None:
        _require_matching_tenant(tenant_id, binding.tenant_id)
        if binding.id in self._bindings:
            raise ValueError("tool binding id already exists")
        if await self.get_by_tool_version(tenant_id, binding.tool_version_id) is not None:
            raise ValueError("tool version already has a binding")
        self._bindings[binding.id] = binding

    async def save(self, tenant_id: str, binding: ToolBinding) -> None:
        _require_matching_tenant(tenant_id, binding.tenant_id)
        current = self._bindings.get(binding.id)
        if current is None or current.tenant_id != tenant_id:
            raise ValueError("tool binding does not exist in tenant")
        version_owner = await self.get_by_tool_version(tenant_id, binding.tool_version_id)
        if version_owner is not None and version_owner.id != binding.id:
            raise ValueError("tool version already has a binding")
        self._bindings[binding.id] = binding

    async def get_by_id(
        self,
        tenant_id: str,
        binding_id: str,
    ) -> ToolBinding | None:
        binding = self._bindings.get(binding_id)
        return binding if binding is not None and binding.tenant_id == tenant_id else None

    async def get_by_tool_version(
        self,
        tenant_id: str,
        tool_version_id: str,
    ) -> ToolBinding | None:
        return next(
            (
                binding
                for binding in self._bindings.values()
                if binding.tenant_id == tenant_id and binding.tool_version_id == tool_version_id
            ),
            None,
        )

    async def get_for_update(
        self,
        tenant_id: str,
        binding_id: str,
    ) -> ToolBinding | None:
        # PostgreSQL Adapter 会把同一意图映射为 SELECT ... FOR UPDATE。
        return await self.get_by_id(tenant_id, binding_id)

    def clone(self) -> InMemoryToolBindingRepository:
        """为 InMemory Unit of Work 创建事务内隔离副本。"""

        return InMemoryToolBindingRepository(self._bindings.values())

    def replace_with(self, repository: InMemoryToolBindingRepository) -> None:
        """一次替换完整内存状态，模拟原子 Commit 的可观察结果。"""

        self._bindings = dict(repository._bindings)

    def _validate_seed_uniqueness(self) -> None:
        versions = [binding.tool_version_id for binding in self._bindings.values()]
        if len(versions) != len(set(versions)):
            raise ValueError("tool version already has a binding")


def _require_matching_tenant(requested_tenant_id: str, entity_tenant_id: str) -> None:
    if requested_tenant_id != entity_tenant_id:
        raise ValueError("entity tenant does not match repository tenant scope")
