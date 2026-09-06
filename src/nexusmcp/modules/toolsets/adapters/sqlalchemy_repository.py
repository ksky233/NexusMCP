"""ToolsetRepository 的 SQLAlchemy Async Adapter。"""

from sqlalchemy import Select, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.modules.toolsets.adapters.sqlalchemy_mapping import (
    grant_to_model,
    member_to_model,
    toolset_from_models,
    toolset_to_model,
    update_toolset_model,
)
from nexusmcp.modules.toolsets.adapters.sqlalchemy_models import (
    ToolsetAccessGrantModel,
    ToolsetMemberModel,
    ToolsetModel,
)
from nexusmcp.modules.toolsets.domain import Toolset, ToolsetKind, ToolsetStatus


class SqlAlchemyToolsetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, tenant_id: str, toolset: Toolset) -> None:
        _require_matching_tenant(tenant_id, toolset.tenant_id)
        self._session.add(toolset_to_model(toolset))
        await self._flush_with_uniqueness_mapping()
        self._session.add_all([member_to_model(member) for member in toolset.members])
        self._session.add_all([grant_to_model(grant) for grant in toolset.grants])
        await self._flush_with_uniqueness_mapping()

    async def save(self, tenant_id: str, toolset: Toolset) -> None:
        _require_matching_tenant(tenant_id, toolset.tenant_id)
        model = await self._get_model(tenant_id, toolset.id, for_update=False)
        if model is None:
            raise ValueError("toolset does not exist in tenant")
        update_toolset_model(model, toolset)
        toolset_uuid = as_uuid(toolset.id, field_name="toolset id")
        await self._session.execute(
            delete(ToolsetMemberModel).where(ToolsetMemberModel.toolset_id == toolset_uuid)
        )
        await self._session.execute(
            delete(ToolsetAccessGrantModel).where(
                ToolsetAccessGrantModel.toolset_id == toolset_uuid
            )
        )
        self._session.add_all([member_to_model(member) for member in toolset.members])
        self._session.add_all([grant_to_model(grant) for grant in toolset.grants])
        await self._flush_with_uniqueness_mapping()

    async def get_by_id(self, tenant_id: str, toolset_id: str) -> Toolset | None:
        model = await self._get_model(tenant_id, toolset_id, for_update=False)
        return await self._aggregate(model) if model is not None else None

    async def get_for_update(self, tenant_id: str, toolset_id: str) -> Toolset | None:
        model = await self._get_model(tenant_id, toolset_id, for_update=True)
        return await self._aggregate(model) if model is not None else None

    async def get_by_slug(self, tenant_id: str, slug: str) -> Toolset | None:
        model = await self._session.scalar(
            select(ToolsetModel).where(
                ToolsetModel.tenant_id == as_uuid(tenant_id, field_name="tenant id"),
                ToolsetModel.slug == slug,
            )
        )
        return await self._aggregate(model) if model is not None else None

    async def get_all_published(self, tenant_id: str) -> Toolset | None:
        model = await self._session.scalar(
            select(ToolsetModel).where(
                ToolsetModel.tenant_id == as_uuid(tenant_id, field_name="tenant id"),
                ToolsetModel.kind == ToolsetKind.ALL_PUBLISHED.value,
            )
        )
        return await self._aggregate(model) if model is not None else None

    async def list_by_tenant(self, tenant_id: str) -> tuple[Toolset, ...]:
        models = (
            await self._session.scalars(
                select(ToolsetModel)
                .where(ToolsetModel.tenant_id == as_uuid(tenant_id, field_name="tenant id"))
                .order_by(ToolsetModel.slug)
            )
        ).all()
        return tuple([await self._aggregate(model) for model in models])

    async def list_granted_active(
        self,
        tenant_id: str,
        principal_id: str,
    ) -> tuple[Toolset, ...]:
        models = (
            await self._session.scalars(
                select(ToolsetModel)
                .join(
                    ToolsetAccessGrantModel,
                    ToolsetAccessGrantModel.toolset_id == ToolsetModel.id,
                )
                .where(
                    ToolsetModel.tenant_id == as_uuid(tenant_id, field_name="tenant id"),
                    ToolsetModel.status == ToolsetStatus.ACTIVE.value,
                    ToolsetAccessGrantModel.principal_id == principal_id,
                )
                .order_by(ToolsetModel.slug)
            )
        ).all()
        return tuple([await self._aggregate(model) for model in models])

    async def _aggregate(self, model: ToolsetModel) -> Toolset:
        members = tuple(
            (
                await self._session.scalars(
                    select(ToolsetMemberModel)
                    .where(ToolsetMemberModel.toolset_id == model.id)
                    .order_by(ToolsetMemberModel.tool_id)
                )
            ).all()
        )
        grants = tuple(
            (
                await self._session.scalars(
                    select(ToolsetAccessGrantModel)
                    .where(ToolsetAccessGrantModel.toolset_id == model.id)
                    .order_by(ToolsetAccessGrantModel.principal_id)
                )
            ).all()
        )
        return toolset_from_models(model, members, grants)

    async def _get_model(
        self,
        tenant_id: str,
        toolset_id: str,
        *,
        for_update: bool,
    ) -> ToolsetModel | None:
        statement = self._statement(tenant_id, toolset_id)
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    @staticmethod
    def _statement(tenant_id: str, toolset_id: str) -> Select[tuple[ToolsetModel]]:
        return select(ToolsetModel).where(
            ToolsetModel.tenant_id == as_uuid(tenant_id, field_name="tenant id"),
            ToolsetModel.id == as_uuid(toolset_id, field_name="toolset id"),
        )

    async def _flush_with_uniqueness_mapping(self) -> None:
        try:
            await self._session.flush()
        except IntegrityError as error:
            if getattr(error.orig, "sqlstate", None) == "23505":
                raise ValueError("toolset uniqueness constraint was violated") from error
            raise


def _require_matching_tenant(requested_tenant_id: str, entity_tenant_id: str) -> None:
    if requested_tenant_id != entity_tenant_id:
        raise ValueError("entity tenant does not match repository tenant scope")
