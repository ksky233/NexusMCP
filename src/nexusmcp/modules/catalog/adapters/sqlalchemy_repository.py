"""ToolCatalogRepository 的 SQLAlchemy Async Adapter。"""

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.modules.catalog.adapters.sqlalchemy_mapping import (
    published_tool_from_models,
    tool_from_model,
    tool_to_model,
    tool_version_from_model,
    tool_version_to_model,
    update_tool_model,
    update_tool_version_model,
)
from nexusmcp.modules.catalog.adapters.sqlalchemy_models import ToolModel, ToolVersionModel
from nexusmcp.modules.catalog.domain import (
    PublishedTool,
    Tool,
    ToolStatus,
    ToolVersion,
    ToolVersionStatus,
)
from nexusmcp.modules.connectors.adapters.sqlalchemy_models import ToolBindingModel
from nexusmcp.modules.connectors.domain import ToolBindingStatus


class SqlAlchemyToolCatalogRepository:
    """使用显式 Query/Mapping 实现 Catalog Port，不向外返回 ORM Model。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_tool(self, tenant_id: str, tool: Tool) -> None:
        _require_matching_tenant(tenant_id, tool.tenant_id)
        self._session.add(tool_to_model(tool))
        await self._session.flush()

    async def save_tool(self, tenant_id: str, tool: Tool) -> None:
        _require_matching_tenant(tenant_id, tool.tenant_id)
        model = await self._get_tool_model(tenant_id, tool.id)
        if model is None:
            raise ValueError("tool does not exist in tenant")
        update_tool_model(model, tool)
        await self._session.flush()

    async def get_tool_by_id(self, tenant_id: str, tool_id: str) -> Tool | None:
        model = await self._get_tool_model(tenant_id, tool_id)
        return tool_from_model(model) if model is not None else None

    async def get_tool_by_name(
        self,
        tenant_id: str,
        canonical_name: str,
    ) -> Tool | None:
        tenant_uuid = as_uuid(tenant_id, field_name="tenant id")
        model = await self._session.scalar(
            select(ToolModel).where(
                ToolModel.tenant_id == tenant_uuid,
                ToolModel.canonical_name == canonical_name,
            )
        )
        return tool_from_model(model) if model is not None else None

    async def get_tool_by_name_for_update(
        self,
        tenant_id: str,
        canonical_name: str,
    ) -> Tool | None:
        tenant_uuid = as_uuid(tenant_id, field_name="tenant id")
        model = await self._session.scalar(
            select(ToolModel)
            .where(
                ToolModel.tenant_id == tenant_uuid,
                ToolModel.canonical_name == canonical_name,
            )
            .with_for_update()
        )
        return tool_from_model(model) if model is not None else None

    async def get_tool_for_update(self, tenant_id: str, tool_id: str) -> Tool | None:
        tenant_uuid = as_uuid(tenant_id, field_name="tenant id")
        tool_uuid = as_uuid(tool_id, field_name="tool id")
        model = await self._session.scalar(
            select(ToolModel)
            .where(
                ToolModel.tenant_id == tenant_uuid,
                ToolModel.id == tool_uuid,
            )
            .with_for_update()
        )
        return tool_from_model(model) if model is not None else None

    async def add_version(self, tenant_id: str, version: ToolVersion) -> None:
        _require_matching_tenant(tenant_id, version.tenant_id)
        tool_model = await self._get_tool_model(tenant_id, version.tool_id)
        if tool_model is None:
            raise ValueError("tool version parent does not exist in tenant")
        self._session.add(
            tool_version_to_model(
                version,
                namespace=tool_model.namespace,
                canonical_name=tool_model.canonical_name,
            )
        )
        await self._session.flush()

    async def save_version(self, tenant_id: str, version: ToolVersion) -> None:
        _require_matching_tenant(tenant_id, version.tenant_id)
        model = await self._get_version_model(tenant_id, version.id)
        if model is None:
            raise ValueError("tool version does not exist in tenant")
        tool_model = await self._get_tool_model(tenant_id, version.tool_id)
        if tool_model is None:
            raise ValueError("tool version parent does not exist in tenant")
        update_tool_version_model(
            model,
            version,
            namespace=tool_model.namespace,
            canonical_name=tool_model.canonical_name,
        )
        await self._session.flush()

    async def get_version_by_id(
        self,
        tenant_id: str,
        tool_version_id: str,
    ) -> ToolVersion | None:
        model = await self._get_version_model(tenant_id, tool_version_id)
        return tool_version_from_model(model) if model is not None else None

    async def get_version_for_update(
        self,
        tenant_id: str,
        tool_version_id: str,
    ) -> ToolVersion | None:
        tenant_uuid = as_uuid(tenant_id, field_name="tenant id")
        version_uuid = as_uuid(tool_version_id, field_name="tool version id")
        model = await self._session.scalar(
            select(ToolVersionModel)
            .where(
                ToolVersionModel.tenant_id == tenant_uuid,
                ToolVersionModel.id == version_uuid,
            )
            .with_for_update()
        )
        return tool_version_from_model(model) if model is not None else None

    async def get_published_version(
        self,
        tenant_id: str,
        tool_id: str,
    ) -> ToolVersion | None:
        tenant_uuid = as_uuid(tenant_id, field_name="tenant id")
        tool_uuid = as_uuid(tool_id, field_name="tool id")
        model = await self._session.scalar(
            select(ToolVersionModel).where(
                ToolVersionModel.tenant_id == tenant_uuid,
                ToolVersionModel.tool_id == tool_uuid,
                ToolVersionModel.status == ToolVersionStatus.PUBLISHED.value,
            )
        )
        return tool_version_from_model(model) if model is not None else None

    async def next_version_number(self, tenant_id: str, tool_id: str) -> int:
        next_version = await self._session.scalar(
            select(func.coalesce(func.max(ToolVersionModel.version), 0) + 1).where(
                ToolVersionModel.tenant_id == as_uuid(tenant_id, field_name="tenant id"),
                ToolVersionModel.tool_id == as_uuid(tool_id, field_name="tool id"),
            )
        )
        return int(next_version or 1)

    async def list_published_by_tenant(self, tenant_id: str) -> tuple[PublishedTool, ...]:
        statement = self._published_statement(tenant_id).order_by(ToolModel.canonical_name)
        rows = (await self._session.execute(statement)).tuples().all()
        return tuple(published_tool_from_models(tool, version) for tool, version in rows)

    async def get_published_by_name(
        self,
        tenant_id: str,
        canonical_name: str,
    ) -> PublishedTool | None:
        statement = self._published_statement(tenant_id).where(
            ToolModel.canonical_name == canonical_name
        )
        row = (await self._session.execute(statement)).tuples().one_or_none()
        if row is None:
            return None
        tool, version = row
        return published_tool_from_models(tool, version)

    async def _get_tool_model(self, tenant_id: str, tool_id: str) -> ToolModel | None:
        tenant_uuid = as_uuid(tenant_id, field_name="tenant id")
        tool_uuid = as_uuid(tool_id, field_name="tool id")
        return await self._session.scalar(
            select(ToolModel).where(
                ToolModel.tenant_id == tenant_uuid,
                ToolModel.id == tool_uuid,
            )
        )

    async def _get_version_model(
        self,
        tenant_id: str,
        tool_version_id: str,
    ) -> ToolVersionModel | None:
        tenant_uuid = as_uuid(tenant_id, field_name="tenant id")
        version_uuid = as_uuid(tool_version_id, field_name="tool version id")
        return await self._session.scalar(
            select(ToolVersionModel).where(
                ToolVersionModel.tenant_id == tenant_uuid,
                ToolVersionModel.id == version_uuid,
            )
        )

    @staticmethod
    def _published_statement(
        tenant_id: str,
    ) -> Select[tuple[ToolModel, ToolVersionModel]]:
        tenant_uuid = as_uuid(tenant_id, field_name="tenant id")
        return (
            select(ToolModel, ToolVersionModel)
            .join(ToolVersionModel, ToolVersionModel.tool_id == ToolModel.id)
            .join(ToolBindingModel, ToolBindingModel.tool_version_id == ToolVersionModel.id)
            .where(
                ToolModel.tenant_id == tenant_uuid,
                ToolVersionModel.tenant_id == tenant_uuid,
                ToolBindingModel.tenant_id == tenant_uuid,
                ToolModel.status == ToolStatus.ACTIVE.value,
                ToolVersionModel.status == ToolVersionStatus.PUBLISHED.value,
                ToolBindingModel.status == ToolBindingStatus.PUBLISHED.value,
            )
        )


def _require_matching_tenant(requested_tenant_id: str, entity_tenant_id: str) -> None:
    if requested_tenant_id != entity_tenant_id:
        raise ValueError("entity tenant does not match repository tenant scope")
