"""FastAPI Application Factory 与依赖组装。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from mcp.server.context import ServerRequestContext
from mcp.server.transport_security import TransportSecuritySettings

from nexusmcp.bootstrap.config import Settings, get_settings
from nexusmcp.bootstrap.persistence_factories import (
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
from nexusmcp.interfaces.mcp.context import resolve_request_context
from nexusmcp.interfaces.mcp.server import create_mcp_server
from nexusmcp.modules.catalog.adapters.in_memory import InMemoryToolCatalogRepository
from nexusmcp.modules.catalog.adapters.sqlalchemy_reader import SqlAlchemyPublishedToolReader
from nexusmcp.modules.catalog.adapters.sqlalchemy_search import SqlAlchemyPublishedToolSearch
from nexusmcp.modules.catalog.ports import PublishedToolReader
from nexusmcp.modules.catalog.publish import PublishTool
from nexusmcp.modules.catalog.review import SubmitToolVersionForReview
from nexusmcp.modules.catalog.search import SearchPublishedTools
from nexusmcp.modules.catalog.use_cases import ListVisibleTools
from nexusmcp.modules.openapi_import.adapters.local_document_reader import (
    LocalOpenApiDocumentReader,
)
from nexusmcp.modules.openapi_import.import_openapi import ImportOpenApi
from nexusmcp.modules.openapi_import.parser import OpenApiParser
from nexusmcp.modules.openapi_import.queries import GetOpenApiImport
from nexusmcp.modules.openapi_import.review import ReviewImportedOperation
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

    def context_resolver(ctx: ServerRequestContext[Any, Any]) -> RequestContext:
        return resolve_request_context(ctx, tenant_id=resolved_settings.local_tenant_id)

    mcp_server = create_mcp_server(
        list_visible_tools=list_visible_tools,
        context_resolver=context_resolver,
    )
    transport_security = TransportSecuritySettings(
        allowed_hosts=resolved_settings.transport_allowed_hosts,
        allowed_origins=resolved_settings.transport_allowed_origins,
    )
    mcp_app = mcp_server.streamable_http_app(transport_security=transport_security)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        # Mounted MCP 子应用不会运行自身 Lifespan，必须由宿主应用管理。
        if resolved_runtime is not None:
            await resolved_runtime.start()
        try:
            async with mcp_server.session_manager.run():
                yield
        finally:
            if resolved_runtime is not None:
                await resolved_runtime.stop()

    async def readiness_probe() -> bool:
        if resolved_runtime is None:
            return True
        return await resolved_runtime.is_ready()

    admin_app: FastAPI | None = None
    if resolved_settings.control_plane_enabled:
        if resolved_runtime is None:  # pragma: no cover - Settings/Composition 已阻止该状态
            raise RuntimeError("Control Plane requires Database Runtime")
        clock = SystemClock()
        identifier_generator = UuidIdentifierGenerator()
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

    # 先注册宿主路由，再注册 Catch-all MCP Mount，避免 /health 被截获。
    app.include_router(create_health_router(readiness_probe))
    if admin_app is not None:
        app.mount("/admin", admin_app)
    app.mount("/", mcp_app)
    return app
