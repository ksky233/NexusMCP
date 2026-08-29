"""UpstreamRepository 的 SQLAlchemy Async Adapter。"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.modules.registry.adapters.sqlalchemy_mapping import (
    update_upstream_model,
    upstream_from_model,
    upstream_to_model,
)
from nexusmcp.modules.registry.adapters.sqlalchemy_models import UpstreamServiceModel
from nexusmcp.modules.registry.domain import UpstreamService
from nexusmcp.shared.errors import UpstreamConflictError


class SqlAlchemyUpstreamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, tenant_id: str, upstream: UpstreamService) -> None:
        _require_matching_tenant(tenant_id, upstream.tenant_id)
        self._session.add(upstream_to_model(upstream))
        try:
            await self._session.flush()
        except IntegrityError as error:
            if getattr(error.orig, "sqlstate", None) == "23505":
                raise UpstreamConflictError(
                    "upstream registration violated a database uniqueness constraint"
                ) from error
            raise

    async def save(self, tenant_id: str, upstream: UpstreamService) -> None:
        _require_matching_tenant(tenant_id, upstream.tenant_id)
        model = await self._get_model(tenant_id, upstream.id, for_update=False)
        if model is None:
            raise ValueError("upstream service does not exist in tenant")
        update_upstream_model(model, upstream)
        await self._session.flush()

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

    async def get_by_name(
        self,
        tenant_id: str,
        namespace: str,
        name: str,
    ) -> UpstreamService | None:
        model = await self._session.scalar(
            select(UpstreamServiceModel).where(
                UpstreamServiceModel.tenant_id == as_uuid(tenant_id, field_name="tenant id"),
                UpstreamServiceModel.namespace == namespace,
                UpstreamServiceModel.name == name,
            )
        )
        return upstream_from_model(model) if model is not None else None

    async def list_by_tenant(self, tenant_id: str) -> tuple[UpstreamService, ...]:
        models = (
            await self._session.scalars(
                select(UpstreamServiceModel)
                .where(UpstreamServiceModel.tenant_id == as_uuid(tenant_id, field_name="tenant id"))
                .order_by(UpstreamServiceModel.namespace, UpstreamServiceModel.name)
            )
        ).all()
        return tuple(upstream_from_model(model) for model in models)

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


def _require_matching_tenant(requested_tenant_id: str, entity_tenant_id: str) -> None:
    if requested_tenant_id != entity_tenant_id:
        raise ValueError("entity tenant does not match repository tenant scope")
