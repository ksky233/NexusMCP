"""ExecutableToolResolver 的 PostgreSQL Published Projection Adapter。"""

from copy import deepcopy

from sqlalchemy import select

from nexusmcp.infrastructure.persistence.identifiers import as_uuid
from nexusmcp.infrastructure.persistence.runtime import DatabaseRuntimePort
from nexusmcp.modules.catalog.adapters.sqlalchemy_models import ToolModel, ToolVersionModel
from nexusmcp.modules.catalog.domain import (
    ToolSideEffect,
    ToolStatus,
    ToolVersionStatus,
    ToolVisibility,
)
from nexusmcp.modules.connectors.adapters.sqlalchemy_models import ToolBindingModel
from nexusmcp.modules.connectors.domain import (
    ToolBindingStatus,
    ToolBindingType,
)
from nexusmcp.modules.execution.domain import ResolvedExecutableTool
from nexusmcp.modules.registry.adapters.sqlalchemy_models import UpstreamServiceModel
from nexusmcp.modules.registry.domain import UpstreamStatus


class SqlAlchemyExecutableToolResolver:
    def __init__(self, database_runtime: DatabaseRuntimePort) -> None:
        self._database_runtime = database_runtime

    async def resolve(
        self,
        tenant_id: str,
        canonical_name: str,
    ) -> ResolvedExecutableTool | None:
        tenant_uuid = as_uuid(tenant_id, field_name="tenant id")
        statement = (
            select(ToolModel, ToolVersionModel, ToolBindingModel, UpstreamServiceModel)
            .join(ToolVersionModel, ToolVersionModel.tool_id == ToolModel.id)
            .join(ToolBindingModel, ToolBindingModel.tool_version_id == ToolVersionModel.id)
            .join(
                UpstreamServiceModel,
                UpstreamServiceModel.id == ToolBindingModel.upstream_service_id,
            )
            .where(
                ToolModel.tenant_id == tenant_uuid,
                ToolVersionModel.tenant_id == tenant_uuid,
                ToolBindingModel.tenant_id == tenant_uuid,
                UpstreamServiceModel.tenant_id == tenant_uuid,
                ToolModel.canonical_name == canonical_name,
                ToolModel.status == ToolStatus.ACTIVE.value,
                ToolVersionModel.status == ToolVersionStatus.PUBLISHED.value,
                ToolBindingModel.status == ToolBindingStatus.PUBLISHED.value,
                UpstreamServiceModel.status == UpstreamStatus.ACTIVE.value,
            )
        )
        session_factory = self._database_runtime.require_session_factory()
        async with session_factory() as session:
            row = (await session.execute(statement)).tuples().one_or_none()
        if row is None:
            return None
        tool, version, binding, upstream = row
        return ResolvedExecutableTool(
            tenant_id=tenant_id,
            tool_id=str(tool.id),
            tool_version_id=str(version.id),
            tool_binding_id=str(binding.id),
            upstream_service_id=str(upstream.id),
            canonical_name=tool.canonical_name,
            version=version.version,
            input_schema=deepcopy(version.input_schema_json),
            output_schema=deepcopy(version.output_schema_json),
            side_effect=ToolSideEffect(version.side_effect),
            visibility=ToolVisibility(version.visibility),
            binding_type=ToolBindingType(binding.binding_type),
            binding_config=deepcopy(binding.binding_config_json),
            upstream_endpoint=upstream.endpoint,
            upstream_auth_scheme=upstream.auth_scheme,
        )
