"""OpenAPI Import Domain 与 SQLAlchemy Model 显式 Mapping。"""

from copy import deepcopy

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.modules.openapi_import.adapters.sqlalchemy_models import (
    ImportedOperationModel,
    OpenApiImportJobModel,
)
from nexusmcp.modules.openapi_import.domain import (
    ImportedOperation,
    ImportJobStatus,
    OpenApiImportJob,
    OpenApiSourceType,
    OperationConflictStatus,
    OperationReviewStatus,
)


def import_job_to_model(job: OpenApiImportJob) -> OpenApiImportJobModel:
    return OpenApiImportJobModel(
        id=as_uuid(job.id, field_name="import job id"),
        tenant_id=as_uuid(job.tenant_id, field_name="tenant id"),
        upstream_service_id=as_uuid(job.upstream_service_id, field_name="upstream service id"),
        source_type=job.source_type.value,
        source_ref=job.source_ref,
        source_digest=job.source_digest,
        openapi_version=job.openapi_version,
        operation_allowlist_json=list(job.operation_allowlist),
        allowlist_snapshot_json=deepcopy(dict(job.allowlist_snapshot)),
        status=job.status.value,
        error_summary=job.error_summary,
        created_by=job.created_by,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


def update_import_job_model(model: OpenApiImportJobModel, job: OpenApiImportJob) -> None:
    model.source_ref = job.source_ref
    model.source_digest = job.source_digest
    model.openapi_version = job.openapi_version
    model.operation_allowlist_json = list(job.operation_allowlist)
    model.allowlist_snapshot_json = deepcopy(dict(job.allowlist_snapshot))
    model.status = job.status.value
    model.error_summary = job.error_summary
    model.started_at = job.started_at
    model.completed_at = job.completed_at


def import_job_from_model(model: OpenApiImportJobModel) -> OpenApiImportJob:
    return OpenApiImportJob(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        upstream_service_id=str(model.upstream_service_id),
        source_type=OpenApiSourceType(model.source_type),
        source_ref=model.source_ref,
        source_digest=model.source_digest,
        openapi_version=model.openapi_version,
        operation_allowlist=tuple(model.operation_allowlist_json),
        allowlist_snapshot=deepcopy(model.allowlist_snapshot_json),
        status=ImportJobStatus(model.status),
        error_summary=model.error_summary,
        created_by=model.created_by,
        created_at=model.created_at,
        started_at=model.started_at,
        completed_at=model.completed_at,
    )


def imported_operation_to_model(operation: ImportedOperation) -> ImportedOperationModel:
    return ImportedOperationModel(
        id=as_uuid(operation.id, field_name="imported operation id"),
        tenant_id=as_uuid(operation.tenant_id, field_name="tenant id"),
        import_job_id=as_uuid(operation.import_job_id, field_name="import job id"),
        upstream_service_id=as_uuid(
            operation.upstream_service_id,
            field_name="upstream service id",
        ),
        operation_key=operation.operation_key,
        operation_id=operation.operation_id,
        method=operation.method,
        path=operation.path,
        normalized_operation_json=deepcopy(dict(operation.normalized_operation)),
        generated_tool_name=operation.generated_tool_name,
        conflict_status=operation.conflict_status.value,
        review_status=operation.review_status.value,
        review_notes=operation.review_notes,
        draft_tool_version_id=(
            as_uuid(operation.draft_tool_version_id, field_name="draft tool version id")
            if operation.draft_tool_version_id is not None
            else None
        ),
        draft_tool_binding_id=(
            as_uuid(operation.draft_tool_binding_id, field_name="draft tool binding id")
            if operation.draft_tool_binding_id is not None
            else None
        ),
    )


def update_imported_operation_model(
    model: ImportedOperationModel,
    operation: ImportedOperation,
) -> None:
    model.operation_id = operation.operation_id
    model.normalized_operation_json = deepcopy(dict(operation.normalized_operation))
    model.generated_tool_name = operation.generated_tool_name
    model.conflict_status = operation.conflict_status.value
    model.review_status = operation.review_status.value
    model.review_notes = operation.review_notes
    model.draft_tool_version_id = (
        as_uuid(operation.draft_tool_version_id, field_name="draft tool version id")
        if operation.draft_tool_version_id is not None
        else None
    )
    model.draft_tool_binding_id = (
        as_uuid(operation.draft_tool_binding_id, field_name="draft tool binding id")
        if operation.draft_tool_binding_id is not None
        else None
    )


def imported_operation_from_model(model: ImportedOperationModel) -> ImportedOperation:
    return ImportedOperation(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        import_job_id=str(model.import_job_id),
        upstream_service_id=str(model.upstream_service_id),
        operation_key=model.operation_key,
        operation_id=model.operation_id,
        method=model.method,
        path=model.path,
        normalized_operation=deepcopy(model.normalized_operation_json),
        generated_tool_name=model.generated_tool_name,
        conflict_status=OperationConflictStatus(model.conflict_status),
        review_status=OperationReviewStatus(model.review_status),
        review_notes=model.review_notes,
        draft_tool_version_id=(
            str(model.draft_tool_version_id) if model.draft_tool_version_id is not None else None
        ),
        draft_tool_binding_id=(
            str(model.draft_tool_binding_id) if model.draft_tool_binding_id is not None else None
        ),
    )
