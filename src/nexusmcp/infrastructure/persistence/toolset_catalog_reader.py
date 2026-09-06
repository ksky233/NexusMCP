"""使用 Toolset Transaction Session 读取 Catalog Availability。"""

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.modules.catalog.adapters.sqlalchemy_models import ToolModel, ToolVersionModel
from nexusmcp.modules.catalog.domain import ToolStatus, ToolVersionStatus
from nexusmcp.modules.toolsets.domain import ToolsetMemberAvailability
from nexusmcp.modules.toolsets.ports import ToolsetCatalogSnapshot


class SqlAlchemyToolsetCatalogReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_member_snapshots(
        self,
        tenant_id: str,
        tool_ids: tuple[str, ...],
    ) -> tuple[ToolsetCatalogSnapshot, ...]:
        if not tool_ids:
            return ()
        tenant_uuid = as_uuid(tenant_id, field_name="tenant id")
        requested = tuple(as_uuid(tool_id, field_name="tool id") for tool_id in tool_ids)
        rows = (
            await self._session.execute(
                select(
                    ToolModel.id,
                    ToolModel.tenant_id,
                    ToolModel.status,
                    ToolVersionModel.id.label("published_tool_version_id"),
                )
                .outerjoin(
                    ToolVersionModel,
                    and_(
                        ToolVersionModel.tool_id == ToolModel.id,
                        ToolVersionModel.tenant_id == ToolModel.tenant_id,
                        ToolVersionModel.status == ToolVersionStatus.PUBLISHED.value,
                    ),
                )
                .where(
                    ToolModel.tenant_id == tenant_uuid,
                    ToolModel.id.in_(requested),
                )
            )
        ).all()
        by_tool_id = {
            str(row.id): ToolsetCatalogSnapshot(
                tool_id=str(row.id),
                tenant_id=str(row.tenant_id),
                availability=(
                    ToolsetMemberAvailability.TOOL_DISABLED
                    if row.status == ToolStatus.DISABLED.value
                    else (
                        ToolsetMemberAvailability.NO_PUBLISHED_VERSION
                        if row.published_tool_version_id is None
                        else ToolsetMemberAvailability.AVAILABLE
                    )
                ),
                published_tool_version_id=(
                    str(row.published_tool_version_id)
                    if row.status == ToolStatus.ACTIVE.value
                    and row.published_tool_version_id is not None
                    else None
                ),
            )
            for row in rows
        }
        return tuple(
            snapshot for tool_id in tool_ids if (snapshot := by_tool_id.get(tool_id)) is not None
        )
