"""ToolBindingRepository 的 SQLAlchemy Async Adapter。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.modules.connectors.adapters.sqlalchemy_mapping import (
    tool_binding_from_model,
    tool_binding_to_model,
    update_tool_binding_model,
)
from nexusmcp.modules.connectors.adapters.sqlalchemy_models import ToolBindingModel
from nexusmcp.modules.connectors.domain import ToolBinding


class SqlAlchemyToolBindingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, tenant_id: str, binding: ToolBinding) -> None:
        _require_matching_tenant(tenant_id, binding.tenant_id)
        self._session.add(tool_binding_to_model(binding))
        await self._session.flush()

    async def save(self, tenant_id: str, binding: ToolBinding) -> None:
        _require_matching_tenant(tenant_id, binding.tenant_id)
        model = await self._get_model(tenant_id, binding.id)
        if model is None:
            raise ValueError("tool binding does not exist in tenant")
        update_tool_binding_model(model, binding)
        await self._session.flush()

    async def get_by_id(
        self,
        tenant_id: str,
        binding_id: str,
    ) -> ToolBinding | None:
        model = await self._get_model(tenant_id, binding_id)
        return tool_binding_from_model(model) if model is not None else None

    async def get_by_tool_version(
        self,
        tenant_id: str,
        tool_version_id: str,
    ) -> ToolBinding | None:
        tenant_uuid = as_uuid(tenant_id, field_name="tenant id")
        version_uuid = as_uuid(tool_version_id, field_name="tool version id")
        model = await self._session.scalar(
            select(ToolBindingModel).where(
                ToolBindingModel.tenant_id == tenant_uuid,
                ToolBindingModel.tool_version_id == version_uuid,
            )
        )
        return tool_binding_from_model(model) if model is not None else None

    async def get_for_update(
        self,
        tenant_id: str,
        binding_id: str,
    ) -> ToolBinding | None:
        tenant_uuid = as_uuid(tenant_id, field_name="tenant id")
        binding_uuid = as_uuid(binding_id, field_name="tool binding id")
        model = await self._session.scalar(
            select(ToolBindingModel)
            .where(
                ToolBindingModel.tenant_id == tenant_uuid,
                ToolBindingModel.id == binding_uuid,
            )
            .with_for_update()
        )
        return tool_binding_from_model(model) if model is not None else None

    async def _get_model(
        self,
        tenant_id: str,
        binding_id: str,
    ) -> ToolBindingModel | None:
        tenant_uuid = as_uuid(tenant_id, field_name="tenant id")
        binding_uuid = as_uuid(binding_id, field_name="tool binding id")
        return await self._session.scalar(
            select(ToolBindingModel).where(
                ToolBindingModel.tenant_id == tenant_uuid,
                ToolBindingModel.id == binding_uuid,
            )
        )


def _require_matching_tenant(requested_tenant_id: str, entity_tenant_id: str) -> None:
    if requested_tenant_id != entity_tenant_id:
        raise ValueError("entity tenant does not match repository tenant scope")
