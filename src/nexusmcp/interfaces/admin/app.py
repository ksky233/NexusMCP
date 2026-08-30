"""S2 最小 Control Plane REST 子应用。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import BackgroundTasks, Depends, FastAPI, Query, Request, status
from pydantic import BaseModel, Field
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from nexusmcp.interfaces.admin.query_models import PageMetadata
from nexusmcp.interfaces.admin.query_routes import create_admin_query_router
from nexusmcp.interfaces.http.errors import problem_responses, register_http_exception_handlers
from nexusmcp.modules.approval.domain import ApprovalRequest
from nexusmcp.modules.approval.use_cases import (
    DecideApproval,
    DecideApprovalCommand,
    GetApproval,
    GetApprovalQuery,
)
from nexusmcp.modules.catalog.domain import ToolSideEffect, ToolVisibility
from nexusmcp.modules.catalog.publish import PublishTool, PublishToolCommand
from nexusmcp.modules.catalog.review import (
    SubmitToolVersionForReview,
    SubmitToolVersionForReviewCommand,
)
from nexusmcp.modules.catalog.search import SearchPublishedTools, SearchPublishedToolsQuery
from nexusmcp.modules.control_plane.ports import ControlPlaneQueryPort
from nexusmcp.modules.control_plane.read_models import UpstreamDetail
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
    RegisterUpstream,
    RegisterUpstreamCommand,
    UpdateUpstream,
    UpdateUpstreamCommand,
)
from nexusmcp.modules.tool_search.domain import ToolRetrievalMode
from nexusmcp.modules.tool_search.index_management import (
    CreateToolSearchReindexJob,
    GetToolSearchReindexJob,
    InspectToolSearchIndex,
    ListToolSearchReindexJobs,
    RunToolSearchReindexJob,
    ToolSearchIndexItem,
    ToolSearchIndexSnapshot,
    ToolSearchReindexJob,
)
from nexusmcp.modules.tool_search.search_tools import SearchTools, SearchToolsQuery
from nexusmcp.shared.errors import FeatureNotEnabledError
from nexusmcp.shared.log_context import bind_log_context
from nexusmcp.shared.request_context import ActorContext, ProtocolEra, RequestContext


@dataclass(frozen=True, slots=True)
class AdminServices:
    register_upstream: RegisterUpstream
    update_upstream: UpdateUpstream
    disable_upstream: DisableUpstream
    queries: ControlPlaneQueryPort
    import_openapi: ImportOpenApi
    get_openapi_import: GetOpenApiImport
    review_operation: ReviewImportedOperation
    submit_version_review: SubmitToolVersionForReview
    publish_tool: PublishTool
    search_tools: SearchPublishedTools
    search_lab: SearchTools | None
    inspect_search_index: InspectToolSearchIndex
    create_reindex_job: CreateToolSearchReindexJob
    run_reindex_job: RunToolSearchReindexJob
    get_reindex_job: GetToolSearchReindexJob
    list_reindex_jobs: ListToolSearchReindexJobs
    decide_approval: DecideApproval
    get_approval: GetApproval


class RegisterUpstreamRequest(BaseModel):
    namespace: str
    name: str
    description: str | None = None
    owner: str
    endpoint: str
    auth_scheme: str | None = "none"
    config: dict[str, Any] = Field(default_factory=dict)
    service_type: str = Field(
        default=UpstreamServiceType.HTTP.value,
        json_schema_extra={"enum": [UpstreamServiceType.HTTP.value]},
    )
    transport_type: str = Field(default="http", json_schema_extra={"enum": ["http"]})


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
    service_type: Literal["http"]
    transport_type: Literal["http"]
    endpoint: str
    auth_scheme: str | None
    config: dict[str, Any]
    status: UpstreamStatus

    @classmethod
    def from_domain(cls, upstream: UpstreamService) -> UpstreamResponse:
        if (
            upstream.service_type is not UpstreamServiceType.HTTP
            or upstream.transport_type != "http"
        ):
            raise FeatureNotEnabledError("Remote MCP upstream response is not supported")
        return cls(
            id=upstream.id,
            tenant_id=upstream.tenant_id,
            namespace=upstream.namespace,
            name=upstream.name,
            description=upstream.description,
            owner=upstream.owner,
            service_type="http",
            transport_type="http",
            endpoint=upstream.endpoint,
            auth_scheme=upstream.auth_scheme,
            config=dict(upstream.config),
            status=upstream.status,
        )

    @classmethod
    def from_read_model(cls, upstream: UpstreamDetail) -> UpstreamResponse:
        if upstream.service_type != "http" or upstream.transport_type != "http":
            raise FeatureNotEnabledError("Remote MCP upstream response is not supported")
        return cls(
            id=upstream.id,
            tenant_id=upstream.tenant_id,
            namespace=upstream.namespace,
            name=upstream.name,
            description=upstream.description,
            owner=upstream.owner,
            service_type="http",
            transport_type="http",
            endpoint=upstream.endpoint,
            auth_scheme=upstream.auth_scheme,
            config=dict(upstream.config),
            status=UpstreamStatus(upstream.status),
        )


class UpstreamPageResponse(BaseModel):
    items: list[UpstreamResponse]
    page: PageMetadata


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


class SearchLabHitResponse(BaseModel):
    position: int
    tool_id: str
    tool_version_id: str
    canonical_name: str
    display_name: str
    description: str
    version: int
    visibility: ToolVisibility
    side_effect: ToolSideEffect
    owner: str | None
    tags: list[str]
    rank: float
    score_kind: Literal["fts", "rrf"]
    lexical_rank: int | None
    lexical_score: float | None
    vector_rank: int | None
    vector_cosine_similarity: float | None
    rrf_score: float | None
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None


class SearchLabResponse(BaseModel):
    retrieval_mode: ToolRetrievalMode
    index_version: str | None
    hits: list[SearchLabHitResponse]


class ToolSearchIndexItemResponse(BaseModel):
    tool_id: str
    tool_version_id: str
    canonical_name: str
    state: Literal["missing", "stale", "current"]
    indexed_at: datetime | None


class ToolSearchIndexStatusResponse(BaseModel):
    published_count: int
    current_count: int
    missing_count: int
    stale_count: int
    embedding_model: str
    embedding_dimensions: int
    embedding_available: bool
    items: list[ToolSearchIndexItemResponse]
    page: PageMetadata


class CreateToolSearchReindexJobRequest(BaseModel):
    force: bool = False
    batch_size: int = Field(default=16, ge=1, le=64)


class ToolSearchReindexJobResponse(BaseModel):
    id: str
    tenant_id: str
    requested_by: str
    status: Literal["pending", "running", "succeeded", "failed"]
    force: bool
    batch_size: int
    embedding_model: str
    embedding_dimensions: int
    published_count: int
    current_count: int
    pending_count: int
    embedded_count: int
    batch_count: int
    error_code: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ToolSearchReindexJobPageResponse(BaseModel):
    items: list[ToolSearchReindexJobResponse]
    page: PageMetadata


class ApprovalResponse(BaseModel):
    id: str
    tenant_id: str
    principal_id: str
    tool_id: str
    tool_version_id: str
    arguments_digest: str
    policy_version: str
    idempotency_key: str | None
    status: str
    requested_at: datetime
    expires_at: datetime
    decided_by: str | None
    decided_at: datetime | None
    consumed_at: datetime | None

    @classmethod
    def from_domain(cls, approval: ApprovalRequest) -> ApprovalResponse:
        return cls(
            id=approval.id,
            tenant_id=approval.tenant_id,
            principal_id=approval.principal_id,
            tool_id=approval.tool_id,
            tool_version_id=approval.tool_version_id,
            arguments_digest=approval.arguments_digest,
            policy_version=approval.policy_version,
            idempotency_key=approval.idempotency_key,
            status=approval.status.value,
            requested_at=approval.requested_at,
            expires_at=approval.expires_at,
            decided_by=approval.decided_by,
            decided_at=approval.decided_at,
            consumed_at=approval.consumed_at,
        )


def get_admin_context(request: Request) -> ActorContext:
    context: ActorContext = request.state.actor_context
    return context


AdminContext = Annotated[ActorContext, Depends(get_admin_context)]


class AdminFastAPI(FastAPI):
    def openapi(self) -> dict[str, Any]:
        schema = super().openapi()
        _normalize_problem_response_media_types(schema)
        return schema


def create_admin_app(
    services: AdminServices,
    *,
    tenant_id: str,
    principal_id: str,
) -> FastAPI:
    app = AdminFastAPI(
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
        operation_id="registerUpstream",
        responses=problem_responses(400, 409, 501),
    )
    async def register_upstream(
        request: RegisterUpstreamRequest,
        context: AdminContext,
    ) -> UpstreamResponse:
        if request.service_type != "http" or request.transport_type != "http":
            raise FeatureNotEnabledError("Remote MCP upstream registration is not supported")
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
                service_type=UpstreamServiceType.HTTP,
                transport_type="http",
            )
        )
        return UpstreamResponse.from_domain(upstream)

    @app.get(
        "/upstreams",
        response_model=UpstreamPageResponse,
        operation_id="listUpstreams",
        responses=problem_responses(400),
    )
    async def list_upstreams(
        context: AdminContext,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        namespace: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
        upstream_status: Annotated[UpstreamStatus | None, Query(alias="status")] = None,
    ) -> UpstreamPageResponse:
        upstreams = await services.queries.list_upstreams(
            context.tenant_id,
            offset=offset,
            limit=limit,
            namespace=namespace,
            status=upstream_status.value if upstream_status else None,
        )
        return UpstreamPageResponse(
            items=[UpstreamResponse.from_read_model(upstream) for upstream in upstreams.items],
            page=PageMetadata(
                offset=upstreams.offset,
                limit=upstreams.limit,
                total=upstreams.total,
            ),
        )

    @app.put(
        "/upstreams/{upstream_service_id}",
        response_model=UpstreamResponse,
        operation_id="updateUpstream",
        responses=problem_responses(400, 404),
    )
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

    @app.post(
        "/upstreams/{upstream_service_id}/disable",
        response_model=UpstreamResponse,
        operation_id="disableUpstream",
        responses=problem_responses(404, 409),
    )
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
        operation_id="submitOpenApiImport",
        responses=problem_responses(400, 404, 422),
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

    @app.get(
        "/openapi/imports/{import_job_id}",
        response_model=ImportDetailResponse,
        operation_id="getOpenApiImport",
        responses=problem_responses(404),
    )
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
        operation_id="reviewImportedOperation",
        responses=problem_responses(404, 409, 422),
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
        operation_id="submitToolVersionReview",
        responses=problem_responses(404, 409),
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
        operation_id="publishToolVersion",
        responses=problem_responses(404, 409, 422),
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

    @app.get(
        "/catalog/search",
        response_model=list[SearchToolResponse],
        operation_id="searchCatalog",
        responses=problem_responses(422, 503),
    )
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

    @app.get(
        "/tool-search/index-status",
        response_model=ToolSearchIndexStatusResponse,
        operation_id="getToolSearchIndexStatus",
        responses=problem_responses(503),
    )
    async def get_tool_search_index_status(
        context: AdminContext,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> ToolSearchIndexStatusResponse:
        snapshot = await services.inspect_search_index.execute(context.tenant_id)
        return _index_status_response(snapshot, offset=offset, limit=limit)

    @app.post(
        "/tool-search/reindex-jobs",
        response_model=ToolSearchReindexJobResponse,
        status_code=status.HTTP_202_ACCEPTED,
        operation_id="createToolSearchReindexJob",
        responses=problem_responses(409, 503),
    )
    async def create_tool_search_reindex_job(
        request: CreateToolSearchReindexJobRequest,
        context: AdminContext,
        background_tasks: BackgroundTasks,
    ) -> ToolSearchReindexJobResponse:
        job = await services.create_reindex_job.execute(
            context,
            force=request.force,
            batch_size=request.batch_size,
        )
        background_tasks.add_task(
            services.run_reindex_job.execute,
            context.tenant_id,
            job.id,
        )
        return _reindex_job_response(job)

    @app.get(
        "/tool-search/reindex-jobs",
        response_model=ToolSearchReindexJobPageResponse,
        operation_id="listToolSearchReindexJobs",
        responses=problem_responses(422),
    )
    async def list_tool_search_reindex_jobs(
        context: AdminContext,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> ToolSearchReindexJobPageResponse:
        jobs, total = await services.list_reindex_jobs.execute(
            context.tenant_id,
            offset=offset,
            limit=limit,
        )
        return ToolSearchReindexJobPageResponse(
            items=[_reindex_job_response(job) for job in jobs],
            page=PageMetadata(offset=offset, limit=limit, total=total),
        )

    @app.get(
        "/tool-search/reindex-jobs/{job_id}",
        response_model=ToolSearchReindexJobResponse,
        operation_id="getToolSearchReindexJob",
        responses=problem_responses(404),
    )
    async def get_tool_search_reindex_job(
        job_id: str,
        context: AdminContext,
    ) -> ToolSearchReindexJobResponse:
        return _reindex_job_response(
            await services.get_reindex_job.execute(context.tenant_id, job_id)
        )

    @app.get(
        "/search/tools",
        response_model=SearchLabResponse,
        operation_id="searchTools",
        responses=problem_responses(422, 503),
    )
    async def search_tool_candidates(
        context: AdminContext,
        query_text: Annotated[str, Query(alias="q", min_length=1, max_length=500)],
        retrieval_mode: ToolRetrievalMode,
        limit: Annotated[int, Query(ge=1, le=10)] = 5,
        namespace: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
        side_effect: ToolSideEffect | None = None,
    ) -> SearchLabResponse:
        if services.search_lab is None:
            raise FeatureNotEnabledError("Tool Search Lab was not composed")
        result = await services.search_lab.execute(
            SearchToolsQuery(
                context=RequestContext(
                    request_id=context.request_id,
                    trace_id=context.trace_id,
                    tenant_id=context.tenant_id,
                    principal_id=context.principal_id,
                    authn_method=context.authn_method,
                    principal_type=context.principal_type,
                    protocol_version="2026-07-28",
                    protocol_era=ProtocolEra.MODERN,
                ),
                text=query_text,
                retrieval_mode=retrieval_mode,
                limit=limit,
                namespace=namespace,
                side_effect=side_effect,
            )
        )
        return SearchLabResponse(
            retrieval_mode=result.retrieval_mode,
            index_version=result.index_version,
            hits=[
                SearchLabHitResponse(
                    position=position,
                    tool_id=hit.tool.tool_id,
                    tool_version_id=hit.tool.tool_version_id,
                    canonical_name=hit.tool.canonical_name,
                    display_name=hit.tool.display_name,
                    description=hit.tool.description,
                    version=hit.tool.version,
                    visibility=hit.tool.visibility,
                    side_effect=hit.tool.side_effect,
                    owner=hit.tool.owner,
                    tags=list(hit.tool.tags),
                    rank=hit.rank,
                    score_kind=(
                        result.diagnostics[hit.tool.tool_version_id].score_kind
                        if result.diagnostics is not None
                        else ("rrf" if result.retrieval_mode is ToolRetrievalMode.HYBRID else "fts")
                    ),
                    lexical_rank=(
                        result.diagnostics[hit.tool.tool_version_id].lexical_rank
                        if result.diagnostics is not None
                        else None
                    ),
                    lexical_score=(
                        result.diagnostics[hit.tool.tool_version_id].lexical_score
                        if result.diagnostics is not None
                        else None
                    ),
                    vector_rank=(
                        result.diagnostics[hit.tool.tool_version_id].vector_rank
                        if result.diagnostics is not None
                        else None
                    ),
                    vector_cosine_similarity=(
                        result.diagnostics[hit.tool.tool_version_id].vector_cosine_similarity
                        if result.diagnostics is not None
                        else None
                    ),
                    rrf_score=(
                        result.diagnostics[hit.tool.tool_version_id].rrf_score
                        if result.diagnostics is not None
                        else None
                    ),
                    input_schema=dict(hit.tool.input_schema),
                    output_schema=(
                        dict(hit.tool.output_schema) if hit.tool.output_schema is not None else None
                    ),
                )
                for position, hit in enumerate(result.hits, start=1)
            ],
        )

    @app.get(
        "/approvals/{approval_id}",
        response_model=ApprovalResponse,
        operation_id="getApproval",
        responses=problem_responses(404),
    )
    async def get_approval(
        approval_id: str,
        context: AdminContext,
    ) -> ApprovalResponse:
        approval = await services.get_approval.execute(
            GetApprovalQuery(context=context, approval_id=approval_id)
        )
        return ApprovalResponse.from_domain(approval)

    @app.post(
        "/approvals/{approval_id}/approve",
        response_model=ApprovalResponse,
        operation_id="approveApproval",
        responses=problem_responses(404, 409),
    )
    async def approve_call(
        approval_id: str,
        context: AdminContext,
    ) -> ApprovalResponse:
        approval = await services.decide_approval.execute(
            DecideApprovalCommand(
                context=context,
                approval_id=approval_id,
                approved=True,
            )
        )
        return ApprovalResponse.from_domain(approval)

    @app.post(
        "/approvals/{approval_id}/reject",
        response_model=ApprovalResponse,
        operation_id="rejectApproval",
        responses=problem_responses(404, 409),
    )
    async def reject_call(
        approval_id: str,
        context: AdminContext,
    ) -> ApprovalResponse:
        approval = await services.decide_approval.execute(
            DecideApprovalCommand(
                context=context,
                approval_id=approval_id,
                approved=False,
            )
        )
        return ApprovalResponse.from_domain(approval)

    app.include_router(create_admin_query_router(services.queries))
    return app


def _index_status_response(
    snapshot: ToolSearchIndexSnapshot,
    *,
    offset: int,
    limit: int,
) -> ToolSearchIndexStatusResponse:
    selected = snapshot.items[offset : offset + limit]
    return ToolSearchIndexStatusResponse(
        published_count=snapshot.published_count,
        current_count=snapshot.current_count,
        missing_count=snapshot.missing_count,
        stale_count=snapshot.stale_count,
        embedding_model=snapshot.embedding_model,
        embedding_dimensions=snapshot.embedding_dimensions,
        embedding_available=snapshot.embedding_available,
        items=[_index_item_response(item) for item in selected],
        page=PageMetadata(offset=offset, limit=limit, total=len(snapshot.items)),
    )


def _index_item_response(item: ToolSearchIndexItem) -> ToolSearchIndexItemResponse:
    return ToolSearchIndexItemResponse(
        tool_id=item.tool_id,
        tool_version_id=item.tool_version_id,
        canonical_name=item.canonical_name,
        state=item.state.value,
        indexed_at=item.indexed_at,
    )


def _reindex_job_response(job: ToolSearchReindexJob) -> ToolSearchReindexJobResponse:
    return ToolSearchReindexJobResponse(
        id=job.id,
        tenant_id=job.tenant_id,
        requested_by=job.requested_by,
        status=job.status.value,
        force=job.force,
        batch_size=job.batch_size,
        embedding_model=job.embedding_model,
        embedding_dimensions=job.embedding_dimensions,
        published_count=job.published_count,
        current_count=job.current_count,
        pending_count=job.pending_count,
        embedded_count=job.embedded_count,
        batch_count=job.batch_count,
        error_code=job.error_code,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def _normalize_problem_response_media_types(schema: dict[str, Any]) -> None:
    """FastAPI 的 `model` 默认声明 JSON；Admin Error Contract 只暴露 Problem JSON。"""

    paths = schema.get("paths")
    if not isinstance(paths, dict):  # pragma: no cover - FastAPI OpenAPI 固定结构
        return
    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            responses = operation.get("responses")
            if not isinstance(responses, dict):
                continue
            for response in responses.values():
                if not isinstance(response, dict):
                    continue
                content = response.get("content")
                if not isinstance(content, dict) or "application/problem+json" not in content:
                    continue
                json_contract = content.pop("application/json", None)
                if isinstance(json_contract, dict):
                    content["application/problem+json"] = json_contract


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
