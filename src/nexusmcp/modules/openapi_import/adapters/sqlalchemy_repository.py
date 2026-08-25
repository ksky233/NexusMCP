"""OpenApiImportRepository 的 SQLAlchemy Async Adapter。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.modules.openapi_import.adapters.sqlalchemy_mapping import (
    import_job_from_model,
    import_job_to_model,
    imported_operation_from_model,
    imported_operation_to_model,
    update_import_job_model,
    update_imported_operation_model,
)
from nexusmcp.modules.openapi_import.adapters.sqlalchemy_models import (
    ImportedOperationModel,
    OpenApiImportJobModel,
)
from nexusmcp.modules.openapi_import.domain import ImportedOperation, OpenApiImportJob


class SqlAlchemyOpenApiImportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_job(self, tenant_id: str, job: OpenApiImportJob) -> None:
        _require_matching_tenant(tenant_id, job.tenant_id)
        self._session.add(import_job_to_model(job))
        await self._session.flush()

    async def save_job(self, tenant_id: str, job: OpenApiImportJob) -> None:
        _require_matching_tenant(tenant_id, job.tenant_id)
        model = await self._get_job_model(tenant_id, job.id, for_update=False)
        if model is None:
            raise ValueError("OpenAPI import job does not exist in tenant")
        update_import_job_model(model, job)
        await self._session.flush()

    async def get_job_by_id(
        self,
        tenant_id: str,
        import_job_id: str,
    ) -> OpenApiImportJob | None:
        model = await self._get_job_model(tenant_id, import_job_id, for_update=False)
        return import_job_from_model(model) if model is not None else None

    async def get_job_for_update(
        self,
        tenant_id: str,
        import_job_id: str,
    ) -> OpenApiImportJob | None:
        model = await self._get_job_model(tenant_id, import_job_id, for_update=True)
        return import_job_from_model(model) if model is not None else None

    async def add_operations(
        self,
        tenant_id: str,
        operations: tuple[ImportedOperation, ...],
    ) -> None:
        for operation in operations:
            _require_matching_tenant(tenant_id, operation.tenant_id)
            self._session.add(imported_operation_to_model(operation))
        await self._session.flush()

    async def list_operations(
        self,
        tenant_id: str,
        import_job_id: str,
    ) -> tuple[ImportedOperation, ...]:
        tenant_uuid = as_uuid(tenant_id, field_name="tenant id")
        job_uuid = as_uuid(import_job_id, field_name="import job id")
        models = (
            await self._session.scalars(
                select(ImportedOperationModel)
                .where(
                    ImportedOperationModel.tenant_id == tenant_uuid,
                    ImportedOperationModel.import_job_id == job_uuid,
                )
                .order_by(ImportedOperationModel.operation_key)
            )
        ).all()
        return tuple(imported_operation_from_model(model) for model in models)

    async def get_operation_for_update(
        self,
        tenant_id: str,
        operation_id: str,
    ) -> ImportedOperation | None:
        tenant_uuid = as_uuid(tenant_id, field_name="tenant id")
        operation_uuid = as_uuid(operation_id, field_name="imported operation id")
        model = await self._session.scalar(
            select(ImportedOperationModel)
            .where(
                ImportedOperationModel.tenant_id == tenant_uuid,
                ImportedOperationModel.id == operation_uuid,
            )
            .with_for_update()
        )
        return imported_operation_from_model(model) if model is not None else None

    async def save_operation(
        self,
        tenant_id: str,
        operation: ImportedOperation,
    ) -> None:
        _require_matching_tenant(tenant_id, operation.tenant_id)
        model = await self._session.scalar(
            select(ImportedOperationModel).where(
                ImportedOperationModel.tenant_id == as_uuid(tenant_id, field_name="tenant id"),
                ImportedOperationModel.id
                == as_uuid(operation.id, field_name="imported operation id"),
            )
        )
        if model is None:
            raise ValueError("imported operation does not exist in tenant")
        update_imported_operation_model(model, operation)
        await self._session.flush()

    async def _get_job_model(
        self,
        tenant_id: str,
        import_job_id: str,
        *,
        for_update: bool,
    ) -> OpenApiImportJobModel | None:
        statement = select(OpenApiImportJobModel).where(
            OpenApiImportJobModel.tenant_id == as_uuid(tenant_id, field_name="tenant id"),
            OpenApiImportJobModel.id == as_uuid(import_job_id, field_name="import job id"),
        )
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)


def _require_matching_tenant(requested_tenant_id: str, entity_tenant_id: str) -> None:
    if requested_tenant_id != entity_tenant_id:
        raise ValueError("entity tenant does not match repository tenant scope")
