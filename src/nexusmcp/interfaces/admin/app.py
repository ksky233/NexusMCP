"""S2 最小 Control Plane REST 子应用。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Query, Request, status
from pydantic import BaseModel, Field
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from nexusmcp.interfaces.http.errors import register_http_exception_handlers
from nexusmcp.modules.catalog.domain import ToolSideEffect, ToolVisibility
from nexusmcp.modules.catalog.publish import PublishTool, PublishToolCommand
from nexusmcp.modules.catalog.review import (
    SubmitToolVersionForReview,
    SubmitToolVersionForReviewCommand,
)
from nexusmcp.modules.catalog.search import SearchPublishedTools, SearchPublishedToolsQuery
from nexusmcp.modules.openapi_import.domain import ImportedOperation, OpenApiImportJob
from nexusmcp.modules.openapi_import.import_openapi import ImportOpenApi, ImportOpenApiCommand
from nexusmcp.modules.openapi_import.queries import GetOpenApiImport, GetOpenApiImportQuery
from nexusmcp.modules.openapi_import.review import (
    ReviewImportedOperation,
    ReviewImportedOperationCommand,
)
from nexusmcp.modules.registry.domain import (
    UpstreamService,
    UpstreamServiceType,
    UpstreamStatus,
)
from nexusmcp.modules.registry.use_cases import (
    DisableUpstream,
    DisableUpstreamCommand,
    ListUpstreams,
    RegisterUpstream,
    RegisterUpstreamCommand,
    UpdateUpstream,
    UpdateUpstreamCommand,
)
from nexusmcp.shared.log_context import bind_log_context
from nexusmcp.shared.request_context import ActorContext


@dataclass(frozen=True, slots=True)
class AdminServices:
    register_upstream: RegisterUpstream
    update_upstream: UpdateUpstream
    disable_upstream: DisableUpstream
    list_upstreams: ListUpstreams
    import_openapi: ImportOpenApi
    get_openapi_import: GetOpenApiImport
    review_operation: ReviewImportedOperation
    submit_version_review: SubmitToolVersionForReview
    publish_tool: PublishTool
    search_tools: SearchPublishedTools


class RegisterUpstreamRequest(BaseModel):
    namespace: str
    name: str
    description: str | None = None
    owner: str
    endpoint: str
    auth_scheme: str | None = "none"
    config: dict[str, Any] = Field(default_factory=dict)
    service_type: UpstreamServiceType = UpstreamServiceType.HTTP
    transport_type: str = "http"


class UpdateUpstreamRequest(BaseModel):
    description: str | None = None
    owner: str
    endpoint: str
    auth_scheme: str | None = "none"
    config: dict[str, Any] = Field(default_factory=dict)


class UpstreamResponse(BaseModel):
    id: str
    tenant_id: str
    namespace: str
    name: str
    description: str | None
    owner: str
    service_type: UpstreamServiceType
    transport_type: str
    endpoint: str
    auth_scheme: str | None
    config: dict[str, Any]
    status: UpstreamStatus

    @classmethod
    def from_domain(cls, upstream: UpstreamService) -> UpstreamResponse:
        return cls(
            id=upstream.id,
            tenant_id=upstream.tenant_id,
            namespace=upstream.namespace,
            name=upstream.name,
            description=upstream.description,
            owner=upstream.owner,
            service_type=upstream.service_type,
            transport_type=upstream.transport_type,
            endpoint=upstream.endpoint,
            auth_scheme=upstream.auth_scheme,
            config=dict(upstream.config),
            status=upstream.status,
        )


class SubmitImportRequest(BaseModel):
    upstream_service_id: str
    source_ref: str
    operation_allowlist: list[str] = Field(default_factory=list)


class SubmitImportResponse(BaseModel):
    import_job_id: str
    operation_ids: list[str]
    conflict_count: int


class ImportJobResponse(BaseModel):
    id: str
    upstream_service_id: str
    source_ref: str
    source_digest: str
    openapi_version: str | None
    status: str
    error_summary: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class ImportedOperationResponse(BaseModel):
    id: str
    operation_key: str
    operation_id: str | None
    method: str
    path: str
    generated_tool_name: str | None
    conflict_status: str
    review_status: str
    draft_tool_version_id: str | None
    draft_tool_binding_id: str | None


class ImportDetailResponse(BaseModel):
    job: ImportJobResponse
    operations: list[ImportedOperationResponse]


class ReviewOperationRequest(BaseModel):
    owner: str
    visibility: ToolVisibility = ToolVisibility.PUBLIC
    review_notes: str | None = None


class ReviewOperationResponse(BaseModel):
    operation_id: str
    tool_id: str
    tool_version_id: str
    tool_binding_id: str
    canonical_name: str
    version: int
    schema_digest: str
    binding_digest: str


class StateResponse(BaseModel):
    status: str


class PublishToolRequest(BaseModel):
    expected_schema_digest: str
    expected_binding_digest: str


class PublishToolResponse(BaseModel):
    tool_id: str
    tool_version_id: str
    tool_binding_id: str
    canonical_name: str
    version: int
    retired_tool_version_id: str | None
    occurred_at: datetime


class SearchToolResponse(BaseModel):
    tool_id: str
    tool_version_id: str
    canonical_name: str
    display_name: str
    description: str
    version: int
    visibility: ToolVisibility
    side_effect: ToolSideEffect
    rank: float


def get_admin_context(request: Request) -> ActorContext:
    context: ActorContext = request.state.actor_context
    return context


AdminContext = Annotated[ActorContext, Depends(get_admin_context)]


def create_admin_app(
    services: AdminServices,
    *,
    tenant_id: str,
    principal_id: str,
) -> FastAPI:
    app = FastAPI(
        title="NexusMCP Admin API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
    )
    register_http_exception_handlers(app)

    @app.middleware("http")
    async def bind_admin_context(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        context = ActorContext(
            request_id=str(uuid.uuid4()),
            trace_id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            principal_id=principal_id,
            authn_method="local_admin",
        )
        request.state.actor_context = context
        with bind_log_context(
            request_id=context.request_id,
            trace_id=context.trace_id,
            tenant_id=context.tenant_id,
        ):
            response = await call_next(request)
        response.headers["X-Request-ID"] = context.request_id
        return response

    @app.post(
        "/upstreams",
        response_model=UpstreamResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def register_upstream(
        request: RegisterUpstreamRequest,
        context: AdminContext,
    ) -> UpstreamResponse:
        upstream = await services.register_upstream.execute(
            RegisterUpstreamCommand(
                context=context,
                namespace=request.namespace,
                name=request.name,
                description=request.description,
                owner=request.owner,
                endpoint=request.endpoint,
                auth_scheme=request.auth_scheme,
                config=request.config,
                service_type=request.service_type,
                transport_type=request.transport_type,
            )
        )
        return UpstreamResponse.from_domain(upstream)

    @app.get("/upstreams", response_model=list[UpstreamResponse])
    async def list_upstreams(context: AdminContext) -> list[UpstreamResponse]:
        upstreams = await services.list_upstreams.execute(context)
        return [UpstreamResponse.from_domain(upstream) for upstream in upstreams]

    @app.put("/upstreams/{upstream_service_id}", response_model=UpstreamResponse)
    async def update_upstream(
        upstream_service_id: str,
        request: UpdateUpstreamRequest,
        context: AdminContext,
    ) -> UpstreamResponse:
        upstream = await services.update_upstream.execute(
            UpdateUpstreamCommand(
                context=context,
                upstream_service_id=upstream_service_id,
                description=request.description,
                owner=request.owner,
                endpoint=request.endpoint,
                auth_scheme=request.auth_scheme,
                config=request.config,
            )
        )
        return UpstreamResponse.from_domain(upstream)

    @app.post("/upstreams/{upstream_service_id}/disable", response_model=UpstreamResponse)
    async def disable_upstream(
        upstream_service_id: str,
        context: AdminContext,
    ) -> UpstreamResponse:
        upstream = await services.disable_upstream.execute(
            DisableUpstreamCommand(
                context=context,
                upstream_service_id=upstream_service_id,
            )
        )
        return UpstreamResponse.from_domain(upstream)

    @app.post(
        "/openapi/imports",
        response_model=SubmitImportResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def submit_import(
        request: SubmitImportRequest,
        context: AdminContext,
    ) -> SubmitImportResponse:
        result = await services.import_openapi.execute(
            ImportOpenApiCommand(
                context=context,
                upstream_service_id=request.upstream_service_id,
                source_ref=request.source_ref,
                operation_allowlist=tuple(request.operation_allowlist),
            )
        )
        return SubmitImportResponse(
            import_job_id=result.import_job_id,
            operation_ids=list(result.operation_ids),
            conflict_count=result.conflict_count,
        )

    @app.get("/openapi/imports/{import_job_id}", response_model=ImportDetailResponse)
    async def get_import(
        import_job_id: str,
        context: AdminContext,
    ) -> ImportDetailResponse:
        result = await services.get_openapi_import.execute(
            GetOpenApiImportQuery(context=context, import_job_id=import_job_id)
        )
        return ImportDetailResponse(
            job=_job_response(result.job),
            operations=[_operation_response(operation) for operation in result.operations],
        )

    @app.post(
        "/openapi/operations/{operation_id}/review",
        response_model=ReviewOperationResponse,
    )
    async def review_operation(
        operation_id: str,
        request: ReviewOperationRequest,
        context: AdminContext,
    ) -> ReviewOperationResponse:
        result = await services.review_operation.execute(
            ReviewImportedOperationCommand(
                context=context,
                operation_id=operation_id,
                owner=request.owner,
                visibility=request.visibility,
                review_notes=request.review_notes,
            )
        )
        return ReviewOperationResponse(
            operation_id=result.operation_id,
            tool_id=result.tool_id,
            tool_version_id=result.tool_version_id,
            tool_binding_id=result.tool_binding_id,
            canonical_name=result.canonical_name,
            version=result.version,
            schema_digest=result.schema_digest,
            binding_digest=result.binding_digest,
        )

    @app.post(
        "/tool-versions/{tool_version_id}/submit-review",
        response_model=StateResponse,
    )
    async def submit_version_review(
        tool_version_id: str,
        context: AdminContext,
    ) -> StateResponse:
        await services.submit_version_review.execute(
            SubmitToolVersionForReviewCommand(
                context=context,
                tool_version_id=tool_version_id,
            )
        )
        return StateResponse(status="review")

    @app.post(
        "/tools/{tool_id}/versions/{tool_version_id}/publish",
        response_model=PublishToolResponse,
    )
    async def publish_tool(
        tool_id: str,
        tool_version_id: str,
        request: PublishToolRequest,
        context: AdminContext,
    ) -> PublishToolResponse:
        result = await services.publish_tool.execute(
            PublishToolCommand(
                context=context,
                tool_id=tool_id,
                tool_version_id=tool_version_id,
                expected_schema_digest=request.expected_schema_digest,
                expected_binding_digest=request.expected_binding_digest,
            )
        )
        event = result.event
        return PublishToolResponse(
            tool_id=event.tool_id,
            tool_version_id=event.tool_version_id,
            tool_binding_id=event.tool_binding_id,
            canonical_name=event.canonical_name,
            version=event.version,
            retired_tool_version_id=result.retired_tool_version_id,
            occurred_at=event.occurred_at,
        )

    @app.get("/catalog/search", response_model=list[SearchToolResponse])
    async def search_catalog(
        context: AdminContext,
        query_text: Annotated[str, Query(alias="q", min_length=1, max_length=200)],
        limit: Annotated[int, Query(ge=1, le=50)] = 10,
    ) -> list[SearchToolResponse]:
        hits = await services.search_tools.execute(
            SearchPublishedToolsQuery(
                context=context,
                text=query_text,
                limit=limit,
            )
        )
        return [
            SearchToolResponse(
                tool_id=hit.tool.tool_id,
                tool_version_id=hit.tool.tool_version_id,
                canonical_name=hit.tool.canonical_name,
                display_name=hit.tool.display_name,
                description=hit.tool.description,
                version=hit.tool.version,
                visibility=hit.tool.visibility,
                side_effect=hit.tool.side_effect,
                rank=hit.rank,
            )
            for hit in hits
        ]

    return app


def _job_response(job: OpenApiImportJob) -> ImportJobResponse:
    return ImportJobResponse(
        id=job.id,
        upstream_service_id=job.upstream_service_id,
        source_ref=job.source_ref,
        source_digest=job.source_digest,
        openapi_version=job.openapi_version,
        status=job.status.value,
        error_summary=job.error_summary,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


def _operation_response(operation: ImportedOperation) -> ImportedOperationResponse:
    return ImportedOperationResponse(
        id=operation.id,
        operation_key=operation.operation_key,
        operation_id=operation.operation_id,
        method=operation.method,
        path=operation.path,
        generated_tool_name=operation.generated_tool_name,
        conflict_status=operation.conflict_status.value,
        review_status=operation.review_status.value,
        draft_tool_version_id=operation.draft_tool_version_id,
        draft_tool_binding_id=operation.draft_tool_binding_id,
    )
