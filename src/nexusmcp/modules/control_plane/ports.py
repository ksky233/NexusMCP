"""Web Control Plane 的跨上下文 Query Port。"""

from typing import Protocol

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


class ControlPlaneQueryPort(Protocol):
    async def dashboard(self, tenant_id: str) -> DashboardSummary: ...

    async def get_upstream(self, tenant_id: str, upstream_id: str) -> UpstreamDetail | None: ...

    async def list_upstreams(
        self,
        tenant_id: str,
        *,
        offset: int,
        limit: int,
        namespace: str | None,
        status: str | None,
    ) -> Page[UpstreamDetail]: ...

    async def list_imports(
        self,
        tenant_id: str,
        *,
        offset: int,
        limit: int,
        status: str | None,
        upstream_id: str | None,
    ) -> Page[ImportJobSummary]: ...

    async def list_review_operations(
        self,
        tenant_id: str,
        *,
        offset: int,
        limit: int,
        review_status: str | None,
        conflict_status: str | None,
        import_job_id: str | None,
    ) -> Page[ReviewOperationSummary]: ...

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
    ) -> Page[ToolSummary]: ...

    async def get_tool(self, tenant_id: str, tool_id: str) -> ToolDetail | None: ...

    async def list_tool_versions(
        self,
        tenant_id: str,
        tool_id: str,
        *,
        offset: int,
        limit: int,
    ) -> Page[ToolVersionDetail]: ...

    async def get_tool_version(
        self,
        tenant_id: str,
        tool_version_id: str,
    ) -> ToolVersionDetail | None: ...

    async def get_tool_binding(
        self,
        tenant_id: str,
        binding_id: str,
    ) -> ToolBindingDetail | None: ...

    async def get_tool_version_binding(
        self,
        tenant_id: str,
        tool_version_id: str,
    ) -> ToolBindingDetail | None: ...

    async def list_approvals(
        self,
        tenant_id: str,
        *,
        offset: int,
        limit: int,
        status: str | None,
        principal_id: str | None,
        tool_id: str | None,
    ) -> Page[ApprovalSummary]: ...

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
    ) -> Page[ExecutionSummary]: ...

    async def get_execution(
        self,
        tenant_id: str,
        execution_id: str,
    ) -> ExecutionSummary | None: ...

    async def list_execution_attempts(
        self,
        tenant_id: str,
        execution_id: str,
        *,
        offset: int,
        limit: int,
    ) -> Page[ExecutionAttemptSummary]: ...

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
    ) -> Page[AuditEventSummary]: ...

    async def search_projection_status(self, tenant_id: str) -> SearchProjectionSummary: ...
