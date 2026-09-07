"""FastAPI Application Factory 与依赖组装。"""

from collections.abc import AsyncGenerator, Awaitable, Callable
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
    RuntimeExecutionUnitOfWorkFactory,
    RuntimeOpenApiImportUnitOfWorkFactory,
    RuntimeRegistryUnitOfWorkFactory,
    RuntimeReviewUnitOfWorkFactory,
    RuntimeToolSearchUnitOfWorkFactory,
    RuntimeToolsetUnitOfWorkFactory,
)
from nexusmcp.infrastructure.clock import SystemClock
from nexusmcp.infrastructure.identifiers import UuidIdentifierGenerator
from nexusmcp.infrastructure.networking import (
    StaticUpstreamEndpointPolicy,
    SystemHostResolver,
)
from nexusmcp.infrastructure.observability import (
    NexusTelemetry,
    TelemetrySettings,
    create_telemetry_runtime,
)
from nexusmcp.infrastructure.persistence.admin_queries import SqlAlchemyControlPlaneQueries
from nexusmcp.infrastructure.persistence.demo_workspace import SqlAlchemyDemoWorkspaceResetter
from nexusmcp.infrastructure.persistence.local_tenant import (
    ensure_configured_tenant,
    ensure_local_development_tenant,
)
from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntime, DatabaseRuntimePort
from nexusmcp.interfaces.admin import AdminServices, create_admin_app
from nexusmcp.interfaces.admin.toolset_routes import ToolsetAdminServices
from nexusmcp.interfaces.health.router import create_health_router
from nexusmcp.interfaces.mcp.context import request_headers, resolve_request_context
from nexusmcp.interfaces.mcp.http_transport import create_mcp_http_transport
from nexusmcp.interfaces.mcp.server import create_mcp_server
from nexusmcp.modules.approval.use_cases import (
    DecideApproval,
    GetApproval,
    RequestApproval,
)
from nexusmcp.modules.catalog.adapters.in_memory import InMemoryToolCatalogRepository
from nexusmcp.modules.catalog.adapters.sqlalchemy_reader import SqlAlchemyPublishedToolReader
from nexusmcp.modules.catalog.adapters.sqlalchemy_search import SqlAlchemyPublishedToolSearch
from nexusmcp.modules.catalog.ports import PublishedToolReader, PublishedToolSearch
from nexusmcp.modules.catalog.publish import PublishTool
from nexusmcp.modules.catalog.review import SubmitToolVersionForReview
from nexusmcp.modules.catalog.search import SearchPublishedTools
from nexusmcp.modules.catalog.use_cases import ListVisibleTools
from nexusmcp.modules.control_plane.demo_reset import ResetDemoWorkspace
from nexusmcp.modules.credentials.domain import SecretValue
from nexusmcp.modules.credentials.ports import CredentialBindingResolver, CredentialProvider
from nexusmcp.modules.execution.adapters.asyncio_sleeper import AsyncioRetrySleeper
from nexusmcp.modules.execution.adapters.httpx_executor import HttpxToolExecutor
from nexusmcp.modules.execution.adapters.jsonschema_validator import JsonSchemaArgumentsValidator
from nexusmcp.modules.execution.adapters.sqlalchemy_reader import (
    SqlAlchemyAuditEventReader,
    SqlAlchemyToolExecutionReader,
)
from nexusmcp.modules.execution.adapters.sqlalchemy_resolver import (
    SqlAlchemyExecutableToolResolver,
)
from nexusmcp.modules.execution.call_tool import CallTool
from nexusmcp.modules.execution.lifecycle import ExecutionLifecycle
from nexusmcp.modules.execution.retrying_executor import ExecuteWithRetry
from nexusmcp.modules.identity.adapters.context_principal import ContextPrincipalResolver
from nexusmcp.modules.identity.domain import InternalPrincipal, PrincipalType
from nexusmcp.modules.identity.ports import AgentServiceAuthenticator
from nexusmcp.modules.openapi_import.adapters.local_document_reader import (
    LocalOpenApiDocumentReader,
)
from nexusmcp.modules.openapi_import.import_openapi import ImportOpenApi
from nexusmcp.modules.openapi_import.parser import OpenApiParser
from nexusmcp.modules.openapi_import.queries import GetOpenApiImport
from nexusmcp.modules.openapi_import.review import ReviewImportedOperation
from nexusmcp.modules.policy.adapters.static_read_only import StaticReadOnlyPolicyEvaluator
from nexusmcp.modules.policy.ports import PolicyEvaluator
from nexusmcp.modules.registry.egress_ports import (
    AllowAllUpstreamEndpointPolicy,
    UpstreamEndpointPolicy,
)
from nexusmcp.modules.registry.use_cases import (
    DisableUpstream,
    RegisterUpstream,
    UpdateUpstream,
)
from nexusmcp.modules.tool_search.adapters.siliconflow import SiliconFlowEmbeddingProvider
from nexusmcp.modules.tool_search.adapters.sqlalchemy_job_store import (
    SqlAlchemyToolSearchReindexJobStore,
)
from nexusmcp.modules.tool_search.adapters.sqlalchemy_vector_search import (
    SqlAlchemyExactVectorToolSearch,
)
from nexusmcp.modules.tool_search.document_builder import ToolSearchDocumentBuilder
from nexusmcp.modules.tool_search.hybrid_search import SearchHybridTools
from nexusmcp.modules.tool_search.index_management import (
    CreateToolSearchReindexJob,
    GetToolSearchReindexJob,
    InspectToolSearchIndex,
    ListToolSearchReindexJobs,
    RunToolSearchReindexJob,
)
from nexusmcp.modules.tool_search.ports import EmbeddingProvider
from nexusmcp.modules.tool_search.rank_fusion import ReciprocalRankFusion
from nexusmcp.modules.tool_search.reindex_tools import ReindexTools
from nexusmcp.modules.tool_search.search_tools import SearchTools
from nexusmcp.modules.tool_search.vector_search import SearchVectorTools
from nexusmcp.modules.toolsets.runtime import ResolveToolsetAccess
from nexusmcp.modules.toolsets.use_cases import (
    ActivateToolset,
    CreateToolset,
    DisableToolset,
    EnsureAllPublishedToolset,
    GetToolset,
    ListToolsets,
    ReplaceToolsetGrants,
    ReplaceToolsetMembers,
    UpdateToolset,
)
from nexusmcp.shared.request_context import RequestContext


def create_app(
    settings: Settings | None = None,
    tool_reader: PublishedToolReader | None = None,
    database_runtime: DatabaseRuntimePort | None = None,
    tool_http_client: httpx.AsyncClient | None = None,
    agent_service_authenticator: AgentServiceAuthenticator | None = None,
    policy_evaluator: PolicyEvaluator | None = None,
    credential_binding_resolver: CredentialBindingResolver | None = None,
    credential_provider: CredentialProvider | None = None,
    request_state_security: RequestStateSecurity | None = None,
    published_tool_search: PublishedToolSearch | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    telemetry: NexusTelemetry | None = None,
    upstream_endpoint_policy: UpstreamEndpointPolicy | None = None,
) -> FastAPI:
    """创建完整组装的应用，不让业务代码依赖全局对象。"""

    resolved_settings = settings or get_settings()
    if resolved_settings.mcp_identity_mode == "service_identity":
        if agent_service_authenticator is None:
            raise RuntimeError("service_identity requires AgentServiceAuthenticator")
        static_agent_principal = None
    else:
        if agent_service_authenticator is not None:
            raise RuntimeError("static_service does not accept AgentServiceAuthenticator")
        static_agent_principal = InternalPrincipal(
            id=resolved_settings.static_agent_principal_id,
            tenant_id=resolved_settings.local_tenant_id,
            principal_type=PrincipalType.AGENT_SERVICE,
            authn_method="static_service",
        )
    owned_telemetry_runtime = None
    resolved_telemetry = telemetry
    if resolved_telemetry is None:
        owned_telemetry_runtime = create_telemetry_runtime(
            TelemetrySettings(
                enabled=resolved_settings.telemetry_enabled,
                exporter=resolved_settings.telemetry_exporter,
                service_name=resolved_settings.service_name,
                environment=resolved_settings.environment,
                otlp_endpoint=resolved_settings.telemetry_otlp_endpoint,
                export_interval_ms=resolved_settings.telemetry_export_interval_ms,
                export_timeout_seconds=resolved_settings.telemetry_export_timeout_seconds,
            )
        )
        resolved_telemetry = owned_telemetry_runtime.telemetry
    resolved_endpoint_policy = upstream_endpoint_policy
    if resolved_endpoint_policy is None:
        if resolved_settings.upstream_egress_policy_enabled:
            resolved_endpoint_policy = StaticUpstreamEndpointPolicy(
                resolver=SystemHostResolver(),
                allowed_hosts=resolved_settings.upstream_allowed_hosts,
                allowed_cidrs=resolved_settings.upstream_allowed_cidrs,
                allowed_ports=resolved_settings.upstream_allowed_ports,
                allow_local_demo=resolved_settings.upstream_allow_local_demo,
            )
        else:
            resolved_endpoint_policy = AllowAllUpstreamEndpointPolicy()
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
    resolved_policy_evaluator = policy_evaluator or StaticReadOnlyPolicyEvaluator()
    principal_resolver = ContextPrincipalResolver()
    reindex_job_store: SqlAlchemyToolSearchReindexJobStore | None = None
    search_backend = published_tool_search
    if search_backend is None and resolved_runtime is not None:
        search_backend = SqlAlchemyPublishedToolSearch(resolved_runtime)
    if search_backend is None and isinstance(resolved_reader, InMemoryToolCatalogRepository):
        search_backend = resolved_reader
    resolved_embedding_provider = embedding_provider
    embedding_http_client: httpx.AsyncClient | None = None
    if (
        resolved_embedding_provider is None
        and resolved_runtime is not None
        and resolved_settings.catalog_backend == "postgresql"
        and resolved_settings.embedding_api_key is not None
    ):
        embedding_http_client = httpx.AsyncClient(
            follow_redirects=False,
            trust_env=False,
        )
        resolved_embedding_provider = SiliconFlowEmbeddingProvider(
            embedding_http_client,
            api_url=resolved_settings.embedding_api_url,
            api_key=SecretValue(resolved_settings.embedding_api_key.get_secret_value()),
            model=resolved_settings.embedding_model,
            dimensions=resolved_settings.embedding_dimensions,
            timeout_seconds=resolved_settings.embedding_timeout_seconds,
            max_batch_size=resolved_settings.embedding_batch_size,
        )
    lexical_search = SearchPublishedTools(search_backend) if search_backend is not None else None
    hybrid_search: SearchHybridTools | None = None
    if (
        lexical_search is not None
        and resolved_runtime is not None
        and resolved_settings.catalog_backend == "postgresql"
        and resolved_embedding_provider is not None
    ):
        hybrid_search = SearchHybridTools(
            lexical_search=lexical_search,
            vector_search=SearchVectorTools(
                embedding_provider=resolved_embedding_provider,
                vector_search=SqlAlchemyExactVectorToolSearch(resolved_runtime),
            ),
            rank_fusion=ReciprocalRankFusion(),
        )
    search_tools = (
        SearchTools(
            lexical_search=lexical_search,
            principal_resolver=principal_resolver,
            policy_evaluator=resolved_policy_evaluator,
            hybrid_search=hybrid_search,
            hybrid_diagnostic_search=hybrid_search,
            hybrid_index_version=(
                hybrid_search.index_version if hybrid_search is not None else None
            ),
        )
        if lexical_search is not None
        else None
    )
    clock = SystemClock()
    identifier_generator = UuidIdentifierGenerator()
    toolset_uow_factory = (
        RuntimeToolsetUnitOfWorkFactory(resolved_runtime)
        if resolved_runtime is not None and resolved_settings.catalog_backend == "postgresql"
        else None
    )
    ensure_all_published = (
        EnsureAllPublishedToolset(toolset_uow_factory, identifier_generator, clock)
        if toolset_uow_factory is not None
        else None
    )
    resolve_toolset_access = (
        ResolveToolsetAccess(toolset_uow_factory, resolved_reader)
        if toolset_uow_factory is not None
        else None
    )
    request_approval: RequestApproval | None = None
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
        decide_approval = DecideApproval(approval_uow_factory, clock, identifier_generator)
        get_approval = GetApproval(approval_uow_factory)
    call_tool_use_case: CallTool | None = None
    execution_reader: SqlAlchemyToolExecutionReader | None = None
    audit_reader: SqlAlchemyAuditEventReader | None = None
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
        execution_lifecycle = ExecutionLifecycle(
            RuntimeExecutionUnitOfWorkFactory(resolved_runtime),
            clock,
            identifier_generator,
        )
        execution_reader = SqlAlchemyToolExecutionReader(resolved_runtime)
        audit_reader = SqlAlchemyAuditEventReader(resolved_runtime)
        call_tool_use_case = CallTool(
            principal_resolver=principal_resolver,
            tool_resolver=SqlAlchemyExecutableToolResolver(resolved_runtime),
            arguments_validator=JsonSchemaArgumentsValidator(),
            policy_evaluator=resolved_policy_evaluator,
            execution_lifecycle=execution_lifecycle,
            executor=ExecuteWithRetry(
                HttpxToolExecutor(
                    resolved_http_client,
                    endpoint_policy=resolved_endpoint_policy,
                ),
                execution_lifecycle,
                AsyncioRetrySleeper(),
                max_attempts=resolved_settings.tool_retry_max_attempts,
                initial_backoff_seconds=(resolved_settings.tool_retry_initial_backoff_seconds),
            ),
            credential_binding_resolver=credential_binding_resolver,
            credential_provider=credential_provider,
            request_approval=request_approval,
            upstream_endpoint_policy=resolved_endpoint_policy,
            timeout_seconds=resolved_settings.tool_call_timeout_seconds,
        )

    def context_resolver(ctx: ServerRequestContext[Any, Any]) -> RequestContext:
        principal = static_agent_principal
        if agent_service_authenticator is not None:
            principal = agent_service_authenticator.authenticate(
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
        search_tools=search_tools,
        search_first=resolved_settings.tool_discovery_mode == "search_first",
        decide_approval=decide_approval,
        telemetry=resolved_telemetry,
        request_state_security=request_state_security or _request_state_security(resolved_settings),
        resolve_toolset_access=resolve_toolset_access,
    )
    transport_security = TransportSecuritySettings(
        allowed_hosts=resolved_settings.transport_allowed_hosts,
        allowed_origins=resolved_settings.transport_allowed_origins,
    )
    mcp_transport = create_mcp_http_transport(
        mcp_server,
        transport_security=transport_security,
    )
    mcp_app = mcp_transport.app

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        # Mounted MCP 子应用不会运行自身 Lifespan，必须由宿主应用管理。
        runtime_started = False
        try:
            if resolved_runtime is not None:
                await resolved_runtime.start()
                runtime_started = True
                if (
                    resolved_settings.environment == "development"
                    and resolved_settings.control_plane_enabled
                ):
                    await ensure_local_development_tenant(
                        resolved_runtime,
                        resolved_settings.local_tenant_id,
                    )
                elif (
                    resolved_settings.admin_identity_mode == "public_demo"
                    and resolved_settings.control_plane_enabled
                ):
                    await ensure_configured_tenant(
                        resolved_runtime,
                        resolved_settings.local_tenant_id,
                        name="NexusMCP Public Demo",
                    )
                if ensure_all_published is not None:
                    await ensure_all_published.execute(
                        resolved_settings.local_tenant_id,
                        principal_ids=(
                            (resolved_settings.static_agent_principal_id,)
                            if static_agent_principal is not None
                            else ()
                        ),
                    )
                if reindex_job_store is not None:
                    await reindex_job_store.recover_interrupted(
                        resolved_settings.local_tenant_id,
                        finished_at=SystemClock().now(),
                    )
            async with mcp_transport.session_manager.run():
                yield
        finally:
            if owns_http_client and resolved_http_client is not None:
                await resolved_http_client.aclose()
            if embedding_http_client is not None:
                await embedding_http_client.aclose()
            if resolved_runtime is not None and runtime_started:
                await resolved_runtime.stop()
            if owned_telemetry_runtime is not None:
                owned_telemetry_runtime.shutdown()

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
        tool_search_uow_factory = RuntimeToolSearchUnitOfWorkFactory(resolved_runtime)
        if toolset_uow_factory is None:  # pragma: no cover - 上述 Runtime 检查已保证
            raise RuntimeError("Control Plane requires Toolset Unit of Work")
        published_tool_reader = SqlAlchemyPublishedToolReader(resolved_runtime)
        document_builder = ToolSearchDocumentBuilder()
        reindex_job_store = SqlAlchemyToolSearchReindexJobStore(resolved_runtime)
        reindex_tools = ReindexTools(
            published_tools=published_tool_reader,
            unit_of_work_factory=tool_search_uow_factory,
            document_builder=document_builder,
            embedding_provider=resolved_embedding_provider,
            embedding_model=resolved_settings.embedding_model,
            embedding_dimensions=resolved_settings.embedding_dimensions,
            clock=clock,
            identifier_generator=identifier_generator,
        )
        admin_app = create_admin_app(
            AdminServices(
                register_upstream=RegisterUpstream(
                    registry_uow_factory,
                    identifier_generator,
                    resolved_endpoint_policy,
                ),
                update_upstream=UpdateUpstream(
                    registry_uow_factory,
                    resolved_endpoint_policy,
                ),
                disable_upstream=DisableUpstream(registry_uow_factory),
                queries=SqlAlchemyControlPlaneQueries(
                    resolved_runtime,
                    embedding_model=resolved_settings.embedding_model,
                    embedding_dimensions=resolved_settings.embedding_dimensions,
                ),
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
                search_lab=search_tools,
                inspect_search_index=InspectToolSearchIndex(
                    published_tools=published_tool_reader,
                    unit_of_work_factory=tool_search_uow_factory,
                    document_builder=document_builder,
                    embedding_model=resolved_settings.embedding_model,
                    embedding_dimensions=resolved_settings.embedding_dimensions,
                    embedding_available=resolved_embedding_provider is not None,
                ),
                create_reindex_job=CreateToolSearchReindexJob(
                    store=reindex_job_store,
                    identifier_generator=identifier_generator,
                    clock=clock,
                    embedding_model=resolved_settings.embedding_model,
                    embedding_dimensions=resolved_settings.embedding_dimensions,
                    embedding_available=resolved_embedding_provider is not None,
                ),
                run_reindex_job=RunToolSearchReindexJob(
                    store=reindex_job_store,
                    reindex_tools=reindex_tools,
                    clock=clock,
                ),
                get_reindex_job=GetToolSearchReindexJob(reindex_job_store),
                list_reindex_jobs=ListToolSearchReindexJobs(reindex_job_store),
                decide_approval=decide_approval,
                get_approval=get_approval,
                toolsets=ToolsetAdminServices(
                    create=CreateToolset(toolset_uow_factory, identifier_generator, clock),
                    list=ListToolsets(toolset_uow_factory),
                    get=GetToolset(toolset_uow_factory),
                    update=UpdateToolset(toolset_uow_factory, clock),
                    replace_members=ReplaceToolsetMembers(toolset_uow_factory, clock),
                    replace_grants=ReplaceToolsetGrants(toolset_uow_factory, clock),
                    activate=ActivateToolset(toolset_uow_factory, clock),
                    disable=DisableToolset(toolset_uow_factory, clock),
                ),
                reset_demo_workspace=(
                    ResetDemoWorkspace(
                        SqlAlchemyDemoWorkspaceResetter(resolved_runtime),
                        after_reset=(
                            _toolset_baseline_initializer(
                                ensure_all_published,
                                (
                                    resolved_settings.static_agent_principal_id
                                    if static_agent_principal is not None
                                    else None
                                ),
                            )
                            if ensure_all_published is not None
                            else None
                        ),
                    )
                    if resolved_settings.admin_identity_mode == "public_demo"
                    else None
                ),
            ),
            tenant_id=resolved_settings.local_tenant_id,
            principal_id=(
                resolved_settings.demo_admin_principal_id
                if resolved_settings.admin_identity_mode == "public_demo"
                else resolved_settings.local_admin_principal_id
            ),
            authn_method=(
                "public_demo"
                if resolved_settings.admin_identity_mode == "public_demo"
                else "local_admin"
            ),
        )

    app = FastAPI(
        title=resolved_settings.app_name,
        debug=resolved_settings.debug,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.mcp_server = mcp_server
    app.state.mcp_transport = mcp_transport
    app.state.database_runtime = resolved_runtime
    app.state.admin_app = admin_app
    app.state.execution_reader = execution_reader
    app.state.audit_reader = audit_reader
    app.state.decide_approval = decide_approval
    app.state.get_approval = get_approval
    app.state.embedding_provider = resolved_embedding_provider
    app.state.telemetry = resolved_telemetry
    app.state.telemetry_runtime = owned_telemetry_runtime
    app.state.upstream_endpoint_policy = resolved_endpoint_policy

    # 先注册宿主路由，再注册 Catch-all MCP Mount，避免 /health 被截获。
    app.include_router(create_health_router(readiness_probe))
    if admin_app is not None:
        app.mount("/admin", admin_app)
    app.mount("/", mcp_app)
    return app


def _toolset_baseline_initializer(
    ensure_all_published: EnsureAllPublishedToolset,
    principal_id: str | None,
) -> Callable[[str], Awaitable[None]]:
    async def initialize(tenant_id: str) -> None:
        await ensure_all_published.execute(
            tenant_id,
            principal_ids=(principal_id,) if principal_id is not None else (),
        )

    return initialize


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
