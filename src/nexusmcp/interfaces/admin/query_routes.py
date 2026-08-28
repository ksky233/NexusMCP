"""W1 Web Control Plane 所需的只读 Admin Routes。"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from nexusmcp.interfaces.admin.query_models import (
    ApprovalPageResponse,
    ApprovalSummaryResponse,
    AuditEventPageResponse,
    AuditEventResponse,
    DashboardResponse,
    ExecutionAttemptPageResponse,
    ExecutionAttemptResponse,
    ExecutionPageResponse,
    ExecutionSummaryResponse,
    ImportJobPageResponse,
    ImportJobSummaryResponse,
    PageMetadata,
    ReviewOperationPageResponse,
    ReviewOperationSummaryResponse,
    SearchProjectionResponse,
    ToolBindingDetailResponse,
    ToolDetailResponse,
    ToolPageResponse,
    ToolSummaryResponse,
    ToolVersionDetailResponse,
    ToolVersionPageResponse,
    UpstreamDetailResponse,
)
from nexusmcp.interfaces.http.errors import problem_responses
from nexusmcp.modules.approval.domain import ApprovalStatus
from nexusmcp.modules.audit.domain import AuditOutcome
from nexusmcp.modules.catalog.domain import (
    ToolSideEffect,
    ToolStatus,
    ToolVersionStatus,
    ToolVisibility,
)
from nexusmcp.modules.control_plane.ports import ControlPlaneQueryPort
from nexusmcp.modules.control_plane.read_models import Page
from nexusmcp.modules.execution.domain import ExecutionStatus
from nexusmcp.modules.openapi_import.domain import (
    ImportJobStatus,
    OperationConflictStatus,
    OperationReviewStatus,
)
from nexusmcp.shared.errors import (
    FeatureNotEnabledError,
    ToolBindingNotFoundError,
    ToolExecutionNotFoundError,
    ToolNotFoundError,
    ToolVersionNotFoundError,
    UpstreamNotFoundError,
)
from nexusmcp.shared.request_context import ActorContext

PageOffset = Annotated[int, Query(ge=0)]
PageLimit = Annotated[int, Query(ge=1, le=100)]


def _admin_context(request: Request) -> ActorContext:
    context: ActorContext = request.state.actor_context
    return context


AdminContext = Annotated[ActorContext, Depends(_admin_context)]


def create_admin_query_router(queries: ControlPlaneQueryPort) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/dashboard",
        response_model=DashboardResponse,
        operation_id="getDashboard",
        responses=problem_responses(503),
    )
    async def get_dashboard(context: AdminContext) -> DashboardResponse:
        return DashboardResponse.model_validate(await queries.dashboard(context.tenant_id))

    @router.get(
        "/upstreams/{upstream_service_id}",
        response_model=UpstreamDetailResponse,
        operation_id="getUpstream",
        responses=problem_responses(404, 501),
    )
    async def get_upstream(
        upstream_service_id: str,
        context: AdminContext,
    ) -> UpstreamDetailResponse:
        upstream = await queries.get_upstream(context.tenant_id, upstream_service_id)
        if upstream is None:
            raise UpstreamNotFoundError("upstream did not exist in tenant")
        if upstream.service_type != "http" or upstream.transport_type != "http":
            raise FeatureNotEnabledError("Remote MCP upstream response is not supported")
        return UpstreamDetailResponse.model_validate(upstream)

    @router.get(
        "/openapi/imports",
        response_model=ImportJobPageResponse,
        operation_id="listOpenApiImports",
        responses=problem_responses(422),
    )
    async def list_imports(
        context: AdminContext,
        offset: PageOffset = 0,
        limit: PageLimit = 50,
        job_status: Annotated[ImportJobStatus | None, Query(alias="status")] = None,
        upstream_service_id: str | None = None,
    ) -> ImportJobPageResponse:
        page = await queries.list_imports(
            context.tenant_id,
            offset=offset,
            limit=limit,
            status=job_status.value if job_status else None,
            upstream_id=upstream_service_id,
        )
        return _page_response(ImportJobPageResponse, ImportJobSummaryResponse, page)

    @router.get(
        "/openapi/operations",
        response_model=ReviewOperationPageResponse,
        operation_id="listReviewOperations",
        responses=problem_responses(422),
    )
    async def list_review_operations(
        context: AdminContext,
        offset: PageOffset = 0,
        limit: PageLimit = 50,
        review_status: OperationReviewStatus | None = None,
        conflict_status: OperationConflictStatus | None = None,
        import_job_id: str | None = None,
    ) -> ReviewOperationPageResponse:
        page = await queries.list_review_operations(
            context.tenant_id,
            offset=offset,
            limit=limit,
            review_status=review_status.value if review_status else None,
            conflict_status=conflict_status.value if conflict_status else None,
            import_job_id=import_job_id,
        )
        return _page_response(
            ReviewOperationPageResponse,
            ReviewOperationSummaryResponse,
            page,
        )

    @router.get(
        "/tools",
        response_model=ToolPageResponse,
        operation_id="listTools",
        responses=problem_responses(422),
    )
    async def list_tools(
        context: AdminContext,
        offset: PageOffset = 0,
        limit: PageLimit = 50,
        namespace: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
        tool_status: Annotated[ToolStatus | None, Query(alias="status")] = None,
        version_status: ToolVersionStatus | None = None,
        visibility: ToolVisibility | None = None,
        side_effect: ToolSideEffect | None = None,
    ) -> ToolPageResponse:
        page = await queries.list_tools(
            context.tenant_id,
            offset=offset,
            limit=limit,
            namespace=namespace,
            status=tool_status.value if tool_status else None,
            version_status=version_status.value if version_status else None,
            visibility=visibility.value if visibility else None,
            side_effect=side_effect.value if side_effect else None,
        )
        return _page_response(ToolPageResponse, ToolSummaryResponse, page)

    @router.get(
        "/tools/{tool_id}",
        response_model=ToolDetailResponse,
        operation_id="getTool",
        responses=problem_responses(404),
    )
    async def get_tool(tool_id: str, context: AdminContext) -> ToolDetailResponse:
        tool = await queries.get_tool(context.tenant_id, tool_id)
        if tool is None:
            raise ToolNotFoundError("tool did not exist in tenant")
        return ToolDetailResponse.model_validate(tool)

    @router.get(
        "/tools/{tool_id}/versions",
        response_model=ToolVersionPageResponse,
        operation_id="listToolVersions",
        responses=problem_responses(404, 422),
    )
    async def list_tool_versions(
        tool_id: str,
        context: AdminContext,
        offset: PageOffset = 0,
        limit: PageLimit = 50,
    ) -> ToolVersionPageResponse:
        if await queries.get_tool(context.tenant_id, tool_id) is None:
            raise ToolNotFoundError("tool did not exist in tenant")
        page = await queries.list_tool_versions(
            context.tenant_id,
            tool_id,
            offset=offset,
            limit=limit,
        )
        return _page_response(ToolVersionPageResponse, ToolVersionDetailResponse, page)

    @router.get(
        "/tool-versions/{tool_version_id}",
        response_model=ToolVersionDetailResponse,
        operation_id="getToolVersion",
        responses=problem_responses(404),
    )
    async def get_tool_version(
        tool_version_id: str,
        context: AdminContext,
    ) -> ToolVersionDetailResponse:
        version = await queries.get_tool_version(context.tenant_id, tool_version_id)
        if version is None:
            raise ToolVersionNotFoundError("tool version did not exist in tenant")
        return ToolVersionDetailResponse.model_validate(version)

    @router.get(
        "/tool-versions/{tool_version_id}/binding",
        response_model=ToolBindingDetailResponse,
        operation_id="getToolVersionBinding",
        responses=problem_responses(404, 501),
    )
    async def get_tool_version_binding(
        tool_version_id: str,
        context: AdminContext,
    ) -> ToolBindingDetailResponse:
        binding = await queries.get_tool_version_binding(context.tenant_id, tool_version_id)
        if binding is None:
            raise ToolBindingNotFoundError("tool version binding did not exist in tenant")
        if binding.binding_type != "http":
            raise FeatureNotEnabledError("Remote MCP tool binding response is not supported")
        return ToolBindingDetailResponse.model_validate(binding)

    @router.get(
        "/tool-bindings/{tool_binding_id}",
        response_model=ToolBindingDetailResponse,
        operation_id="getToolBinding",
        responses=problem_responses(404, 501),
    )
    async def get_tool_binding(
        tool_binding_id: str,
        context: AdminContext,
    ) -> ToolBindingDetailResponse:
        binding = await queries.get_tool_binding(context.tenant_id, tool_binding_id)
        if binding is None:
            raise ToolBindingNotFoundError("tool binding did not exist in tenant")
        if binding.binding_type != "http":
            raise FeatureNotEnabledError("Remote MCP tool binding response is not supported")
        return ToolBindingDetailResponse.model_validate(binding)

    @router.get(
        "/approvals",
        response_model=ApprovalPageResponse,
        operation_id="listApprovals",
        responses=problem_responses(422),
    )
    async def list_approvals(
        context: AdminContext,
        offset: PageOffset = 0,
        limit: PageLimit = 50,
        approval_status: Annotated[ApprovalStatus | None, Query(alias="status")] = None,
        principal_id: str | None = None,
        tool_id: str | None = None,
    ) -> ApprovalPageResponse:
        page = await queries.list_approvals(
            context.tenant_id,
            offset=offset,
            limit=limit,
            status=approval_status.value if approval_status else None,
            principal_id=principal_id,
            tool_id=tool_id,
        )
        return _page_response(ApprovalPageResponse, ApprovalSummaryResponse, page)

    @router.get(
        "/executions",
        response_model=ExecutionPageResponse,
        operation_id="listExecutions",
        responses=problem_responses(422),
    )
    async def list_executions(
        context: AdminContext,
        offset: PageOffset = 0,
        limit: PageLimit = 50,
        execution_status: Annotated[ExecutionStatus | None, Query(alias="status")] = None,
        principal_id: str | None = None,
        tool_id: str | None = None,
        trace_id: str | None = None,
    ) -> ExecutionPageResponse:
        page = await queries.list_executions(
            context.tenant_id,
            offset=offset,
            limit=limit,
            status=execution_status.value if execution_status else None,
            principal_id=principal_id,
            tool_id=tool_id,
            trace_id=trace_id,
        )
        return _page_response(ExecutionPageResponse, ExecutionSummaryResponse, page)

    @router.get(
        "/executions/{execution_id}",
        response_model=ExecutionSummaryResponse,
        operation_id="getExecution",
        responses=problem_responses(404),
    )
    async def get_execution(
        execution_id: str,
        context: AdminContext,
    ) -> ExecutionSummaryResponse:
        execution = await queries.get_execution(context.tenant_id, execution_id)
        if execution is None:
            raise ToolExecutionNotFoundError("execution did not exist in tenant")
        return ExecutionSummaryResponse.model_validate(execution)

    @router.get(
        "/executions/{execution_id}/attempts",
        response_model=ExecutionAttemptPageResponse,
        operation_id="listExecutionAttempts",
        responses=problem_responses(404, 422),
    )
    async def list_execution_attempts(
        execution_id: str,
        context: AdminContext,
        offset: PageOffset = 0,
        limit: PageLimit = 50,
    ) -> ExecutionAttemptPageResponse:
        if await queries.get_execution(context.tenant_id, execution_id) is None:
            raise ToolExecutionNotFoundError("execution did not exist in tenant")
        page = await queries.list_execution_attempts(
            context.tenant_id,
            execution_id,
            offset=offset,
            limit=limit,
        )
        return _page_response(
            ExecutionAttemptPageResponse,
            ExecutionAttemptResponse,
            page,
        )

    @router.get(
        "/audit-events",
        response_model=AuditEventPageResponse,
        operation_id="listAuditEvents",
        responses=problem_responses(422),
    )
    async def list_audit_events(
        context: AdminContext,
        offset: PageOffset = 0,
        limit: PageLimit = 50,
        trace_id: str | None = None,
        principal_id: str | None = None,
        tool_id: str | None = None,
        execution_id: str | None = None,
        outcome: AuditOutcome | None = None,
    ) -> AuditEventPageResponse:
        page = await queries.list_audit_events(
            context.tenant_id,
            offset=offset,
            limit=limit,
            trace_id=trace_id,
            principal_id=principal_id,
            tool_id=tool_id,
            execution_id=execution_id,
            outcome=outcome.value if outcome else None,
        )
        return _page_response(AuditEventPageResponse, AuditEventResponse, page)

    @router.get(
        "/search/projection-status",
        response_model=SearchProjectionResponse,
        operation_id="getSearchProjectionStatus",
        responses=problem_responses(503),
    )
    async def get_search_projection_status(context: AdminContext) -> SearchProjectionResponse:
        return SearchProjectionResponse.model_validate(
            await queries.search_projection_status(context.tenant_id)
        )

    return router


def _page_response[ResponseT: BaseModel, ItemResponseT: BaseModel](
    response_type: type[ResponseT],
    item_type: type[ItemResponseT],
    page: Page[Any],
) -> ResponseT:
    return response_type.model_validate(
        {
            "items": [item_type.model_validate(item) for item in page.items],
            "page": PageMetadata(offset=page.offset, limit=page.limit, total=page.total),
        }
    )
