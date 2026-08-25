"""UpstreamRepository 的 SQLAlchemy Async Adapter。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.modules.registry.adapters.sqlalchemy_mapping import upstream_from_model
from nexusmcp.modules.registry.adapters.sqlalchemy_models import UpstreamServiceModel
from nexusmcp.modules.registry.domain import UpstreamService


class SqlAlchemyUpstreamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(
        self,
        tenant_id: str,
        upstream_service_id: str,
    ) -> UpstreamService | None:
        model = await self._get_model(tenant_id, upstream_service_id, for_update=False)
        return upstream_from_model(model) if model is not None else None

    async def get_for_update(
        self,
        tenant_id: str,
        upstream_service_id: str,
    ) -> UpstreamService | None:
        model = await self._get_model(tenant_id, upstream_service_id, for_update=True)
        return upstream_from_model(model) if model is not None else None

    async def _get_model(
        self,
        tenant_id: str,
        upstream_service_id: str,
        *,
        for_update: bool,
    ) -> UpstreamServiceModel | None:
        statement = select(UpstreamServiceModel).where(
            UpstreamServiceModel.tenant_id == as_uuid(tenant_id, field_name="tenant id"),
            UpstreamServiceModel.id
            == as_uuid(upstream_service_id, field_name="upstream service id"),
        )
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)
