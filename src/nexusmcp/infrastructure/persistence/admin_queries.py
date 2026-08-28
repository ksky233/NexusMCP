"""跨业务表的 Admin Read Model SQLAlchemy Adapter。"""

import uuid
from typing import Any

from sqlalchemy import String, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntimePort
from nexusmcp.modules.approval.adapters.sqlalchemy_models import ApprovalRequestModel
from nexusmcp.modules.audit.adapters.sqlalchemy_models import AuditEventModel
from nexusmcp.modules.catalog.adapters.sqlalchemy_models import ToolModel, ToolVersionModel
from nexusmcp.modules.connectors.adapters.sqlalchemy_models import ToolBindingModel
from nexusmcp.modules.control_plane.read_models import (
    ApprovalSummary,
    AuditEventSummary,
    DashboardSummary,
    ExecutionAttemptSummary,
    ExecutionSummary,
    ImportJobSummary,
    Page,
    ReviewOperationSummary,
    SearchProjectionSummary,
    ToolBindingDetail,
    ToolDetail,
    ToolSummary,
    ToolVersionDetail,
    UpstreamDetail,
)
from nexusmcp.modules.execution.adapters.sqlalchemy_models import (
    ExecutionAttemptModel,
    ToolExecutionModel,
)
from nexusmcp.modules.openapi_import.adapters.sqlalchemy_models import (
    ImportedOperationModel,
    OpenApiImportJobModel,
)
from nexusmcp.modules.registry.adapters.sqlalchemy_models import UpstreamServiceModel
from nexusmcp.modules.tool_search.adapters.sqlalchemy_models import ToolSearchEmbeddingModel


class SqlAlchemyControlPlaneQueries:
    """Query Side 可以跨 Context Join，但只返回稳定 Read Model，不泄漏 ORM。"""

    def __init__(
        self,
        database_runtime: DatabaseRuntimePort,
        *,
        embedding_model: str,
        embedding_dimensions: int,
    ) -> None:
        self._database_runtime = database_runtime
        self._embedding_model = embedding_model
        self._embedding_dimensions = embedding_dimensions

    async def dashboard(self, tenant_id: str) -> DashboardSummary:
        tenant_uuid = _required_uuid(tenant_id)
        async with self._session() as session:
            active_upstreams = await _scalar_count(
                session,
                select(func.count())
                .select_from(UpstreamServiceModel)
                .where(
                    UpstreamServiceModel.tenant_id == tenant_uuid,
                    UpstreamServiceModel.status == "active",
                    UpstreamServiceModel.service_type == "http",
                    UpstreamServiceModel.transport_type == "http",
                ),
            )
            published_tools = await _scalar_count(
                session,
                select(func.count())
                .select_from(ToolVersionModel)
                .where(
                    ToolVersionModel.tenant_id == tenant_uuid,
                    ToolVersionModel.status == "published",
                ),
            )
            pending_reviews = await _scalar_count(
                session,
                select(func.count())
                .select_from(ImportedOperationModel)
                .where(
                    ImportedOperationModel.tenant_id == tenant_uuid,
                    ImportedOperationModel.review_status.in_(("pending", "needs_change")),
                ),
            )
            pending_approvals = await _scalar_count(
                session,
                select(func.count())
                .select_from(ApprovalRequestModel)
                .where(
                    ApprovalRequestModel.tenant_id == tenant_uuid,
                    ApprovalRequestModel.status == "pending",
                ),
            )
            failed_executions = await _scalar_count(
                session,
                select(func.count())
                .select_from(ToolExecutionModel)
                .where(
                    ToolExecutionModel.tenant_id == tenant_uuid,
                    ToolExecutionModel.status == "failed",
                ),
            )
            unknown_executions = await _scalar_count(
                session,
                select(func.count())
                .select_from(ToolExecutionModel)
                .where(
                    ToolExecutionModel.tenant_id == tenant_uuid,
                    ToolExecutionModel.status == "unknown",
                ),
            )
            projection = await self._search_projection_status(session, tenant_uuid)
        return DashboardSummary(
            active_upstreams=active_upstreams,
            published_tools=published_tools,
            pending_reviews=pending_reviews,
            pending_approvals=pending_approvals,
            failed_executions=failed_executions,
            unknown_executions=unknown_executions,
            search_projection=projection,
        )

    async def get_upstream(self, tenant_id: str, upstream_id: str) -> UpstreamDetail | None:
        tenant_uuid = _required_uuid(tenant_id)
        resource_uuid = _optional_uuid(upstream_id)
        if resource_uuid is None:
            return None
        async with self._session() as session:
            model = await session.scalar(
                select(UpstreamServiceModel).where(
                    UpstreamServiceModel.tenant_id == tenant_uuid,
                    UpstreamServiceModel.id == resource_uuid,
                )
            )
        return _upstream_detail(model) if model is not None else None

    async def list_upstreams(
        self,
        tenant_id: str,
        *,
        offset: int,
        limit: int,
        namespace: str | None,
        status: str | None,
    ) -> Page[UpstreamDetail]:
        tenant_uuid = _required_uuid(tenant_id)
        statement = select(UpstreamServiceModel).where(
            UpstreamServiceModel.tenant_id == tenant_uuid,
            UpstreamServiceModel.service_type == "http",
            UpstreamServiceModel.transport_type == "http",
        )
        if namespace is not None:
            statement = statement.where(UpstreamServiceModel.namespace == namespace)
        if status is not None:
            statement = statement.where(UpstreamServiceModel.status == status)
        statement = statement.order_by(
            UpstreamServiceModel.namespace.asc(),
            UpstreamServiceModel.name.asc(),
        )
        async with self._session() as session:
            rows, total = await _paged_rows(session, statement, offset=offset, limit=limit)
        return Page(
            items=tuple(_upstream_detail(row[0]) for row in rows),
            offset=offset,
            limit=limit,
            total=total,
        )

    async def list_imports(
        self,
        tenant_id: str,
        *,
        offset: int,
        limit: int,
        status: str | None,
        upstream_id: str | None,
    ) -> Page[ImportJobSummary]:
        tenant_uuid = _required_uuid(tenant_id)
        statement = (
            select(OpenApiImportJobModel, UpstreamServiceModel.name)
            .join(
                UpstreamServiceModel,
                UpstreamServiceModel.id == OpenApiImportJobModel.upstream_service_id,
            )
            .where(OpenApiImportJobModel.tenant_id == tenant_uuid)
            .order_by(OpenApiImportJobModel.created_at.desc(), OpenApiImportJobModel.id.desc())
        )
        if status is not None:
            statement = statement.where(OpenApiImportJobModel.status == status)
        upstream_uuid = _optional_uuid(upstream_id) if upstream_id is not None else None
        if upstream_id is not None:
            if upstream_uuid is None:
                return Page(items=(), offset=offset, limit=limit, total=0)
            statement = statement.where(OpenApiImportJobModel.upstream_service_id == upstream_uuid)
        async with self._session() as session:
            rows, total = await _paged_rows(session, statement, offset=offset, limit=limit)
        return Page(
            items=tuple(_import_summary(row[0], str(row[1])) for row in rows),
            offset=offset,
            limit=limit,
            total=total,
        )

    async def list_review_operations(
        self,
        tenant_id: str,
        *,
        offset: int,
        limit: int,
        review_status: str | None,
        conflict_status: str | None,
        import_job_id: str | None,
    ) -> Page[ReviewOperationSummary]:
        tenant_uuid = _required_uuid(tenant_id)
        statement = select(ImportedOperationModel).where(
            ImportedOperationModel.tenant_id == tenant_uuid
        )
        if review_status is not None:
            statement = statement.where(ImportedOperationModel.review_status == review_status)
        if conflict_status is not None:
            statement = statement.where(ImportedOperationModel.conflict_status == conflict_status)
        job_uuid = _optional_uuid(import_job_id) if import_job_id is not None else None
        if import_job_id is not None:
            if job_uuid is None:
                return Page(items=(), offset=offset, limit=limit, total=0)
            statement = statement.where(ImportedOperationModel.import_job_id == job_uuid)
        statement = statement.order_by(
            ImportedOperationModel.created_at.desc(),
            ImportedOperationModel.id.desc(),
        )
        async with self._session() as session:
            rows, total = await _paged_rows(session, statement, offset=offset, limit=limit)
        return Page(
            items=tuple(_review_summary(row[0]) for row in rows),
            offset=offset,
            limit=limit,
            total=total,
        )

    async def list_tools(
        self,
        tenant_id: str,
        *,
        offset: int,
        limit: int,
        namespace: str | None,
        status: str | None,
        version_status: str | None,
        visibility: str | None,
        side_effect: str | None,
    ) -> Page[ToolSummary]:
        tenant_uuid = _required_uuid(tenant_id)
        latest_versions = (
            select(
                ToolVersionModel.tool_id.label("tool_id"),
                func.max(ToolVersionModel.version).label("version"),
            )
            .where(ToolVersionModel.tenant_id == tenant_uuid)
            .group_by(ToolVersionModel.tool_id)
            .subquery()
        )
        statement = (
            select(ToolModel, ToolVersionModel)
            .join(latest_versions, latest_versions.c.tool_id == ToolModel.id)
            .join(
                ToolVersionModel,
                and_(
                    ToolVersionModel.tool_id == latest_versions.c.tool_id,
                    ToolVersionModel.version == latest_versions.c.version,
                ),
            )
            .where(ToolModel.tenant_id == tenant_uuid)
        )
        if namespace is not None:
            statement = statement.where(ToolModel.namespace == namespace)
        if status is not None:
            statement = statement.where(ToolModel.status == status)
        if version_status is not None:
            statement = statement.where(ToolVersionModel.status == version_status)
        if visibility is not None:
            statement = statement.where(ToolVersionModel.visibility == visibility)
        if side_effect is not None:
            statement = statement.where(ToolVersionModel.side_effect == side_effect)
        statement = statement.order_by(ToolModel.canonical_name.asc())
        async with self._session() as session:
            rows, total = await _paged_rows(session, statement, offset=offset, limit=limit)
        return Page(
            items=tuple(_tool_summary(row[0], row[1]) for row in rows),
            offset=offset,
            limit=limit,
            total=total,
        )

    async def get_tool(self, tenant_id: str, tool_id: str) -> ToolDetail | None:
        tenant_uuid = _required_uuid(tenant_id)
        tool_uuid = _optional_uuid(tool_id)
        if tool_uuid is None:
            return None
        async with self._session() as session:
            model = await session.scalar(
                select(ToolModel).where(
                    ToolModel.tenant_id == tenant_uuid,
                    ToolModel.id == tool_uuid,
                )
            )
        return _tool_detail(model) if model is not None else None

    async def list_tool_versions(
        self,
        tenant_id: str,
        tool_id: str,
        *,
        offset: int,
        limit: int,
    ) -> Page[ToolVersionDetail]:
        tenant_uuid = _required_uuid(tenant_id)
        tool_uuid = _optional_uuid(tool_id)
        if tool_uuid is None:
            return Page(items=(), offset=offset, limit=limit, total=0)
        statement = (
            select(ToolVersionModel)
            .where(
                ToolVersionModel.tenant_id == tenant_uuid,
                ToolVersionModel.tool_id == tool_uuid,
            )
            .order_by(ToolVersionModel.version.desc())
        )
        async with self._session() as session:
            rows, total = await _paged_rows(session, statement, offset=offset, limit=limit)
        return Page(
            items=tuple(_version_detail(row[0]) for row in rows),
            offset=offset,
            limit=limit,
            total=total,
        )

    async def get_tool_binding(
        self,
        tenant_id: str,
        binding_id: str,
    ) -> ToolBindingDetail | None:
        tenant_uuid = _required_uuid(tenant_id)
        binding_uuid = _optional_uuid(binding_id)
        if binding_uuid is None:
            return None
        async with self._session() as session:
            model = await session.scalar(
                select(ToolBindingModel).where(
                    ToolBindingModel.tenant_id == tenant_uuid,
                    ToolBindingModel.id == binding_uuid,
                )
            )
        return _binding_detail(model) if model is not None else None

    async def list_approvals(
        self,
        tenant_id: str,
        *,
        offset: int,
        limit: int,
        status: str | None,
        principal_id: str | None,
        tool_id: str | None,
    ) -> Page[ApprovalSummary]:
        tenant_uuid = _required_uuid(tenant_id)
        statement = (
            select(ApprovalRequestModel, ToolModel.canonical_name)
            .join(ToolModel, ToolModel.id == ApprovalRequestModel.tool_id)
            .where(ApprovalRequestModel.tenant_id == tenant_uuid)
        )
        if status is not None:
            statement = statement.where(ApprovalRequestModel.status == status)
        if principal_id is not None:
            statement = statement.where(ApprovalRequestModel.principal_id == principal_id)
        tool_uuid = _optional_uuid(tool_id) if tool_id is not None else None
        if tool_id is not None:
            if tool_uuid is None:
                return Page(items=(), offset=offset, limit=limit, total=0)
            statement = statement.where(ApprovalRequestModel.tool_id == tool_uuid)
        statement = statement.order_by(
            ApprovalRequestModel.requested_at.desc(),
            ApprovalRequestModel.id.desc(),
        )
        async with self._session() as session:
            rows, total = await _paged_rows(session, statement, offset=offset, limit=limit)
        return Page(
            items=tuple(_approval_summary(row[0], str(row[1])) for row in rows),
            offset=offset,
            limit=limit,
            total=total,
        )

    async def list_executions(
        self,
        tenant_id: str,
        *,
        offset: int,
        limit: int,
        status: str | None,
        principal_id: str | None,
        tool_id: str | None,
        trace_id: str | None,
    ) -> Page[ExecutionSummary]:
        tenant_uuid = _required_uuid(tenant_id)
        statement = (
            select(ToolExecutionModel, ToolModel.canonical_name)
            .join(ToolModel, ToolModel.id == ToolExecutionModel.tool_id)
            .where(ToolExecutionModel.tenant_id == tenant_uuid)
        )
        if status is not None:
            statement = statement.where(ToolExecutionModel.status == status)
        if principal_id is not None:
            statement = statement.where(ToolExecutionModel.principal_id == principal_id)
        if trace_id is not None:
            statement = statement.where(ToolExecutionModel.trace_id == trace_id)
        tool_uuid = _optional_uuid(tool_id) if tool_id is not None else None
        if tool_id is not None:
            if tool_uuid is None:
                return Page(items=(), offset=offset, limit=limit, total=0)
            statement = statement.where(ToolExecutionModel.tool_id == tool_uuid)
        statement = statement.order_by(
            ToolExecutionModel.planned_at.desc(),
            ToolExecutionModel.id.desc(),
        )
        async with self._session() as session:
            rows, total = await _paged_rows(session, statement, offset=offset, limit=limit)
        return Page(
            items=tuple(_execution_summary(row[0], str(row[1])) for row in rows),
            offset=offset,
            limit=limit,
            total=total,
        )

    async def get_execution(
        self,
        tenant_id: str,
        execution_id: str,
    ) -> ExecutionSummary | None:
        tenant_uuid = _required_uuid(tenant_id)
        execution_uuid = _optional_uuid(execution_id)
        if execution_uuid is None:
            return None
        async with self._session() as session:
            row = (
                await session.execute(
                    select(ToolExecutionModel, ToolModel.canonical_name)
                    .join(ToolModel, ToolModel.id == ToolExecutionModel.tool_id)
                    .where(
                        ToolExecutionModel.tenant_id == tenant_uuid,
                        ToolExecutionModel.id == execution_uuid,
                    )
                )
            ).first()
        return _execution_summary(row[0], str(row[1])) if row is not None else None

    async def list_execution_attempts(
        self,
        tenant_id: str,
        execution_id: str,
        *,
        offset: int,
        limit: int,
    ) -> Page[ExecutionAttemptSummary]:
        tenant_uuid = _required_uuid(tenant_id)
        execution_uuid = _optional_uuid(execution_id)
        if execution_uuid is None:
            return Page(items=(), offset=offset, limit=limit, total=0)
        statement = (
            select(ExecutionAttemptModel)
            .where(
                ExecutionAttemptModel.tenant_id == tenant_uuid,
                ExecutionAttemptModel.execution_id == execution_uuid,
            )
            .order_by(ExecutionAttemptModel.attempt_number.asc())
        )
        async with self._session() as session:
            rows, total = await _paged_rows(session, statement, offset=offset, limit=limit)
        return Page(
            items=tuple(_attempt_summary(row[0]) for row in rows),
            offset=offset,
            limit=limit,
            total=total,
        )

    async def list_audit_events(
        self,
        tenant_id: str,
        *,
        offset: int,
        limit: int,
        trace_id: str | None,
        principal_id: str | None,
        tool_id: str | None,
        execution_id: str | None,
        outcome: str | None,
    ) -> Page[AuditEventSummary]:
        tenant_uuid = _required_uuid(tenant_id)
        statement = select(AuditEventModel).where(AuditEventModel.tenant_id == tenant_uuid)
        if trace_id is not None:
            statement = statement.where(AuditEventModel.trace_id == trace_id)
        if principal_id is not None:
            statement = statement.where(AuditEventModel.actor_id == principal_id)
        if outcome is not None:
            statement = statement.where(AuditEventModel.outcome == outcome)
        execution_uuid = _optional_uuid(execution_id) if execution_id is not None else None
        if execution_id is not None:
            if execution_uuid is None:
                return Page(items=(), offset=offset, limit=limit, total=0)
            statement = statement.where(AuditEventModel.execution_id == execution_uuid)
        tool_uuid = _optional_uuid(tool_id) if tool_id is not None else None
        if tool_id is not None:
            if tool_uuid is None:
                return Page(items=(), offset=offset, limit=limit, total=0)
            version_ids = select(cast(ToolVersionModel.id, String)).where(
                ToolVersionModel.tenant_id == tenant_uuid,
                ToolVersionModel.tool_id == tool_uuid,
            )
            statement = statement.where(AuditEventModel.resource_id.in_(version_ids))
        statement = statement.order_by(
            AuditEventModel.occurred_at.desc(),
            AuditEventModel.id.desc(),
        )
        async with self._session() as session:
            rows, total = await _paged_rows(session, statement, offset=offset, limit=limit)
        return Page(
            items=tuple(_audit_summary(row[0]) for row in rows),
            offset=offset,
            limit=limit,
            total=total,
        )

    async def search_projection_status(self, tenant_id: str) -> SearchProjectionSummary:
        tenant_uuid = _required_uuid(tenant_id)
        async with self._session() as session:
            return await self._search_projection_status(session, tenant_uuid)

    async def _search_projection_status(
        self,
        session: AsyncSession,
        tenant_uuid: uuid.UUID,
    ) -> SearchProjectionSummary:
        published_tools = await _scalar_count(
            session,
            select(func.count())
            .select_from(ToolVersionModel)
            .where(
                ToolVersionModel.tenant_id == tenant_uuid,
                ToolVersionModel.status == "published",
            ),
        )
        indexed_tools = await _scalar_count(
            session,
            select(func.count())
            .select_from(ToolSearchEmbeddingModel)
            .join(ToolVersionModel, ToolVersionModel.id == ToolSearchEmbeddingModel.tool_version_id)
            .where(
                ToolSearchEmbeddingModel.tenant_id == tenant_uuid,
                ToolSearchEmbeddingModel.embedding_model == self._embedding_model,
                ToolSearchEmbeddingModel.embedding_dimensions == self._embedding_dimensions,
                ToolVersionModel.status == "published",
            ),
        )
        latest_indexed_at = await session.scalar(
            select(func.max(ToolSearchEmbeddingModel.indexed_at)).where(
                ToolSearchEmbeddingModel.tenant_id == tenant_uuid,
                ToolSearchEmbeddingModel.embedding_model == self._embedding_model,
                ToolSearchEmbeddingModel.embedding_dimensions == self._embedding_dimensions,
            )
        )
        return SearchProjectionSummary(
            published_tools=published_tools,
            indexed_tools=indexed_tools,
            pending_tools=max(published_tools - indexed_tools, 0),
            coverage_percent=(
                round(indexed_tools / published_tools * 100, 2) if published_tools else 100.0
            ),
            embedding_model=self._embedding_model,
            embedding_dimensions=self._embedding_dimensions,
            latest_indexed_at=latest_indexed_at,
        )

    def _session(self) -> AsyncSession:
        return self._database_runtime.require_session_factory()()


async def _paged_rows(
    session: AsyncSession,
    statement: Any,
    *,
    offset: int,
    limit: int,
) -> tuple[tuple[Any, ...], int]:
    count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
    total = await _scalar_count(session, count_statement)
    rows = (await session.execute(statement.offset(offset).limit(limit))).all()
    return tuple(rows), total


async def _scalar_count(session: AsyncSession, statement: Any) -> int:
    return int((await session.scalar(statement)) or 0)


def _required_uuid(value: str) -> uuid.UUID:
    return uuid.UUID(value)


def _optional_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _upstream_detail(model: UpstreamServiceModel) -> UpstreamDetail:
    return UpstreamDetail(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        namespace=model.namespace,
        name=model.name,
        description=model.description,
        owner=model.owner,
        service_type=model.service_type,
        transport_type=model.transport_type,
        endpoint=model.endpoint,
        protocol_min=model.protocol_min,
        protocol_max=model.protocol_max,
        auth_scheme=model.auth_scheme,
        config=dict(model.config_json),
        status=model.status,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _import_summary(model: OpenApiImportJobModel, upstream_name: str) -> ImportJobSummary:
    return ImportJobSummary(
        id=str(model.id),
        upstream_service_id=str(model.upstream_service_id),
        upstream_name=upstream_name,
        source_type=model.source_type,
        source_ref=model.source_ref,
        source_digest=model.source_digest,
        openapi_version=model.openapi_version,
        status=model.status,
        error_summary=model.error_summary,
        created_by=model.created_by,
        created_at=model.created_at,
        started_at=model.started_at,
        completed_at=model.completed_at,
    )


def _review_summary(model: ImportedOperationModel) -> ReviewOperationSummary:
    return ReviewOperationSummary(
        id=str(model.id),
        import_job_id=str(model.import_job_id),
        upstream_service_id=str(model.upstream_service_id),
        operation_id=model.operation_id,
        operation_key=model.operation_key,
        method=model.method,
        path=model.path,
        generated_tool_name=model.generated_tool_name,
        conflict_status=model.conflict_status,
        review_status=model.review_status,
        review_notes=model.review_notes,
        draft_tool_version_id=(
            str(model.draft_tool_version_id) if model.draft_tool_version_id else None
        ),
        draft_tool_binding_id=(
            str(model.draft_tool_binding_id) if model.draft_tool_binding_id else None
        ),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _tool_summary(tool: ToolModel, version: ToolVersionModel) -> ToolSummary:
    return ToolSummary(
        id=str(tool.id),
        namespace=tool.namespace,
        canonical_name=tool.canonical_name,
        owner=tool.owner,
        status=tool.status,
        latest_version_id=str(version.id),
        latest_version=version.version,
        display_name=version.display_name,
        description=version.description,
        version_status=version.status,
        visibility=version.visibility,
        side_effect=version.side_effect,
        tags=tuple(version.tags_json),
        created_at=tool.created_at,
        updated_at=tool.updated_at,
    )


def _tool_detail(model: ToolModel) -> ToolDetail:
    return ToolDetail(
        id=str(model.id),
        tenant_id=str(model.tenant_id),
        namespace=model.namespace,
        canonical_name=model.canonical_name,
        owner=model.owner,
        status=model.status,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _version_detail(model: ToolVersionModel) -> ToolVersionDetail:
    return ToolVersionDetail(
        id=str(model.id),
        tool_id=str(model.tool_id),
        version=model.version,
        display_name=model.display_name,
        description=model.description,
        input_schema=dict(model.input_schema_json),
        output_schema=(dict(model.output_schema_json) if model.output_schema_json else None),
        schema_digest=model.schema_digest,
        tags=tuple(model.tags_json),
        side_effect=model.side_effect,
        visibility=model.visibility,
        status=model.status,
        created_by=model.created_by,
        created_at=model.created_at,
        reviewed_at=model.reviewed_at,
        published_at=model.published_at,
        retired_at=model.retired_at,
    )


def _binding_detail(model: ToolBindingModel) -> ToolBindingDetail:
    return ToolBindingDetail(
        id=str(model.id),
        tool_version_id=str(model.tool_version_id),
        upstream_service_id=str(model.upstream_service_id),
        imported_operation_id=(
            str(model.imported_operation_id) if model.imported_operation_id else None
        ),
        binding_type=model.binding_type,
        binding_config=dict(model.binding_config_json),
        binding_digest=model.binding_digest,
        status=model.status,
        created_at=model.created_at,
        updated_at=model.updated_at,
        published_at=model.published_at,
    )


def _approval_summary(model: ApprovalRequestModel, canonical_name: str) -> ApprovalSummary:
    return ApprovalSummary(
        id=str(model.id),
        principal_id=model.principal_id,
        tool_id=str(model.tool_id),
        tool_version_id=str(model.tool_version_id),
        canonical_name=canonical_name,
        arguments_digest=model.arguments_digest,
        policy_version=model.policy_version,
        has_idempotency_key=model.idempotency_key is not None,
        status=model.status,
        requested_at=model.requested_at,
        expires_at=model.expires_at,
        decided_by=model.decided_by,
        decided_at=model.decided_at,
        consumed_at=model.consumed_at,
    )


def _execution_summary(model: ToolExecutionModel, canonical_name: str) -> ExecutionSummary:
    return ExecutionSummary(
        id=str(model.id),
        request_id=model.request_id,
        trace_id=model.trace_id,
        principal_id=model.principal_id,
        tool_id=str(model.tool_id),
        tool_version_id=str(model.tool_version_id),
        tool_binding_id=str(model.tool_binding_id),
        canonical_name=canonical_name,
        policy_version=model.policy_version,
        policy_reason_code=model.policy_reason_code,
        side_effect=model.side_effect,
        status=model.status,
        has_idempotency_key=model.idempotency_key is not None,
        planned_at=model.planned_at,
        started_at=model.started_at,
        finished_at=model.finished_at,
        error_code=model.error_code,
        error_category=model.error_category,
        attempt_count=model.attempt_count,
    )


def _attempt_summary(model: ExecutionAttemptModel) -> ExecutionAttemptSummary:
    return ExecutionAttemptSummary(
        id=str(model.id),
        execution_id=str(model.execution_id),
        attempt_number=model.attempt_number,
        status=model.status,
        started_at=model.started_at,
        finished_at=model.finished_at,
        error_code=model.error_code,
        error_category=model.error_category,
        upstream_status=model.upstream_status,
    )


def _audit_summary(model: AuditEventModel) -> AuditEventSummary:
    return AuditEventSummary(
        id=str(model.id),
        actor_id=model.actor_id,
        action=model.action,
        resource_type=model.resource_type,
        resource_id=model.resource_id,
        outcome=model.outcome,
        request_id=model.request_id,
        trace_id=model.trace_id,
        occurred_at=model.occurred_at,
        arguments_digest=model.arguments_digest,
        policy_version=model.policy_version,
        reason_code=model.reason_code,
        execution_id=str(model.execution_id) if model.execution_id else None,
        metadata=dict(model.metadata_json),
    )
