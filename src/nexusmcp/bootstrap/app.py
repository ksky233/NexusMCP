"""FastAPI Application Factory 与依赖组装。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI
from mcp.server.context import ServerRequestContext
from mcp.server.request_state import RequestStateSecurity
from mcp.server.transport_security import TransportSecuritySettings

from nexusmcp.bootstrap.config import Settings, get_settings
from nexusmcp.bootstrap.persistence_factories import (
    RuntimeApprovalUnitOfWorkFactory,
    RuntimeCatalogUnitOfWorkFactory,
    RuntimeOpenApiImportUnitOfWorkFactory,
    RuntimeRegistryUnitOfWorkFactory,
    RuntimeReviewUnitOfWorkFactory,
)
from nexusmcp.infrastructure.clock import SystemClock
from nexusmcp.infrastructure.identifiers import UuidIdentifierGenerator
from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntime, DatabaseRuntimePort
from nexusmcp.interfaces.admin import AdminServices, create_admin_app
from nexusmcp.interfaces.health.router import create_health_router
from nexusmcp.interfaces.mcp.context import request_headers, resolve_request_context
from nexusmcp.interfaces.mcp.server import create_mcp_server
from nexusmcp.modules.approval.use_cases import (
    ConsumeApproval,
    DecideApproval,
    GetApproval,
    RequestApproval,
)
from nexusmcp.modules.catalog.adapters.in_memory import InMemoryToolCatalogRepository
from nexusmcp.modules.catalog.adapters.sqlalchemy_reader import SqlAlchemyPublishedToolReader
from nexusmcp.modules.catalog.adapters.sqlalchemy_search import SqlAlchemyPublishedToolSearch
from nexusmcp.modules.catalog.ports import PublishedToolReader
from nexusmcp.modules.catalog.publish import PublishTool
from nexusmcp.modules.catalog.review import SubmitToolVersionForReview
from nexusmcp.modules.catalog.search import SearchPublishedTools
from nexusmcp.modules.catalog.use_cases import ListVisibleTools
from nexusmcp.modules.credentials.ports import CredentialBindingResolver, CredentialProvider
from nexusmcp.modules.execution.adapters.httpx_executor import HttpxToolExecutor
from nexusmcp.modules.execution.adapters.in_memory import InMemoryToolExecutionRepository
from nexusmcp.modules.execution.adapters.jsonschema_validator import JsonSchemaArgumentsValidator
from nexusmcp.modules.execution.adapters.sqlalchemy_resolver import (
    SqlAlchemyExecutableToolResolver,
)
from nexusmcp.modules.execution.call_tool import CallTool
from nexusmcp.modules.identity.adapters.context_principal import ContextPrincipalResolver
from nexusmcp.modules.identity.ports import PrincipalAuthenticator
from nexusmcp.modules.openapi_import.adapters.local_document_reader import (
    LocalOpenApiDocumentReader,
)
from nexusmcp.modules.openapi_import.import_openapi import ImportOpenApi
from nexusmcp.modules.openapi_import.parser import OpenApiParser
from nexusmcp.modules.openapi_import.queries import GetOpenApiImport
from nexusmcp.modules.openapi_import.review import ReviewImportedOperation
from nexusmcp.modules.policy.adapters.static_read_only import StaticReadOnlyPolicyEvaluator
from nexusmcp.modules.policy.ports import PolicyEvaluator
from nexusmcp.modules.registry.use_cases import (
    DisableUpstream,
    ListUpstreams,
    RegisterUpstream,
    UpdateUpstream,
)
from nexusmcp.shared.request_context import RequestContext


def create_app(
    settings: Settings | None = None,
    tool_reader: PublishedToolReader | None = None,
    database_runtime: DatabaseRuntimePort | None = None,
    tool_http_client: httpx.AsyncClient | None = None,
    principal_authenticator: PrincipalAuthenticator | None = None,
    policy_evaluator: PolicyEvaluator | None = None,
    credential_binding_resolver: CredentialBindingResolver | None = None,
    credential_provider: CredentialProvider | None = None,
    request_state_security: RequestStateSecurity | None = None,
) -> FastAPI:
    """创建完整组装的应用，不让业务代码依赖全局对象。"""

    resolved_settings = settings or get_settings()
    resolved_runtime = database_runtime
    resolved_reader = tool_reader
    if resolved_reader is None and resolved_settings.catalog_backend == "postgresql":
        if resolved_runtime is None:
            database_url = resolved_settings.database_url
            if database_url is None:  # pragma: no cover - Settings Validator 已阻止该状态
                raise RuntimeError("database URL is required for PostgreSQL catalog")
            resolved_runtime = DatabaseRuntime(
                database_url.get_secret_value(),
                echo=resolved_settings.database_echo,
                readiness_timeout_seconds=resolved_settings.database_readiness_timeout_seconds,
            )
        resolved_reader = SqlAlchemyPublishedToolReader(resolved_runtime)
    if resolved_reader is None:
        resolved_reader = InMemoryToolCatalogRepository()
    list_visible_tools = ListVisibleTools(resolved_reader)
    clock = SystemClock()
    identifier_generator = UuidIdentifierGenerator()
    request_approval: RequestApproval | None = None
    consume_approval: ConsumeApproval | None = None
    decide_approval: DecideApproval | None = None
    get_approval: GetApproval | None = None
    if resolved_runtime is not None:
        approval_uow_factory = RuntimeApprovalUnitOfWorkFactory(resolved_runtime)
        request_approval = RequestApproval(
            approval_uow_factory,
            clock,
            identifier_generator,
            ttl_seconds=resolved_settings.approval_ttl_seconds,
        )
        consume_approval = ConsumeApproval(approval_uow_factory, clock)
        decide_approval = DecideApproval(approval_uow_factory, clock)
        get_approval = GetApproval(approval_uow_factory)
    call_tool_use_case: CallTool | None = None
    execution_repository: InMemoryToolExecutionRepository | None = None
    resolved_http_client = tool_http_client
    owns_http_client = False
    if resolved_settings.tool_execution_enabled:
        if resolved_runtime is None:  # pragma: no cover - Settings/Composition 已阻止该状态
            raise RuntimeError("Tool execution requires Database Runtime")
        if resolved_http_client is None:
            resolved_http_client = httpx.AsyncClient(
                follow_redirects=False,
                trust_env=False,
            )
            owns_http_client = True
        execution_repository = InMemoryToolExecutionRepository()
        call_tool_use_case = CallTool(
            principal_resolver=ContextPrincipalResolver(),
            tool_resolver=SqlAlchemyExecutableToolResolver(resolved_runtime),
            arguments_validator=JsonSchemaArgumentsValidator(),
            policy_evaluator=policy_evaluator or StaticReadOnlyPolicyEvaluator(),
            execution_repository=execution_repository,
            executor=HttpxToolExecutor(resolved_http_client),
            clock=clock,
            identifier_generator=identifier_generator,
            credential_binding_resolver=credential_binding_resolver,
            credential_provider=credential_provider,
            request_approval=request_approval,
            consume_approval=consume_approval,
            timeout_seconds=resolved_settings.tool_call_timeout_seconds,
        )

    def context_resolver(ctx: ServerRequestContext[Any, Any]) -> RequestContext:
        principal = None
        if principal_authenticator is not None:
            principal = principal_authenticator.authenticate(
                request_headers(ctx).get("authorization"),
                resolved_settings.local_tenant_id,
            )
        return resolve_request_context(
            ctx,
            tenant_id=resolved_settings.local_tenant_id,
            principal=principal,
        )

    mcp_server = create_mcp_server(
        list_visible_tools=list_visible_tools,
        context_resolver=context_resolver,
        call_tool=call_tool_use_case,
        decide_approval=decide_approval,
        request_state_security=request_state_security or _request_state_security(resolved_settings),
    )
    transport_security = TransportSecuritySettings(
        allowed_hosts=resolved_settings.transport_allowed_hosts,
        allowed_origins=resolved_settings.transport_allowed_origins,
    )
    mcp_app = mcp_server.streamable_http_app(transport_security=transport_security)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        # Mounted MCP 子应用不会运行自身 Lifespan，必须由宿主应用管理。
        runtime_started = False
        try:
            if resolved_runtime is not None:
                await resolved_runtime.start()
                runtime_started = True
            async with mcp_server.session_manager.run():
                yield
        finally:
            if owns_http_client and resolved_http_client is not None:
                await resolved_http_client.aclose()
            if resolved_runtime is not None and runtime_started:
                await resolved_runtime.stop()

    async def readiness_probe() -> bool:
        if resolved_runtime is None:
            return True
        return await resolved_runtime.is_ready()

    admin_app: FastAPI | None = None
    if resolved_settings.control_plane_enabled:
        if resolved_runtime is None:  # pragma: no cover - Settings/Composition 已阻止该状态
            raise RuntimeError("Control Plane requires Database Runtime")
        if decide_approval is None or get_approval is None:  # pragma: no cover
            raise RuntimeError("Control Plane requires Approval services")
        registry_uow_factory = RuntimeRegistryUnitOfWorkFactory(resolved_runtime)
        import_uow_factory = RuntimeOpenApiImportUnitOfWorkFactory(resolved_runtime)
        review_uow_factory = RuntimeReviewUnitOfWorkFactory(resolved_runtime)
        catalog_uow_factory = RuntimeCatalogUnitOfWorkFactory(resolved_runtime)
        admin_app = create_admin_app(
            AdminServices(
                register_upstream=RegisterUpstream(
                    registry_uow_factory,
                    identifier_generator,
                ),
                update_upstream=UpdateUpstream(registry_uow_factory),
                disable_upstream=DisableUpstream(registry_uow_factory),
                list_upstreams=ListUpstreams(registry_uow_factory),
                import_openapi=ImportOpenApi(
                    import_uow_factory,
                    LocalOpenApiDocumentReader(resolved_settings.openapi_fixture_root),
                    OpenApiParser(),
                    clock,
                    identifier_generator,
                ),
                get_openapi_import=GetOpenApiImport(import_uow_factory),
                review_operation=ReviewImportedOperation(
                    review_uow_factory,
                    clock,
                    identifier_generator,
                ),
                submit_version_review=SubmitToolVersionForReview(
                    catalog_uow_factory,
                    clock,
                ),
                publish_tool=PublishTool(catalog_uow_factory, clock),
                search_tools=SearchPublishedTools(SqlAlchemyPublishedToolSearch(resolved_runtime)),
                decide_approval=decide_approval,
                get_approval=get_approval,
            ),
            tenant_id=resolved_settings.local_tenant_id,
            principal_id=resolved_settings.local_admin_principal_id,
        )

    app = FastAPI(
        title=resolved_settings.app_name,
        debug=resolved_settings.debug,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.mcp_server = mcp_server
    app.state.database_runtime = resolved_runtime
    app.state.admin_app = admin_app
    app.state.execution_repository = execution_repository
    app.state.decide_approval = decide_approval
    app.state.get_approval = get_approval

    # 先注册宿主路由，再注册 Catch-all MCP Mount，避免 /health 被截获。
    app.include_router(create_health_router(readiness_probe))
    if admin_app is not None:
        app.mount("/admin", admin_app)
    app.mount("/", mcp_app)
    return app


def _request_state_security(settings: Settings) -> RequestStateSecurity:
    key = settings.request_state_key
    if key is None:
        return RequestStateSecurity.ephemeral(
            ttl=settings.approval_ttl_seconds,
            audience="nexusmcp",
        )
    return RequestStateSecurity(
        keys=[key.get_secret_value()],
        ttl=settings.approval_ttl_seconds,
        audience="nexusmcp",
    )
